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
from hunt_copilot.strategy_renderer import render_strategy_card
from hunt_copilot.strategy_fingerprint import strategy_fingerprint, strategy_similarity
from hunt_copilot.strategy_critic import StrategyCritic
from hunt_copilot.strategy_commands import (
    FIELD_LABELS,
    CommandApplication,
    StrategyCommand,
    apply_strategy_command,
    business_fields_equal,
    command_applied,
    parse_strategy_command,
)
from hunt_copilot.validator import StrategyValidator
from hunt_copilot_ai import CopilotAIOrchestrator
from product_knowledge.taxonomy import CATEGORY_LABELS, DEPARTMENT_LABELS, UNCLEAR, direction_summary
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
        self.validator = StrategyValidator(self.settings)
        self.skill_selector = SearchSkillSelector()
        self.critic = StrategyCritic(self.settings)
        self.response_builder = CopilotResponseBuilder()
        self.tool_executor = ToolExecutor(self.settings)
        self.ai_orchestrator = CopilotAIOrchestrator(self.settings)

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
            self._touch(session)
            self.store.save(session)
            if command is not None:
                return self._execute_command(session, command, message)
            if route.should_call_planner and route.should_update_strategy:
                return self._execute_planner_change(session, message)
            assistant = self.conversation_host.reply(route, session, message)
        else:
            assistant = _opening_message()
        return self._finalize_non_mutating(session, assistant)

    def send(self, session_id: str, message: str) -> tuple[CopilotSession, str]:
        session = self._require_session(session_id)
        session.messages.append(ChatMessage(role="user", content=message.strip(), created_at=now_iso()))
        route = self.conversation_router.route(message, session)
        session.last_user_intent = route.intent
        command = parse_strategy_command(message)
        if command is not None:
            return self._execute_command(session, command, message)
        if route.intent in {"smalltalk", "general_question", "capability_help", "strategy_discussion", "strategy_query", "off_topic"}:
            assistant = self.conversation_host.reply(route, session, message)
            return self._finalize_non_mutating(session, assistant)
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
            return self._execute_planner_change(session, message)
        self._refresh_controls(session)
        self._update_memory(session, assistant)
        self._append_assistant(session, assistant)
        self._touch(session)
        self.store.save(session)
        return session, assistant

    def _execute_command(self, session: CopilotSession, command: StrategyCommand, raw_message: str) -> tuple[CopilotSession, str]:
        if command.operation == "query":
            return self._finalize_non_mutating(session, _current_strategy_summary(session.strategy))
        if command.operation == "clarify":
            return self._finalize_non_mutating(session, command.clarification or "请明确要修改哪个策略字段。")
        if command.operation == "undo":
            return self._undo_last_change(session)

        before = session.strategy.model_copy(deep=True)
        application = apply_strategy_command(before, command, raw_message=raw_message)
        if not application.changed:
            assistant = self._command_no_change_response(before, command, application)
            return self._finalize_non_mutating(session, assistant)

        self._push_snapshot(session, before, raw_message)
        session.strategy = application.strategy
        self._sync_strategy_uncertainty(session.strategy)
        session.detected_conflicts = []
        session.recent_strategy_changes = _strategy_changes(before, session.strategy)
        session.selected_skill = self.skill_selector.select(text=raw_message, strategy=session.strategy)
        session.preview = None
        if session.state == CopilotState.CHANNEL_CHECK_FAILED:
            session.state = CopilotState.COLLECTING_REQUIREMENTS
        self._refresh_controls(session)
        self._touch(session)
        self.store.save(session)

        persisted = self._verified_session(session.session_id, application.strategy)
        assistant = self._command_response(before, persisted.strategy, command, application)
        self._append_assistant(persisted, assistant)
        self._update_memory(persisted, assistant)
        self._touch(persisted)
        self.store.save(persisted)
        verified = self._require_session(session.session_id)
        logger.info(
            "hunt_strategy_command session=%s command=%s version=%s verified=true",
            session.session_id,
            command.as_dict(),
            verified.strategy.strategy_version,
        )
        return verified, assistant

    def _execute_planner_change(self, session: CopilotSession, message: str) -> tuple[CopilotSession, str]:
        before = session.strategy.model_copy(deep=True)
        result = self.ai_orchestrator.handle_message(
            message,
            before,
            state=session.state.value,
            **self._planner_context(session),
        )
        expected = result.strategy
        changed = result.changed or not business_fields_equal(before, expected)
        if changed:
            self._push_snapshot(session, before, message)
        session.strategy = expected
        self._sync_strategy_uncertainty(session.strategy)
        session.detected_conflicts = result.detected_conflicts
        session.recent_strategy_changes = result.recent_strategy_changes or _strategy_changes(before, expected)
        session.selected_skill = self.skill_selector.select(text=message, strategy=expected)
        session.preview = None if changed else session.preview
        if changed and session.state == CopilotState.CHANNEL_CHECK_FAILED:
            session.state = CopilotState.COLLECTING_REQUIREMENTS
        self._refresh_controls(session)
        self._touch(session)
        self.store.save(session)

        persisted = self._verified_session(session.session_id, expected)
        assistant = result.assistant_message or self._assistant_for_current_state(persisted)
        self._append_assistant(persisted, assistant)
        self._update_memory(persisted, assistant)
        self._touch(persisted)
        self.store.save(persisted)
        return self._require_session(session.session_id), assistant

    def _undo_last_change(self, session: CopilotSession) -> tuple[CopilotSession, str]:
        if not session.strategy_snapshots:
            return self._finalize_non_mutating(session, "没有可撤销的策略修改，本次未修改策略。")
        before = session.strategy.model_copy(deep=True)
        snapshot = session.strategy_snapshots.pop()
        restored = HuntStrategy.model_validate(snapshot.get("strategy") or {})
        if business_fields_equal(before, restored):
            return self._finalize_non_mutating(session, "上一份策略快照与当前策略相同，本次未修改策略。")
        restored.strategy_version = before.strategy_version + 1
        restored.strategy_confirmed = False
        restored.needs_recheck = True
        session.strategy = restored
        self._sync_strategy_uncertainty(session.strategy)
        session.preview = None
        session.detected_conflicts = []
        session.recent_strategy_changes = _strategy_changes(before, restored)
        session.selected_skill = self.skill_selector.select(strategy=restored)
        self._refresh_controls(session)
        self._touch(session)
        self.store.save(session)
        persisted = self._verified_session(session.session_id, restored)
        assistant = "已撤销刚才的修改。" + _verified_change_summary(before, persisted.strategy)
        self._append_assistant(persisted, assistant)
        self._update_memory(persisted, assistant)
        self._touch(persisted)
        self.store.save(persisted)
        return self._require_session(session.session_id), assistant

    def _push_snapshot(self, session: CopilotSession, strategy: HuntStrategy, reason: str) -> None:
        session.strategy_snapshots.append(
            {"strategy": strategy.model_dump(mode="json"), "reason": reason.strip(), "created_at": now_iso()}
        )
        session.strategy_snapshots = session.strategy_snapshots[-20:]

    def _verified_session(self, session_id: str, expected: HuntStrategy) -> CopilotSession:
        persisted = self._require_session(session_id)
        if not command_applied(persisted.strategy, expected):
            raise RuntimeError("策略修改保存校验失败，请勿执行搜索。")
        return persisted

    def _finalize_non_mutating(self, session: CopilotSession, assistant: str) -> tuple[CopilotSession, str]:
        before = session.strategy.model_dump(mode="json")
        self._refresh_controls(session)
        self._append_assistant(session, assistant)
        self._update_memory(session, assistant)
        self._touch(session)
        self.store.save(session)
        persisted = self._require_session(session.session_id)
        if persisted.strategy.model_dump(mode="json") != before:
            raise RuntimeError("只读消息意外修改了策略，请勿执行搜索。")
        return persisted, assistant

    def update_strategy(self, session_id: str, strategy: HuntStrategy) -> tuple[CopilotSession, str]:
        session = self._require_session(session_id)
        before = session.strategy.model_copy(deep=True)
        updated = strategy.model_copy(deep=True)
        if business_fields_equal(before, updated):
            return self._finalize_non_mutating(session, "策略卡内容没有变化，本次未修改策略。")
        updated.strategy_version = before.strategy_version + 1
        updated.strategy_confirmed = False
        updated.needs_recheck = True
        self._push_snapshot(session, before, "手动编辑策略卡")
        session.strategy = HuntStrategy.model_validate(updated.model_dump())
        self._sync_strategy_uncertainty(session.strategy)
        session.detected_conflicts = []
        session.preview = None
        session.selected_skill = self.skill_selector.select(strategy=session.strategy)
        if session.state == CopilotState.CHANNEL_CHECK_FAILED:
            session.state = CopilotState.COLLECTING_REQUIREMENTS
        self._refresh_controls(session)
        self._touch(session)
        self.store.save(session)
        persisted = self._verified_session(session_id, session.strategy)
        assistant = _verified_change_summary(before, persisted.strategy)
        self._append_assistant(persisted, assistant)
        self._update_memory(persisted, assistant)
        self._touch(persisted)
        self.store.save(persisted)
        return self._require_session(session_id), assistant

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
        self._sync_strategy_uncertainty(session.strategy)
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

    def _command_response(
        self,
        before: HuntStrategy,
        after: HuntStrategy,
        command: StrategyCommand,
        application: CommandApplication,
    ) -> str:
        field_label = FIELD_LABELS.get(command.field, command.field)
        action = {
            "add": "增加",
            "remove": "删除",
            "replace": "替换",
            "keep_only": "仅保留",
            "clear": "清空",
        }.get(command.operation, "更新")
        values = _join_values(list(command.values))
        if command.operation == "remove" and application.removed:
            removed = _join_values(application.removed)
            lead = f"已从{field_label}中删除 {removed}（{field_label}已移除：{removed}）。"
        elif command.operation == "keep_only":
            lead = f"{field_label}仅保留：{values}。"
        elif command.operation == "replace":
            lead = f"{field_label}已替换为：{values}。"
        elif command.operation == "add":
            lead = f"{field_label}已增加：{values}。"
        elif command.operation == "clear":
            lead = f"已清空{field_label}。"
        else:
            lead = f"已{action}{field_label}{('：' + values) if values else ''}。"
        response = lead + "\n" + _field_change_line(command.field, application.previous_values, application.current_values)
        if command.field == "product_keywords":
            response += f"\n目标地区未变化：{_join_values(after.target_regions) or '未设置'}。"
        elif command.field == "target_regions":
            response += f"\n产品关键词未变化：{_join_values(after.product_keywords) or '未设置'}。"
        conflicts = self.validator.validate(after).detected_conflicts
        if conflicts:
            response += "\n需要处理冲突：" + "；".join(conflicts) + "。"
        return response + "\n右侧策略卡已按保存后的结果更新。"

    def _command_no_change_response(
        self,
        strategy: HuntStrategy,
        command: StrategyCommand,
        application: CommandApplication,
    ) -> str:
        field_label = FIELD_LABELS.get(command.field, command.field or "指定字段")
        values = _join_values(application.unmatched or list(command.values))
        if command.operation == "remove" and values:
            return f"{field_label}中没有找到 {values}，本次没有修改策略。"
        current = _field_values_for_response(strategy, command.field)
        return f"{field_label}已经是该状态，本次没有修改策略。当前{field_label}：{_join_values(current) or '未设置'}。"

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

    def _sync_strategy_uncertainty(self, strategy: HuntStrategy) -> None:
        validation = self.validator.validate(strategy)
        strategy.uncertain_fields = list(dict.fromkeys(validation.missing_fields))

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
        if strategy.application_scenarios:
            description_parts.append("应用场景：" + ", ".join(strategy.application_scenarios))
        if strategy.business_notes:
            description_parts.append("业务说明：" + "；".join(strategy.business_notes[-5:]))
        return {
            "website_url": "",
            "description": "\n\n".join(part for part in description_parts if part),
            "product_keywords": strategy.product_keywords,
            "product_department": strategy.product_department,
            "product_category": strategy.product_category,
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
                "product_department": strategy.product_department,
                "product_category": strategy.product_category,
                "application_scenarios": strategy.application_scenarios,
                "business_notes": strategy.business_notes,
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
        ("product_department", "业务部门"),
        ("product_category", "产品分类"),
        ("product_keywords", "产品关键词"),
        ("application_scenarios", "应用场景"),
        ("business_notes", "业务说明"),
        ("exclusions", "排除对象"),
    ):
        if getattr(before, field) != getattr(after, field):
            changes.append(f"{label}：{_render_strategy_value(field, getattr(after, field)) or '已清空'}")
    if before.hard_filters != after.hard_filters:
        changes.append(f"硬条件：{_join_values(after.hard_filters.enabled_labels()) or '未设置'}")
    if before.preferred_fields != after.preferred_fields:
        changes.append(f"优先字段：{_join_values(after.preferred_fields) or '未设置'}")
    if before.budget != after.budget:
        changes.append(f"数量预算：候选 {after.budget.max_candidates}，最终 {after.budget.final_leads}，预算 {after.budget.total_usd:g} USD")
    return changes[:8]


