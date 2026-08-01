"""Context-aware reply suggestions for Hunt Copilot."""

from __future__ import annotations

from hunt_copilot.schemas import CopilotSession
from hunt_copilot.validator import ValidationResult


FIELD_LABELS = {
    "target_regions": "目标地区",
    "customer_types": "目标客户",
    "product_keywords": "JPS 产品关键词",
    "required_fields": "必需字段",
    "budget": "预算和数量",
}


def suggested_replies(session: CopilotSession, validation: ValidationResult) -> list[str]:
    strategy = session.strategy
    replies: list[str] = []
    missing = set(validation.missing_fields)

    if "target_regions" in missing:
        replies.append("目标地区是越南")
        replies.append("目标地区是泰国")
    if "customer_types" in missing:
        replies.append("目标客户是牙科学校和牙科设备经销商，排除普通牙科诊所")
    if "product_keywords" in missing and strategy.customer_types and strategy.product_knowledge_summary:
        keywords = _suggested_keywords(strategy.product_knowledge_summary)
        if keywords:
            replies.append("采用 JPS 推荐关键词：" + "、".join(keywords[:3]))
        replies.append("只要 dental simulator")
    if "required_fields" in missing and strategy.target_regions and strategy.customer_types and strategy.product_keywords:
        replies.append("Instagram、邮箱、电话作为硬条件")
        replies.append("邮箱和电话作为硬条件，社媒作为优先字段")

    if validation.detected_conflicts or validation.blocking_errors:
        replies.append("把排除对象从目标客户里移除")
    if strategy.budget.max_candidates < strategy.budget.final_leads * 3:
        replies.append(f"候选池改为 {max(strategy.budget.final_leads * 4, 40)} 个")

    if validation.can_confirm_strategy and not strategy.strategy_confirmed:
        replies.append("确认策略")
    return _dedupe(replies)[:4]


def is_light_smalltalk(message: str) -> bool:
    text = str(message or "").strip().lower()
    return text in {"hi", "hello", "hey", "你好", "您好", "在吗", "开始", "start"}


def missing_field_labels(validation: ValidationResult) -> list[str]:
    return [FIELD_LABELS.get(item, item) for item in validation.missing_fields]


def _suggested_keywords(summary: str) -> list[str]:
    if "建议关键词：" not in summary:
        return []
    raw = summary.split("建议关键词：", 1)[-1].split("；", 1)[0]
    return [item.strip() for item in raw.split("、") if item.strip()]


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(value.strip())
    return result
