"""Hunt Copilot state machine and execution bridge."""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import Any

from automation.job_queue import HuntJobQueue
from api.hunt_store import load_hunt
from config.settings import Settings, get_settings
from hunt_copilot.conversation_host import ConversationHost
from hunt_copilot.conversation_guide import is_light_smalltalk, suggested_replies
from hunt_copilot.conversation_router import ConversationRouter
from hunt_copilot.llm_planner import HuntCopilotLLMPlanner
from hunt_copilot.patch_merger import StrategyPatchMerger
from hunt_copilot.planner import render_strategy_card
from hunt_copilot.response_builder import CopilotResponseBuilder
from hunt_copilot.schemas import (
    ChannelStatus,
    ChatMessage,
    ConfirmExecutionRequest,
    CopilotHistorySummary,
    CopilotSession,
    CopilotState,
    HuntStrategy,
    PreviewSummary,
)
from hunt_copilot.skill_selector import SearchSkillSelector
from hunt_copilot.state_machine import allowed_actions, choose_state
from hunt_copilot.store import HuntCopilotStore
from hunt_copilot.strategy_fingerprint import strategy_fingerprint, strategy_similarity
from hunt_copilot.strategy_critic import StrategyCritic
from hunt_copilot.strategy_commands import apply_strategy_command, command_applied, parse_strategy_command
from hunt_copilot.validator import StrategyValidator
from search_tools import list_tool_status
from tool_executor import ToolExecutor, build_tool_plan