def _field_values_for_response(strategy: HuntStrategy, field_name: str) -> list[str]:
    if field_name in {"target_regions", "customer_types", "product_keywords", "application_scenarios", "business_notes", "exclusions", "preferred_fields"}:
        return list(getattr(strategy, field_name))
    if field_name in {"product_department", "product_category"}:
        value = str(getattr(strategy, field_name) or "")
        if field_name == "product_department":
            return [DEPARTMENT_LABELS.get(value, value)]
        return [CATEGORY_LABELS.get(value, value)]
    if field_name == "hard_filters":
        return strategy.hard_filters.enabled_labels()
    if field_name.startswith("budget."):
        return [str(getattr(strategy.budget, field_name.split(".", 1)[1]))]
    return []


def _field_change_line(field_name: str, before: list[str], after: list[str]) -> str:
    label = FIELD_LABELS.get(field_name, field_name)
    return f"{label}：{_join_values(before) or '未设置'} → {_join_values(after) or '已清空'}。"


def _verified_change_summary(before: HuntStrategy, after: HuntStrategy) -> str:
    lines = ["策略已保存并重新读取，实际修改如下："]
    for field_name in ("target_regions", "customer_types", "product_department", "product_category", "product_keywords", "application_scenarios", "business_notes", "exclusions", "hard_filters", "preferred_fields"):
        old_values = _field_values_for_response(before, field_name)
        new_values = _field_values_for_response(after, field_name)
        if old_values != new_values:
            lines.append(_field_change_line(field_name, old_values, new_values))
    for field_name in ("budget.max_candidates", "budget.final_leads", "budget.total_usd"):
        old_values = _field_values_for_response(before, field_name)
        new_values = _field_values_for_response(after, field_name)
        if old_values != new_values:
            lines.append(_field_change_line(field_name, old_values, new_values))
    if len(lines) == 1:
        lines.append("没有业务字段发生变化。")
    return "\n".join(lines)


