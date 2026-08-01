"""Merge AI planner patches into the authoritative strategy object."""

from __future__ import annotations

from typing import Any

from hunt_copilot.schemas import HuntStrategy
from product_knowledge import JpsProductRecommender


LIST_FIELDS = {"target_regions", "customer_types", "product_keywords", "exclusions", "required_fields", "preferred_fields", "confirmed_fields"}


class StrategyPatchMerger:
    def __init__(self) -> None:
        self.recommender = JpsProductRecommender()

    def merge(self, strategy: HuntStrategy, patch: dict[str, Any], *, raw_message: str = "") -> HuntStrategy:
        merged = strategy.model_copy(deep=True)
        changed = False
        for field in LIST_FIELDS:
            if field in patch and patch[field] is not None:
                if field == "product_keywords" and _exclusive_keyword_message(raw_message):
                    setattr(merged, field, _incoming_list(patch[field]))
                else:
                    setattr(merged, field, _merge_list(getattr(merged, field), patch[field]))
                changed = True
        if "hard_filters" in patch and isinstance(patch["hard_filters"], dict):
            for key, value in patch["hard_filters"].items():
                if hasattr(merged.hard_filters, key) and value is not None:
                    setattr(merged.hard_filters, key, bool(value))
                    changed = True
        if "budget" in patch and isinstance(patch["budget"], dict):
            for key, value in patch["budget"].items():
                if hasattr(merged.budget, key) and value not in (None, ""):
                    setattr(merged.budget, key, value)
                    changed = True
        if "rules" in patch and isinstance(patch["rules"], dict):
            for key, value in patch["rules"].items():
                if hasattr(merged.rules, key) and value is not None:
                    setattr(merged.rules, key, value)
                    changed = True
        if raw_message.strip():
            merged.raw_requirement = (merged.raw_requirement + "\n" + raw_message.strip()).strip()
        self._normalize_with_product_knowledge(merged, raw_message)
        self._sync_required_fields(merged)
        if changed:
            merged.strategy_version += 1
            merged.strategy_confirmed = False
            merged.needs_recheck = True
        return HuntStrategy.model_validate(merged.model_dump())

    def _normalize_with_product_knowledge(self, strategy: HuntStrategy, raw_message: str) -> None:
        strategy.exclusions = self.recommender.normalize_exclusions(strategy.exclusions, text=raw_message)
        strategy.customer_types = self.recommender.normalize_customer_types(strategy.customer_types, text=raw_message)
        recommendation = self.recommender.recommend(
            customer_types=strategy.customer_types,
            exclusions=strategy.exclusions,
            product_keywords=strategy.product_keywords,
            user_requirement=raw_message or strategy.raw_requirement,
        )
        if recommendation.normalized_customer_types:
            strategy.customer_types = recommendation.normalized_customer_types
        if recommendation.normalized_exclusions:
            strategy.exclusions = recommendation.normalized_exclusions
        if not strategy.product_keywords and recommendation.recommended_keywords:
            strategy.product_keywords = recommendation.recommended_keywords
        strategy.product_knowledge_refs = recommendation.matched_families
        strategy.product_knowledge_notes = recommendation.reasons
        strategy.product_knowledge_summary = _product_summary(recommendation.recommended_keywords, recommendation.matched_families, recommendation.reasons)
        exclusions = {item.lower().strip() for item in strategy.exclusions}
        strategy.customer_types = [
            item for item in strategy.customer_types
            if not any(item.lower().strip() == ex or item.lower().strip() in ex or ex in item.lower().strip() for ex in exclusions)
        ]

    def _sync_required_fields(self, strategy: HuntStrategy) -> None:
        for label in strategy.required_fields:
            normalized = label.lower().strip()
            if normalized in {"instagram", "ins", "ig"}:
                strategy.hard_filters.require_instagram = True
            elif normalized in {"facebook", "fb"}:
                strategy.hard_filters.require_facebook = True
            elif normalized in {"邮箱", "email", "e-mail", "mail"}:
                strategy.hard_filters.require_email = True
            elif normalized in {"电话", "phone", "tel", "whatsapp"}:
                strategy.hard_filters.require_phone = True
            elif normalized in {"官网", "website", "official site"}:
                strategy.hard_filters.require_website = True
            elif normalized in {"地址", "address", "location"}:
                strategy.hard_filters.require_address = True
        labels = strategy.hard_filters.enabled_labels()
        if labels:
            strategy.required_fields = labels


def _merge_list(existing: list[str], incoming: Any) -> list[str]:
    values = incoming if isinstance(incoming, list) else [incoming]
    seen = {str(item).strip().lower() for item in existing if str(item).strip()}
    result = [str(item).strip() for item in existing if str(item).strip()]
    for item in values:
        clean = str(item or "").strip()
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result


def _incoming_list(incoming: Any) -> list[str]:
    values = incoming if isinstance(incoming, list) else [incoming]
    return _merge_list([], values)


def _exclusive_keyword_message(message: str) -> bool:
    text = str(message or "").strip().lower()
    return any(marker in text for marker in ("只要", "只用", "只保留", "就用", "only", "use only"))


def _product_summary(keywords: list[str], families: list[str], reasons: list[str]) -> str:
    parts: list[str] = []
    if families:
        parts.append("匹配产品线：" + "、".join(families[:3]))
    if keywords:
        parts.append("建议关键词：" + "、".join(keywords[:5]))
    if reasons:
        parts.append(reasons[0])
    return "；".join(parts)