logger = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class HuntCopilotService:
    def __init__(self, *, store: HuntCopilotStore | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.store = store or HuntCopilotStore()
        self.conversation_router = ConversationRouter(self.settings)
        self.conversation_host = ConversationHost()
        self.llm_planner = HuntCopilotLLMPlanner(self.settings)
        self.patch_merger = StrategyPatchMerger()
        self.validator = StrategyValidator(self.settings)
        self.skill_selector = SearchSkillSelector()
        self.critic = StrategyCritic(self.settings)
        self.response_builder = CopilotResponseBuilder()
        self.tool_executor = ToolExecutor(self.settings)

    def start(self, message: str) -> tuple[CopilotSession, str]:
        session = CopilotSession(
            session_id=str(uuid.uuid4()),
            state=CopilotState.COLLECTING_REQUIREMENTS,
            strategy=HuntStrategy(),
            created_at=now_iso(),
            updated_at=now_iso(),
        )
        if message.strip():
            session.messages.append(ChatMessage(role="user", content=message.strip(), created_at=now_iso()))
            route = self.conversation_router.route(message, session)
            session.last_user_intent = route.intent
            command = parse_strategy_command(message)
            if command and command.operation != "show":
                before = session.strategy.model_copy(deep=True)
                session.strategy = apply_strategy_command(session.strategy, command, raw_message=message)
                session.recent_strategy_changes = _strategy_changes(before, session.strategy)
                session.selected_skill = self.skill_selector.select(text=message, strategy=session.strategy)
                assistant = self._command_response(session, command)
            elif command and command.operation == "show":
                assistant = _current_strategy_summary(session.strategy)
            elif route.should_call_planner and route.should_update_strategy:
                before = session.strategy.model_copy(deep=True)
                planner_response = self.llm_planner.plan(message, session.strategy, session.state.value, **self._planner_context(session))
                session.detected_conflicts = planner_response.detected_conflicts
                session.strategy = self.patch_merger.merge(session.strategy, planner_response.strategy_patch, raw_message=message)
                session.recent_strategy_changes = _strategy_changes(before, session.strategy)
                session.selected_skill = self.skill_selector.select(text=message, strategy=session.strategy)
                assistant = self._assistant_for_current_state(session, fallback=planner_response.assistant_message)
            else:
                assistant = self.conversation_host.reply(route, session, message)
        else:
            assistant = _opening_message()
        self._refresh_controls(session)
        self._update_memory(session, assistant)
        self._append_assistant(session, assistant)
        self.store.save(session)
        if message.strip():
            command = parse_strategy_command(message)
            if command is not None and not command_applied(self._require_session(session.session_id).strategy, command):
                raise RuntimeError("策略修改保存校验失败，请勿执行搜索。")
        return session, assistant

    def send(self, session_id: str, message: str) -> tuple[CopilotSession, str]:
        session = self._require_session(session_id)
        session.messages.append(ChatMessage(role="user", content=message.strip(), created_at=now_iso()))
        route = self.conversation_router.route(message, session)
        session.last_user_intent = route.intent
        command = parse_strategy_command(message)
        if command is not None:
            if command.operation == "show":
                assistant = _current_strategy_summary(session.strategy)
            else:
                before = session.strategy.model_copy(deep=True)
                session.strategy = apply_strategy_command(session.strategy, command, raw_message=message)
                session.detected_conflicts = []
                session.recent_strategy_changes = _strategy_changes(before, session.strategy)
                session.selected_skill = self.skill_selector.select(text=message, strategy=session.strategy)
                session.preview = None
                if session.state == CopilotState.CHANNEL_CHECK_FAILED:
                    session.state = CopilotState.COLLECTING_REQUIREMENTS
                self._refresh_controls(session)
                assistant = self._command_response(session, command)
            self._refresh_controls(session)
            self._append_assistant(session, assistant)
            self._update_memory(session, assistant)
            self._touch(session)
            self.store.save(session)
            persisted = self._require_session(session_id)
            if not command_applied(persisted.strategy, command):
                raise RuntimeError("策略修改保存校验失败，请勿执行搜索。")
            logger.info(
                "hunt_strategy_command session=%s operation=%s field=%s values=%s version=%s verified=true",
                session_id,
                command.operation,
                command.field,
                list(command.values),
                persisted.strategy.strategy_version,
            )
            return persisted, assistant
        if route.intent in {"smalltalk", "general_question", "capability_help", "strategy_discussion", "strategy_query", "off_topic"}:
            self._refresh_controls(session)
            assistant = self.conversation_host.reply(route, session, message)
            self._append_assistant(session, assistant)
            self._update_memory(session, assistant)
            self._touch(session)
            self.store.save(session)
            return session, assistant
        if route.action == "confirm_strategy":
            ok, assistant = self._confirm_strategy(session)
            if not ok:
                self._append_assistant(session, assistant)
                self._update_memory(session, assistant)
                self._touch(session)
                self.store.save(session)
                return session, assistant
        elif route.action == "confirm_execution":
            assistant = self.conversation_host.blocked_action(session, action="confirm_execution")
        elif route.action == "check_channels":
            ok, reason = self.validator.can_check_channels(session.strategy)
            assistant = "可以检查通道，请点击右侧“检查通道”按钮。" if ok else reason
        elif route.action == "cancel_session":
            session.state = CopilotState.CANCELLED
            assistant = "已取消当前 Copilot 会话。"
        elif route.action == "restart_session":
            session.strategy = HuntStrategy()
            session.preview = None
            session.channel_status = []
            session.automation_job_id = ""
            session.selected_skill = self.skill_selector.select(strategy=session.strategy)
            session.state = CopilotState.COLLECTING_REQUIREMENTS
            session.recent_strategy_changes = ["已清空当前策略，重新开始。"]
            assistant = "已重新开始。请告诉我这次要找的国家、客户类型、产品关键词和硬条件。"
        else:
            before = session.strategy.model_copy(deep=True)
            planner_response = self.llm_planner.plan(message, session.strategy, session.state.value, **self._planner_context(session))
            session.detected_conflicts = planner_response.detected_conflicts
            session.strategy = self.patch_merger.merge(session.strategy, planner_response.strategy_patch, raw_message=message)
            session.recent_strategy_changes = _strategy_changes(before, session.strategy)
            session.selected_skill = self.skill_selector.select(text=message, strategy=session.strategy)
            if session.state == CopilotState.CHANNEL_CHECK_FAILED:
                session.state = CopilotState.COLLECTING_REQUIREMENTS
            self._refresh_controls(session)
            assistant = self._assistant_for_current_state(session, fallback=planner_response.assistant_message)
        self._refresh_controls(session)
        self._update_memory(session, assistant)
        self._append_assistant(session, assistant)
        self._touch(session)
        self.store.save(session)
        return session, assistant

    def update_strategy(self, session_id: str, strategy: HuntStrategy) -> tuple[CopilotSession, str]:
        session = self._require_session(session_id)
        session.strategy = strategy.model_validate(strategy.model_dump())
        session.detected_conflicts = []
        session.strategy.strategy_version += 1
        session.strategy.strategy_confirmed = False
        session.strategy.needs_recheck = True
        session.preview = None
        session.selected_skill = self.skill_selector.select(strategy=session.strategy)
        if session.state == CopilotState.CHANNEL_CHECK_FAILED:
            session.state = CopilotState.COLLECTING_REQUIREMENTS
        self._refresh_controls(session)
        assistant = self._assistant_for_current_state(session)
        self._append_assistant(session, assistant)
        self._touch(session)
        self.store.save(session)
        return session, assistant

    def confirm_strategy(self, session_id: str) -> tuple[CopilotSession, str]:
        session = self._require_session(session_id)
        _, assistant = self._confirm_strategy(session)
        self._append_assistant(session, assistant)
        self._touch(session)
        self.store.save(session)
        return session, assistant

    def get(self, session_id: str) -> CopilotSession:
        return self._sync_job_state(self._require_session(session_id))

    def list_history(self, *, limit: int = 50) -> list[CopilotHistorySummary]:
        return [self._history_summary(self._sync_job_state(session)) for session in self.store.list_recent(limit=limit)]

    def duplicate_session(self, session_id: str) -> tuple[CopilotSession, str]:
        source = self._require_session(session_id)
        session = CopilotSession(
            session_id=str(uuid.uuid4()),
            state=CopilotState.COLLECTING_REQUIREMENTS,
            strategy=source.strategy.model_copy(deep=True),
            created_at=now_iso(),
            updated_at=now_iso(),
        )
        session.strategy.strategy_confirmed = False
        session.strategy.needs_recheck = True
        session.strategy.strategy_version += 1
        session.selected_skill = self.skill_selector.select(strategy=session.strategy)
        self._refresh_controls(session)
        assistant = "已复制历史策略。请检查右侧策略卡，确认后再检查通道和执行。"
        self._append_assistant(session, assistant)
        self.store.save(session)
        return session, assistant

    def check_channels(self, session_id: str) -> tuple[CopilotSession, str]:
        session = self._require_session(session_id)
        ok, reason = self.validator.can_check_channels(session.strategy)
        if not ok:
            raise ValueError(reason)
        session.state = CopilotState.CHECKING_CHANNELS
        session.channel_status = self._channel_status()
        missing = [item.channel for item in session.channel_status if not item.configured and item.enabled]
        if missing:
            session.state = CopilotState.CHANNEL_CHECK_FAILED
            assistant = "通道健康检查未通过：" + "、".join(missing) + " 缺少配置。请先在配置中心补齐密钥，再回来执行。"
        else:
            session.state = CopilotState.PREVIEW_COMPLETED
            session.tool_plan = build_tool_plan(session.strategy)
            session.tool_execution_preview = self.tool_executor.preview_plan(session.tool_plan)
            session.preview = self._build_preview(session.strategy)
            session.strategy.needs_recheck = False
            assistant = "通道健康检查通过。我已经生成小样本预检计划，请确认后再正式执行。"
        self._refresh_controls(session)
        self._append_assistant(session, assistant)
        self._touch(session)
        self.store.save(session)
        return session, assistant

    def confirm_execution(self, session_id: str, request: ConfirmExecutionRequest) -> tuple[CopilotSession, dict[str, Any]]:
        session = self._require_session(session_id)
        current_hash = strategy_fingerprint(session.strategy)
        if request.expected_strategy_version is not None and request.expected_strategy_version != session.strategy.strategy_version:
            raise ValueError("策略版本已变化，请刷新页面并重新检查通道后再执行。")
        if request.expected_strategy_hash and request.expected_strategy_hash != current_hash:
            raise ValueError("策略内容已变化，请刷新页面并重新检查通道后再执行。")
        ok, reason = self.validator.can_execute(session.strategy, preview_ready=session.preview is not None, automation_job_id=session.automation_job_id)
        if not ok:
            raise ValueError(reason)
        payload = self._hunt_payload(session.strategy, request)
        queue = HuntJobQueue(self.settings.automation_queue_db_path)
        queue.init_db()
        job_id = queue.enqueue(payload, now_iso=now_iso())
        job = queue.get(job_id) or {"id": job_id, "payload": payload, "status": "queued"}
        job["job_id"] = str(job.get("id") or job_id)
        session.automation_job_id = job_id
        session.state = CopilotState.RUNNING_FULL_SEARCH
        session.strategy.rules.allow_execution = True
        self._append_assistant(session, f"正式 Hunt 已创建，任务编号：{job_id}。系统会先进入 candidate_pool 合并证据，再筛选入库。")
        self._touch(session)
        self.store.save(session)
        return session, job

    def _confirm_strategy(self, session: CopilotSession) -> tuple[bool, str]:
        self._refresh_controls(session)
        validation = self.validator.validate(session.strategy)
        if not validation.can_confirm_strategy:
            parts = []
            if validation.missing_fields:
                parts.append("还缺少：" + "、".join(validation.missing_fields))
            if validation.detected_conflicts:
                parts.append("存在冲突：" + "；".join(validation.detected_conflicts))
            if validation.blocking_errors:
                parts.append("阻断项：" + "；".join(validation.blocking_errors))
            assistant = "策略卡还不能确认。" + " ".join(parts)
            self._refresh_controls(session)
            return False, assistant
        session.strategy.strategy_confirmed = True
        session.strategy.needs_recheck = True
        session.preview = None
        session.state = CopilotState.WAITING_STRATEGY_CONFIRMATION
        self._refresh_controls(session)
        return True, _confirmed_summary(session.strategy)

    def _assistant_for_current_state(self, session: CopilotSession, *, fallback: str = "") -> str:
        validation = self.validator.validate(session.strategy)
        return self.response_builder.build(session, validation, fallback=fallback)

    def _command_response(self, session: CopilotSession, command) -> str:
        values = "、".join(command.values)
        labels = {"keep_only": "仅保留", "replace": "已替换为", "remove": "已移除", "add": "已增加"}
        return f"目标地区{labels.get(command.operation, '已更新')}：{values}。\n\n" + _current_strategy_summary(session.strategy)

    def _planner_context(self, session: CopilotSession) -> dict[str, Any]:
        return {
            "recent_messages": [item.model_dump(mode="json") for item in session.messages[-8:]],
            "conversation_summary": session.conversation_summary,
            "last_user_intent": session.last_user_intent,
            "last_ai_action": session.last_ai_action,
            "clarification_focus": session.clarification_focus,
        }

    def _refresh_controls(self, session: CopilotSession) -> None:
        validation = self.validator.validate(session.strategy)
        session.missing_fields = validation.missing_fields
        session.detected_conflicts = list(dict.fromkeys([*session.detected_conflicts, *validation.detected_conflicts, *validation.blocking_errors, *validation.warnings]))
        if session.state not in {CopilotState.CHANNEL_CHECK_FAILED, CopilotState.CHECKING_CHANNELS}:
            session.state = choose_state(session, validation)
        session.allowed_actions = allowed_actions(session, validation)
        session.strategy_version = session.strategy.strategy_version
        session.needs_recheck = session.strategy.needs_recheck
        session.strategy_hash = strategy_fingerprint(session.strategy)
        session.similar_history = [item.model_dump(mode="json") for item in self._similar_history(session)]
        session.suggested_replies = suggested_replies(session, validation)
        if session.selected_skill is None:
            session.selected_skill = self.skill_selector.select(strategy=session.strategy)
        session.critic_notes = self.critic.review(session.strategy, validation, session.selected_skill)
        if validation.can_confirm_strategy:
            session.tool_plan = build_tool_plan(session.strategy)
            session.tool_execution_preview = self.tool_executor.preview_plan(session.tool_plan)

    def _update_memory(self, session: CopilotSession, assistant: str) -> None:
        validation = self.validator.validate(session.strategy)
        session.clarification_focus = validation.missing_fields[0] if validation.missing_fields else ""
        session.last_ai_action = _last_ai_action(session, assistant)
        session.conversation_summary = _conversation_summary(session)

    def _similar_history(self, session: CopilotSession) -> list[CopilotHistorySummary]:
        matches: list[CopilotHistorySummary] = []
        for other in self.store.list_recent(limit=80):
            if other.session_id == session.session_id:
                continue
            score = strategy_similarity(session.strategy, other.strategy)
            if score < 0.55:
                continue
            summary = self._history_summary(other)
            summary.similarity = score
            matches.append(summary)
        matches.sort(key=lambda item: (item.similarity, item.updated_at), reverse=True)
        return matches[:5]

    def _channel_status(self) -> list[ChannelStatus]:
        return [
            ChannelStatus(
                channel=item.capability.name,
                enabled=True,
                configured=item.configured,
                status=item.status,
                message=item.message,
            )
            for item in list_tool_status(self.settings)
        ]

    def _build_preview(self, strategy: HuntStrategy) -> PreviewSummary:
        keywords = max(1, len(strategy.product_keywords) or 1)
        regions = max(1, len(strategy.target_regions) or 1)
        customer_types = max(1, len(strategy.customer_types) or 1)
        estimated_queries = min(80, keywords * regions * customer_types * 4)
        warnings = []
        if strategy.hard_filters.require_instagram:
            warnings.append("Instagram 是硬条件，Apify Token 未配置时会阻断执行。")
        if strategy.hard_filters.require_email or strategy.hard_filters.require_phone:
            warnings.append("邮箱/电话需要官网、地图和公开页面补全，预检通过后仍会做硬过滤。")
        return PreviewSummary(
            status="ready",
            estimated_queries=estimated_queries,
            expected_candidate_pool=strategy.budget.max_candidates,
            expected_final_leads=strategy.budget.final_leads,
            required_fields=strategy.hard_filters.enabled_labels(),
            channel_breakdown={
                "web": "Tavily 发现官网、目录和公开网页",
                "google_maps": "Serper/Maps 补充地址、电话、官网",
                "instagram": "Apify Instagram 查找公开账号和 bio 外链",
                "facebook": "Apify Facebook 查找公开 Page 和联系方式",
            },
            warnings=warnings,
        )

    def _hunt_payload(self, strategy: HuntStrategy, request: ConfirmExecutionRequest) -> dict[str, Any]:
        description_parts = [strategy.raw_requirement.strip(), render_strategy_card(strategy)]
        return {
            "website_url": "",
            "description": "\n\n".join(part for part in description_parts if part),
            "product_keywords": strategy.product_keywords,
            "target_customer_profile": ", ".join(strategy.customer_types),
            "target_regions": strategy.target_regions,
            "uploaded_file_ids": [],
            "target_lead_count": strategy.budget.final_leads,
            "max_rounds": 3,
            "min_new_leads_threshold": 1,
            "search_sources": strategy.search_sources,
            "tool_plan": (build_tool_plan(strategy).model_dump(mode="json")),
            "search_budget": {
                "preview_total_usd": strategy.budget.preview_total_usd,
                "total_usd": strategy.budget.total_usd,
                "apify_actor_max_items": strategy.budget.apify_actor_max_items,
                "apify_actor_max_total_charge_usd": strategy.budget.apify_actor_max_total_charge_usd,
                "apify_task_max_total_charge_usd": strategy.budget.apify_task_max_total_charge_usd,
                "max_candidates": strategy.budget.max_candidates,
                "final_leads": strategy.budget.final_leads,
                "hard_filters": strategy.hard_filters.model_dump(),
                "target_regions": strategy.target_regions,
                "customer_types": strategy.customer_types,
                "product_keywords": strategy.product_keywords,
                "exclusions": strategy.exclusions,
                "candidate_pool_enabled": strategy.rules.candidate_pool_enabled,
                "merge_multi_source_evidence": strategy.rules.merge_multi_source_evidence,
                "missing_required_action": strategy.rules.missing_required_action,
            },
            "enable_email_craft": request.enable_email_craft,
            "email_template_examples": request.email_template_examples,
            "email_template_notes": request.email_template_notes,
        }

    def _history_summary(self, session: CopilotSession) -> CopilotHistorySummary:
        job_id = session.automation_job_id
        job_status = ""
        result_count = 0
        candidate_count = 0
        instagram_count = 0
        email_count = 0
        phone_count = 0
        if job_id:
            queue = HuntJobQueue(self.settings.automation_queue_db_path)
            queue.init_db()
            job = queue.get(job_id) or {}
            job_status = str(job.get("status", "") or "")
            hunt_id = str(job.get("last_hunt_id", "") or "")
            hunt = load_hunt(hunt_id) if hunt_id else None
            result = (hunt or {}).get("result") if isinstance((hunt or {}).get("result"), dict) else {}
            candidates = result.get("candidate_pool") if isinstance(result.get("candidate_pool"), list) else []
            leads = result.get("leads") if isinstance(result.get("leads"), list) else []
            result_count = len(leads)
            candidate_count = len(candidates)
            instagram_count = _count_present(candidates, "instagram_url")
            email_count = _count_present(candidates, "email") + sum(1 for lead in leads if lead.get("emails"))
            phone_count = _count_present(candidates, "phone") + sum(1 for lead in leads if lead.get("phone_numbers"))
        return CopilotHistorySummary(
            session_id=session.session_id,
            created_at=session.created_at,
            updated_at=session.updated_at,
            state=session.state.value if hasattr(session.state, "value") else str(session.state),
            target_regions=session.strategy.target_regions,
            customer_types=session.strategy.customer_types,
            product_keywords=session.strategy.product_keywords,
            required_fields=session.strategy.hard_filters.enabled_labels(),
            max_candidates=session.strategy.budget.max_candidates,
            final_leads=session.strategy.budget.final_leads,
            job_id=job_id,
            job_status=job_status,
            result_count=result_count,
            candidate_count=candidate_count,
            instagram_count=instagram_count,
            email_count=email_count,
            phone_count=phone_count,
            strategy_hash=strategy_fingerprint(session.strategy),
        )

    def _sync_job_state(self, session: CopilotSession) -> CopilotSession:
        if not session.automation_job_id or session.state not in {CopilotState.RUNNING_FULL_SEARCH, CopilotState.FAILED}:
            return session
        queue = HuntJobQueue(self.settings.automation_queue_db_path)
        queue.init_db()
        job = queue.get(session.automation_job_id) or {}
        status = str(job.get("status") or "").strip().lower()
        next_state = None
        if status in {"completed", "complete", "succeeded", "success", "done"}:
            next_state = CopilotState.COMPLETED
        elif status in {"failed", "error", "dead", "cancelled", "canceled"}:
            next_state = CopilotState.FAILED
        if next_state and session.state != next_state:
            session.state = next_state
            self._touch(session)
            self.store.save(session)
        return session

    def _require_session(self, session_id: str) -> CopilotSession:
        session = self.store.get(session_id)
        if session is None:
            raise KeyError("Hunt Copilot session not found")
        return session

    def _append_assistant(self, session: CopilotSession, content: str) -> None:
        session.messages.append(ChatMessage(role="assistant", content=content, created_at=now_iso()))

    def _touch(self, session: CopilotSession) -> None:
        session.updated_at = now_iso()


def _count_present(items: list[Any], key: str) -> int:
    count = 0
    for item in items:
        if isinstance(item, dict) and str(item.get(key, "") or "").strip():
            count += 1
    return count


def _strategy_changes(before: HuntStrategy, after: HuntStrategy) -> list[str]:
    changes: list[str] = []
    for field, label in (
        ("target_regions", "目标地区"),
        ("customer_types", "目标客户"),
        ("product_keywords", "产品关键词"),
        ("exclusions", "排除对象"),
    ):
        if getattr(before, field) != getattr(after, field):
            changes.append(f"{label}：{_join_values(getattr(after, field)) or '已清空'}")
    if before.hard_filters != after.hard_filters:
        changes.append(f"硬条件：{_join_values(after.hard_filters.enabled_labels()) or '未设置'}")
    if before.budget != after.budget:
        changes.append(f"数量预算：候选 {after.budget.max_candidates}，最终 {after.budget.final_leads}，预算 {after.budget.total_usd:g} USD")
    return changes[:8]


def _join_values(values: list[str]) -> str:
    return "、".join(str(item) for item in values if str(item).strip())


def _last_ai_action(session: CopilotSession, assistant: str) -> str:
    if session.state == CopilotState.STRATEGY_READY:
        return "showed_strategy_ready"
    if "还需要确认" in assistant or session.clarification_focus:
        return f"asked_{session.clarification_focus or 'missing_field'}"
    if session.state == CopilotState.WAITING_STRATEGY_CONFIRMATION:
        return "confirmed_strategy"
    if session.state == CopilotState.PREVIEW_COMPLETED:
        return "prepared_preview"
    return "answered"


def _conversation_summary(session: CopilotSession) -> str:
    strategy = session.strategy
    parts: list[str] = []
    if strategy.target_regions:
        parts.append("地区 " + _join_values(strategy.target_regions))
    if strategy.customer_types:
        parts.append("客户 " + _join_values(strategy.customer_types))
    if strategy.product_keywords:
        parts.append("产品 " + _join_values(strategy.product_keywords[:4]))
    if strategy.exclusions:
        parts.append("排除 " + _join_values(strategy.exclusions))
    required = strategy.hard_filters.enabled_labels()
    if required:
        parts.append("硬条件 " + _join_values(required))
    if session.clarification_focus:
        parts.append("当前追问 " + session.clarification_focus)
    return "；".join(parts)[:600]


def _opening_message() -> str:
    return "你好，我可以帮你创建客户搜索任务。先告诉我目标地区、客户类型、JPS 产品关键词和排除对象；确认前不会调用搜索 API。"


def _confirmed_summary(strategy: HuntStrategy) -> str:
    required = "、".join(strategy.hard_filters.enabled_labels()) or "未设置"
    return (
        "好的，策略卡已确认："
        f"目标地区 {', '.join(strategy.target_regions)}；"
        f"目标客户 {', '.join(strategy.customer_types)}；"
        f"排除 {', '.join(strategy.exclusions) or '无'}；"
        f"产品关键词 {', '.join(strategy.product_keywords)}；"
        f"硬条件 {required}。下一步请点击通道检查，通过后再决定是否正式执行。"
    )


def _current_strategy_summary(strategy: HuntStrategy) -> str:
    return (
        "当前策略卡（仅展示，未修改）："
        f"目标地区 {_join_values(strategy.target_regions) or '未设置'}；"
        f"目标客户 {_join_values(strategy.customer_types) or '未设置'}；"
        f"产品关键词 {_join_values(strategy.product_keywords) or '未设置'}；"
        f"排除对象 {_join_values(strategy.exclusions) or '无'}；"
        f"硬条件 {_join_values(strategy.hard_filters.enabled_labels()) or '未设置'}。"
    )