def _join_values(values: list[str]) -> str:
    return "、".join(str(item) for item in values if str(item).strip())


def _render_strategy_value(field_name: str, value: Any) -> str:
    if field_name == "product_department":
        return DEPARTMENT_LABELS.get(str(value or ""), str(value or ""))
    if field_name == "product_category":
        return CATEGORY_LABELS.get(str(value or ""), str(value or ""))
    if isinstance(value, list):
        return _join_values(value)
    return str(value or "")


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
    direction = _direction_text(strategy)
    if direction:
        parts.append("搜索方向 " + direction)
    if strategy.product_keywords:
        parts.append("产品 " + _join_values(strategy.product_keywords[:4]))
    if strategy.application_scenarios:
        parts.append("应用场景 " + _join_values(strategy.application_scenarios[:3]))
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
    direction = _direction_text(strategy) or "待确认"
    return (
        "好的，策略卡已确认："
        f"目标地区 {', '.join(strategy.target_regions)}；"
        f"目标客户 {', '.join(strategy.customer_types)}；"
        f"搜索方向 {direction}；"
        f"排除 {', '.join(strategy.exclusions) or '无'}；"
        f"产品关键词 {', '.join(strategy.product_keywords)}；"
        f"硬条件 {required}。下一步请点击通道检查，通过后再决定是否正式执行。"
    )


def _current_strategy_summary(strategy: HuntStrategy) -> str:
    return (
        "当前策略卡（仅展示，未修改）："
        f"目标地区 {_join_values(strategy.target_regions) or '未设置'}；"
        f"目标客户 {_join_values(strategy.customer_types) or '未设置'}；"
        f"搜索方向 {_direction_text(strategy) or '未设置'}；"
        f"产品关键词 {_join_values(strategy.product_keywords) or '未设置'}；"
        f"应用场景 {_join_values(strategy.application_scenarios) or '未设置'}；"
        f"排除对象 {_join_values(strategy.exclusions) or '无'}；"
        f"硬条件 {_join_values(strategy.hard_filters.enabled_labels()) or '未设置'}；"
        f"候选数量 {strategy.budget.max_candidates}；"
        f"最终数量 {strategy.budget.final_leads}；"
        f"正式预算 {strategy.budget.total_usd:g} USD。"
    )


def _direction_text(strategy: HuntStrategy) -> str:
    if strategy.product_department == UNCLEAR and strategy.product_category == UNCLEAR:
        return ""
    return direction_summary(strategy.product_department, strategy.product_category)
