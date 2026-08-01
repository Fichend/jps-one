"""MiniMax/LLM-backed planner with deterministic fallback."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging

from config.settings import Settings, get_settings
from hunt_copilot.planner import infer_strategy
from hunt_copilot.planner_prompt import SYSTEM_PROMPT, build_planner_prompt
from hunt_copilot.schemas import HuntStrategy, PlannerResponse
from tools.llm_client import LLMTool
from tools.llm_output import parse_json

logger = logging.getLogger(__name__)


class HuntCopilotLLMPlanner:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def plan(
        self,
        message: str,
        strategy: HuntStrategy,
        state: str,
        *,
        recent_messages: list[dict] | None = None,
        conversation_summary: str = "",
        last_user_intent: str = "",
        last_ai_action: str = "",
        clarification_focus: str = "",
    ) -> PlannerResponse:
        if not self._enabled():
            return self._fallback(message, strategy)
        try:
            return _run_coro_with_timeout(
                self._plan_async(
                    message,
                    strategy,
                    state,
                    recent_messages=recent_messages or [],
                    conversation_summary=conversation_summary,
                    last_user_intent=last_user_intent,
                    last_ai_action=last_ai_action,
                    clarification_focus=clarification_focus,
                ),
                timeout_seconds=max(1, int(self.settings.hunt_copilot_planner_timeout_seconds) + 1),
            )
        except TimeoutError:
            logger.warning("Hunt Copilot LLM planner timed out; using fallback")
            return self._fallback(message, strategy)
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("Hunt Copilot LLM planner failed; using fallback: %s", exc)
            return self._fallback(message, strategy)

    async def _plan_async(
        self,
        message: str,
        strategy: HuntStrategy,
        state: str,
        *,
        recent_messages: list[dict],
        conversation_summary: str,
        last_user_intent: str,
        last_ai_action: str,
        clarification_focus: str,
    ) -> PlannerResponse:
        model = self.settings.hunt_copilot_model.strip()
        llm_settings = self.settings.model_copy(update={"llm_model": model}) if model else self.settings
        llm = LLMTool(settings=llm_settings, agent="hunt_copilot_planner")
        prompt = build_planner_prompt(
            message,
            strategy,
            state,
            recent_messages=recent_messages,
            conversation_summary=conversation_summary,
            last_user_intent=last_user_intent,
            last_ai_action=last_ai_action,
            clarification_focus=clarification_focus,
        )
        response_format = None if "minimax" in llm_settings.llm_model.lower() else {"type": "json_object"}
        raw = await asyncio.wait_for(
            llm.generate(
                prompt,
                system=SYSTEM_PROMPT,
                temperature=0.1,
                max_tokens=1800,
                response_format=response_format,
                timeout_seconds=max(1, int(self.settings.hunt_copilot_planner_timeout_seconds)),
            ),
            timeout=max(1, int(self.settings.hunt_copilot_planner_timeout_seconds)),
        )
        data = parse_json(raw, context="HuntCopilotLLMPlanner")
        if not isinstance(data, dict):
            raise ValueError("LLM planner returned non-JSON response")
        return PlannerResponse.model_validate(data)

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

    def _fallback(self, message: str, strategy: HuntStrategy) -> PlannerResponse:
        inferred = infer_strategy(message, strategy)
        patch = _diff_strategy(strategy, inferred)
        missing = []
        if not inferred.target_regions:
            missing.append("target_regions")
        if not inferred.customer_types:
            missing.append("customer_types")
        if not inferred.product_keywords:
            missing.append("product_keywords")
        intent = _detect_intent(message)
        assistant = "已理解，我已更新策略卡。" if patch else "我理解了，我们继续补齐策略卡。"
        if missing:
            assistant += " 还需要确认：" + "、".join(missing) + "。"
        return PlannerResponse(
            intent=intent,
            assistant_message=assistant,
            strategy_patch=patch,
            missing_fields=missing,
            ready_for_strategy_card=not missing,
            suggested_action="show_strategy_card" if not missing else "continue_collecting",
        )


def _diff_strategy(before: HuntStrategy, after: HuntStrategy) -> dict:
    patch: dict = {}
    for field in ("target_regions", "customer_types", "product_keywords", "exclusions", "raw_requirement"):
        if getattr(before, field) != getattr(after, field):
            patch[field] = getattr(after, field)
    if before.hard_filters != after.hard_filters:
        patch["hard_filters"] = after.hard_filters.model_dump()
    if before.budget != after.budget:
        patch["budget"] = after.budget.model_dump()
    if before.rules != after.rules:
        patch["rules"] = after.rules.model_dump()
    return patch


def _run_coro_with_timeout(coro, *, timeout_seconds: int):
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="hunt-copilot-planner")
    future = executor.submit(asyncio.run, coro)
    try:
        return future.result(timeout=max(1, timeout_seconds))
    except concurrent.futures.TimeoutError as exc:
        future.cancel()
        raise TimeoutError from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _detect_intent(message: str) -> str:
    text = (message or "").strip().lower()
    if text in {"确认", "确认策略", "ok", "yes", "同意"}:
        return "confirm_strategy"
    if "执行" in text or "开始搜索" in text:
        return "confirm_execution"
    if "通道" in text or "检查" in text:
        return "request_channel_check"
    if "策略卡" in text or "输出" in text:
        return "request_strategy_card"
    if "取消" in text:
        return "cancel_session"
    if "重新" in text:
        return "restart_session"
    return "provide_requirement"
