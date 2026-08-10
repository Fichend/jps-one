"""Prompt contract for the Hunt Copilot LLM planner."""

from __future__ import annotations

import json

from hunt_copilot.product_context import JpsProductContextBuilder
from hunt_copilot.schemas import HuntStrategy


SYSTEM_PROMPT = """你是 JPS-One 的 Hunt Copilot AI Planner。

你的职责是和业务员像聊天一样共同整理客户搜索策略卡，但你不能执行搜索、不能消耗搜索预算、不能伪造通道结果。

必须遵守：
- 只输出 JSON，不要输出 Markdown。
- AI 只给 intent、assistant_message 和 strategy_patch，后端会负责合并、校验、预算和执行。
- 排除对象不能放进目标客户。例如“排除普通牙科诊所”只能进入 exclusions。
- 用户说“必须有”才放入 required_fields / hard_filters；不要自动把 Facebook 变成硬条件。
- 产品关键词为空时，只能在 assistant_message 中建议 JPS 产品关键词；未经用户主动采用，禁止写入 strategy_patch.product_keywords。
- 如果用户只说“确认”，根据当前策略判断是确认策略，还是说明缺少什么。
- 搜索通道默认全部启用，不询问业务员选择 API。
"""


def build_planner_prompt(
    message: str,
    strategy: HuntStrategy,
    state: str,
    *,
    recent_messages: list[dict] | None = None,
    conversation_summary: str = "",
    last_user_intent: str = "",
    last_ai_action: str = "",
    clarification_focus: str = "",
) -> str:
    product_context = JpsProductContextBuilder().build(strategy, message=message)
    return json.dumps(
        {
            "task": "根据本轮用户消息更新 HuntStrategy。只返回指定 JSON 协议。",
            "current_state": state,
            "current_strategy": strategy.model_dump(),
            "conversation_summary": conversation_summary,
            "last_user_intent": last_user_intent,
            "last_ai_action": last_ai_action,
            "clarification_focus": clarification_focus,
            "recent_messages": recent_messages or [],
            "jps_product_catalog_context": product_context.as_prompt_context(),
            "user_message": message,
            "planner_rules": [
                "如果用户没有明确产品关键词，参考 jps_product_catalog_context.recommended_keywords 追问；禁止把推荐词写入 strategy_patch.product_keywords。",
                "如果用户目标客户与排除对象冲突，以排除对象为准，并在 assistant_message 里说明已经排除。",
                "回答要像业务主管协助业务员整理策略，说明你理解到什么、缺什么、建议怎么填。",
                "不要输出完整策略卡，策略卡由右侧 UI 展示。",
            ],
            "response_schema": {
                "intent": "provide_requirement | modify_target | modify_product_keywords | modify_required_fields | modify_preferred_fields | modify_exclusions | modify_budget | request_strategy_card | confirm_strategy | request_channel_check | confirm_execution | restart_session | cancel_session | smalltalk",
                "assistant_message": "自然语言回复，简洁说明你理解/修改了什么，缺什么，下一步是什么。不要粘贴整张策略卡。",
                "strategy_patch": {
                    "target_regions": ["国家/地区"],
                    "customer_types": ["客户类型，英文规范优先"],
                    "product_keywords": ["JPS 产品关键词，英文规范优先"],
                    "exclusions": ["排除对象，英文规范优先"],
                    "hard_filters": {
                        "require_instagram": False,
                        "require_facebook": False,
                        "require_email": False,
                        "require_phone": False,
                        "require_website": False,
                        "require_address": False,
                    },
                    "budget": {
                        "preview_total_usd": 0.1,
                        "total_usd": 1,
                        "max_candidates": 40,
                        "final_leads": 10,
                    },
                    "rules": {
                        "hard_filter_enabled": True,
                        "missing_required_action": "pending_then_reject",
                    },
                },
                "detected_conflicts": ["冲突说明"],
                "missing_fields": ["target_regions | customer_types | product_keywords | required_fields | budget"],
                "ready_for_strategy_card": False,
                "suggested_action": "continue_collecting | show_strategy_card | confirm_strategy | check_channels | run_preview | execute | restart | cancel",
            },
        },
        ensure_ascii=False,
    )
