"""Route user messages before strategy planning.

The router keeps casual chat and help questions out of the strategy-card
pipeline. High-confidence cases are handled by deterministic rules; ambiguous
messages can be classified by the configured LLM and safely fall back to rules.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import re

from config.settings import Settings, get_settings
from hunt_copilot.schemas import ConversationRoute, CopilotSession
from tools.llm_client import LLMTool
from tools.llm_output import parse_json

logger = logging.getLogger(__name__)


PLANNER_INTENTS = {"search_requirement", "strategy_patch"}
CONFIRM_WORDS = {"确认", "确认策略", "可以", "可以的", "ok", "yes", "同意", "就这样", "没问题"}
SMALLTALK_WORDS = {"hi", "hello", "hey", "你好", "您好", "在吗", "开始", "start"}
CAPABILITY_PATTERNS = ("你能做什么", "能做什么", "怎么用", "如何使用", "帮我什么", "help", "能力", "功能")
EXECUTION_PATTERNS = ("开始搜索", "正式执行", "执行搜索", "开始执行", "启动搜索", "run search")
SEARCH_MARKERS = (
    "客户", "经销商", "学校", "医院", "诊所", "进口商", "分销", "代理", "采购", "目标", "排除",
    "instagram", "facebook", "邮箱", "电话", "官网", "地址", "候选", "最终", "预算", "产品", "关键词",
    "customer", "distributor", "dealer", "school", "hospital", "importer", "supplier", "lead", "candidate", "budget",
)


class ConversationRouter:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def route(self, message: str, session: CopilotSession) -> ConversationRoute:
        text = str(message or "").strip()
        rule = self._rule_route(text, session)
        if self._should_use_rule_route(rule) or not self._enabled():
            return rule
        try:
            ai_route = _run_coro_with_timeout(
                self._route_async(text, session),
                timeout_seconds=max(1, int(self.settings.hunt_copilot_router_timeout_seconds) + 1),
            )
            return ai_route if ai_route.confidence >= 0.55 else rule
        except TimeoutError:
            logger.warning("Hunt Copilot route classification timed out; using fallback route")
            return rule
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("Hunt Copilot route classification failed; using fallback: %s", exc)
            return rule

    async def _route_async(self, message: str, session: CopilotSession) -> ConversationRoute:
        model = self.settings.hunt_copilot_model.strip()
        llm_settings = self.settings.model_copy(update={"llm_model": model}) if model else self.settings
        llm = LLMTool(settings=llm_settings, agent="hunt_copilot_router")
        prompt = json.dumps(
            {
                "task": "Classify this user message before Hunt strategy planning. Return JSON only.",
                "current_state": session.state.value if hasattr(session.state, "value") else str(session.state),
                "current_strategy": session.strategy.model_dump(),
                "conversation_summary": session.conversation_summary,
                "last_user_intent": session.last_user_intent,
                "clarification_focus": session.clarification_focus,
                "recent_messages": [item.model_dump() for item in session.messages[-8:]],
                "user_message": message,
                "intents": [
                    "smalltalk", "general_question", "capability_help", "strategy_discussion",
                "search_requirement", "strategy_patch", "strategy_confirmation", "channel_check_request", "execution_confirmation",
                    "restart_session", "cancel_session", "off_topic",
                ],
                "rules": [
                    "Only search_requirement or strategy_patch may update the strategy.",
                    "General questions and smalltalk must not update strategy.",
                    "If the user says confirm, classify as strategy_confirmation unless execution is explicitly mentioned.",
                    "Execution confirmation does not execute directly; backend gates decide.",
                ],
                "response_schema": {
                    "intent": "one intent string",
                    "should_call_planner": False,
                    "should_update_strategy": False,
                    "should_run_action": False,
                    "action": "confirm_strategy | confirm_execution | restart_session | cancel_session |",
                    "confidence": 0.0,
                    "reason": "short reason",
                    "assistant_message": "optional natural reply for non-planning intents",
                },
            },
            ensure_ascii=False,
        )
        response_format = None if "minimax" in llm_settings.llm_model.lower() else {"type": "json_object"}
        raw = await asyncio.wait_for(
            llm.generate(
                prompt,
                system="You are a safe routing layer. Return JSON only. Never execute tools.",
                temperature=0.0,
                max_tokens=700,
                response_format=response_format,
                timeout_seconds=max(1, int(self.settings.hunt_copilot_router_timeout_seconds)),
            ),
            timeout=max(1, int(self.settings.hunt_copilot_router_timeout_seconds)),
        )
        data = parse_json(raw, context="ConversationRouter")
        if not isinstance(data, dict):
            raise ValueError("router returned non-JSON response")
        route = ConversationRoute.model_validate(data)
        if route.intent in PLANNER_INTENTS:
            route.should_call_planner = True
            route.should_update_strategy = True
        else:
            route.should_call_planner = False
            route.should_update_strategy = False
        return route

    def _enabled(self) -> bool:
        if not self.settings.hunt_copilot_llm_enabled:
            return False
        return bool(
            self.settings.minimax_api_key
            or self.settings.openai_api_key
            or self.settings.openrouter_api_key
            or self.settings.anthropic_api_key
            or self.settings.groq_api_key
            or self.settings.zai_api_key
            or self.settings.moonshot_api_key
        )

    def _should_use_rule_route(self, route: ConversationRoute) -> bool:
        if route.confidence >= 0.9:
            return True
        return route.intent in PLANNER_INTENTS and route.confidence >= 0.75

    def _rule_route(self, text: str, session: CopilotSession) -> ConversationRoute:
        lower = text.lower().strip()
        if not lower:
            return _route("smalltalk", False, False, confidence=1.0, reason="empty message")
        if lower in SMALLTALK_WORDS:
            return _route("smalltalk", False, False, confidence=1.0, reason="simple greeting")
        if lower in CONFIRM_WORDS:
            return _route("strategy_confirmation", False, False, action="confirm_strategy", confidence=1.0, reason="explicit confirmation")
        if any(pattern in lower for pattern in ("取消", "cancel")):
            return _route("cancel_session", False, False, action="cancel_session", confidence=1.0, reason="cancel request")
        if any(pattern in lower for pattern in ("重新开始", "重开", "restart")):
            return _route("restart_session", False, False, action="restart_session", confidence=1.0, reason="restart request")
        if any(pattern in lower for pattern in EXECUTION_PATTERNS):
            return _route("execution_confirmation", False, False, action="confirm_execution", confidence=0.95, reason="execution request")
        if "通道" in lower or "检查" in lower:
            return _route("channel_check_request", False, False, action="check_channels", confidence=0.9, reason="channel check request")
        if any(pattern in lower for pattern in CAPABILITY_PATTERNS):
            return _route("capability_help", False, False, confidence=0.95, reason="capability/help question")
        if _math_question(lower):
            return _route("general_question", False, False, confidence=0.95, reason="simple math/general question")
        if _strategy_discussion(lower):
            return _route("strategy_discussion", False, False, confidence=0.9, reason="strategy discussion without explicit patch")
        if _initial_search_requirement(lower):
            return _route("search_requirement", True, True, confidence=0.9, reason="initial search requirement")
        if _strategy_patch(lower, session):
            return _route("strategy_patch", True, True, confidence=0.85, reason="strategy field update")
        if any(marker in lower for marker in SEARCH_MARKERS):
            return _route("search_requirement", True, True, confidence=0.75, reason="search requirement markers")
        if lower.endswith("?") or lower.endswith("？"):
            return _route("general_question", False, False, confidence=0.75, reason="question without search markers")
        return _route("search_requirement", True, True, confidence=0.45, reason="ambiguous fallback")


def _route(intent: str, should_call_planner: bool, should_update_strategy: bool, *, action: str = "", confidence: float = 0.0, reason: str = "") -> ConversationRoute:
    return ConversationRoute(
        intent=intent,
        should_call_planner=should_call_planner,
        should_update_strategy=should_update_strategy,
        should_run_action=bool(action),
        action=action,
        confidence=confidence,
        reason=reason,
    )


def _run_coro_with_timeout(coro, *, timeout_seconds: int):
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="hunt-copilot-router")
    future = executor.submit(asyncio.run, coro)
    try:
        return future.result(timeout=max(1, timeout_seconds))
    except concurrent.futures.TimeoutError as exc:
        future.cancel()
        raise TimeoutError from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _math_question(text: str) -> bool:
    if "=" in text or "几" in text or "多少" in text:
        return bool(re.search(r"\d+\s*[+\-*/x×÷]\s*\d+", text))
    return False


def _strategy_discussion(text: str) -> bool:
    markers = ("够不够", "难不难", "会不会", "合理吗", "怎么看", "建议", "为什么", "效果", "太少", "太多")
    return any(marker in text for marker in markers) and any(marker in text for marker in SEARCH_MARKERS)


def _strategy_patch(text: str, session: CopilotSession) -> bool:
    patch_markers = ("改成", "设置", "只要", "只用", "只保留", "必须", "硬条件", "候选", "最终", "预算", "排除", "不要")
    if any(marker in text for marker in patch_markers):
        return True
    if session.clarification_focus:
        return True
    return False


def _initial_search_requirement(text: str) -> bool:
    starters = ("我要找", "我需要", "寻找", "帮我找", "找 ", "找")
    customer_markers = ("客户", "经销商", "学校", "医院", "进口商", "分销", "customer", "distributor", "school", "hospital")
    return any(starter in text for starter in starters) and any(marker in text for marker in customer_markers)
