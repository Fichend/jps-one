"""Compose semantic slots into the authoritative HuntStrategy."""

from __future__ import annotations

from typing import Any

from hunt_copilot.schemas import HuntStrategy
from hunt_copilot_ai.schemas import ComposeResult, GuardrailResult, SlotValue
from product_knowledge import JpsProductRecommender
from product_knowledge.taxonomy import (
    UNCLEAR,
    infer_product_direction,
    specialize_customer_types,
    specialize_exclusions,
)


CONFIDENCE_THRESHOLD = 0.75


class StrategyComposer:
    def __init__(self) -> None:
        self.recommender = JpsProductRecommender()

    def compose(self, strategy: HuntStrategy, guardrails: GuardrailResult, *, raw_message: str = "") -> ComposeResult:
        before = strategy.model_copy(deep=True)
        updated = strategy.model_copy(deep=True)
        slots = guardrails.slots

        _merge_slots(updated, "target_regions", slots.target_regions)
        _merge_slots(updated, "customer_types", slots.customer_types)
        _merge_slots(updated, "application_scenarios", slots.application_scenarios)
        _merge_slots(updated, "exclusions", slots.exclusions)
        _merge_slots(updated, "business_notes", slots.business_notes)

        if _exclusive_product_message(raw_message) and _accepted(slots.product_keywords):
            updated.product_keywords = [slot.value for slot in _accepted(slots.product_keywords)]
            _record_sources(updated, "product_keywords", _accepted(slots.product_keywords))
        else:
            _merge_slots(updated, "product_keywords", slots.product_keywords)

        for slot in _accepted(slots.required_fields):
            _enable_required_field(updated, slot.value)
            _record_sources(updated, "required_fields", [slot])

        if slots.budget:
            for key, value in slots.budget.items():
                if hasattr(updated.budget, key) and value not in (None, ""):
                    setattr(updated.budget, key, value)
            if updated.budget.final_leads > updated.budget.max_candidates:
                updated.budget.max_candidates = max(updated.budget.final_leads * 4, updated.budget.final_leads)

        if raw_message.strip():
            updated.raw_requirement = (updated.raw_requirement + "\n" + raw_message.strip()).strip()

        self._normalize_product_knowledge(updated, raw_message)
        updated.uncertain_fields = _dedupe([*updated.uncertain_fields, *guardrails.slots.model_dump().get("uncertain_fields", [])])
        updated.last_extraction = {
            "raw_message": raw_message,
            "slots": slots.model_dump(mode="json"),
            "rejected_fields": guardrails.rejected_fields,
            "detected_conflicts": guardrails.detected_conflicts,
        }

        changed = _business_dump(before) != _business_dump(updated)
        if changed:
            updated.strategy_version += 1
            updated.strategy_confirmed = False
            updated.needs_recheck = True
        else:
            updated = before
        validated = HuntStrategy.model_validate(updated.model_dump())
        return ComposeResult(strategy=validated, changed=changed, recent_changes=_strategy_changes(before, validated))

    def _normalize_product_knowledge(self, strategy: HuntStrategy, raw_message: str) -> None:
        strategy.exclusions = self.recommender.normalize_exclusions(strategy.exclusions, text=raw_message)
        strategy.customer_types = self.recommender.normalize_customer_types(strategy.customer_types, text=raw_message)
        direction = infer_product_direction(
            text=raw_message or strategy.raw_requirement,
            product_keywords=strategy.product_keywords,
            customer_types=strategy.customer_types,
            application_scenarios=strategy.application_scenarios,
        )
        if direction.department != UNCLEAR:
            strategy.product_department = direction.department
        if direction.category != UNCLEAR:
            strategy.product_category = direction.category

        strategy.customer_types = specialize_customer_types(
            strategy.customer_types,
            department=strategy.product_department,
            category=strategy.product_category,
            raw_text=raw_message or strategy.raw_requirement,
        )
        strategy.exclusions = specialize_exclusions(
            strategy.exclusions,
            department=strategy.product_department,
            category=strategy.product_category,
        )
        recommendation = self.recommender.recommend(
            customer_types=strategy.customer_types,
            exclusions=strategy.exclusions,
            product_keywords=strategy.product_keywords,
            user_requirement=raw_message or strategy.raw_requirement,
        )
        if recommendation.normalized_customer_types:
            strategy.customer_types = specialize_customer_types(
                recommendation.normalized_customer_types,
                department=strategy.product_department,
                category=strategy.product_category,
                raw_text=raw_message or strategy.raw_requirement,
            )
        if recommendation.normalized_exclusions:
            strategy.exclusions = specialize_exclusions(
                recommendation.normalized_exclusions,
                department=strategy.product_department,
                category=strategy.product_category,
            )
        strategy.product_knowledge_refs = recommendation.matched_families
        strategy.product_knowledge_notes = recommendation.reasons
        strategy.product_knowledge_summary = _product_summary(recommendation.recommended_keywords, recommendation.matched_families, recommendation.reasons)
        exclusions = {item.lower().strip() for item in strategy.exclusions}
        strategy.customer_types = [
            item for item in strategy.customer_types
            if not any(item.lower().strip() == ex or item.lower().strip() in ex or ex in item.lower().strip() for ex in exclusions)
        ]


def _merge_slots(strategy: HuntStrategy, field_name: str, slots: list[SlotValue]) -> None:
    incoming = _accepted(slots)
    if not incoming:
        return
    current = list(getattr(strategy, field_name))
    seen = {item.casefold().strip() for item in current}
    for slot in incoming:
        key = slot.value.casefold().strip()
        if key and key not in seen:
            current.append(slot.value)
            seen.add(key)
    setattr(strategy, field_name, current)
    _record_sources(strategy, field_name, incoming)


def _accepted(slots: list[SlotValue]) -> list[SlotValue]:
    return [slot for slot in slots if slot.confidence >= CONFIDENCE_THRESHOLD and str(slot.value or "").strip()]


def _record_sources(strategy: HuntStrategy, field_name: str, slots: list[SlotValue]) -> None:
    if not slots:
        return
    sources = list(strategy.field_sources.get(field_name, []))
    confidences = [float(slot.confidence) for slot in slots]
    for slot in slots:
        source = slot.source_text or slot.value
        if source and source not in sources:
            sources.append(source)
    strategy.field_sources[field_name] = sources[-8:]
    strategy.field_confidence[field_name] = max([strategy.field_confidence.get(field_name, 0.0), *confidences])


def _enable_required_field(strategy: HuntStrategy, value: str) -> None:
    mapping = {
        "require_instagram": "require_instagram",
        "instagram": "require_instagram",
        "ins": "require_instagram",
        "require_facebook": "require_facebook",
        "facebook": "require_facebook",
        "require_email": "require_email",
        "email": "require_email",
        "邮箱": "require_email",
        "require_phone": "require_phone",
        "phone": "require_phone",
        "电话": "require_phone",
        "require_website": "require_website",
        "website": "require_website",
        "官网": "require_website",
        "require_address": "require_address",
        "address": "require_address",
        "地址": "require_address",
    }
    key = mapping.get(str(value or "").casefold().strip()) or mapping.get(str(value or "").strip())
    if key and hasattr(strategy.hard_filters, key):
        setattr(strategy.hard_filters, key, True)
        strategy.required_fields = strategy.hard_filters.enabled_labels()


def _exclusive_product_message(message: str) -> bool:
    text = str(message or "").strip().lower()
    return any(marker in text for marker in ("只要", "只用", "只保留", "仅保留", "use only", "keep only", "only"))


def _business_dump(strategy: HuntStrategy) -> dict[str, Any]:
    return {
        "target_regions": strategy.target_regions,
        "customer_types": strategy.customer_types,
        "product_keywords": strategy.product_keywords,
        "product_department": strategy.product_department,
        "product_category": strategy.product_category,
        "application_scenarios": strategy.application_scenarios,
        "business_notes": strategy.business_notes,
        "exclusions": strategy.exclusions,
        "hard_filters": strategy.hard_filters.model_dump(),
        "required_fields": strategy.required_fields,
        "preferred_fields": strategy.preferred_fields,
        "confirmed_fields": strategy.confirmed_fields,
        "budget": strategy.budget.model_dump(),
        "rules": strategy.rules.model_dump(),
    }


def _strategy_changes(before: HuntStrategy, after: HuntStrategy) -> list[str]:
    changes: list[str] = []
    for field, label in (
        ("target_regions", "目标地区"),
        ("customer_types", "目标客户"),
        ("product_keywords", "产品关键词"),
        ("product_department", "业务部门"),
        ("product_category", "产品分类"),
        ("application_scenarios", "应用场景"),
        ("business_notes", "业务说明"),
        ("exclusions", "排除对象"),
    ):
        if getattr(before, field) != getattr(after, field):
            value = getattr(after, field)
            rendered = _join(value) if isinstance(value, list) else str(value or "")
            changes.append(f"{label}：{rendered or '已清空'}")
    if before.hard_filters != after.hard_filters:
        changes.append(f"重点补全：{_join(after.hard_filters.enabled_labels()) or '未设置'}")
    if before.budget != after.budget:
        changes.append(f"数量预算：候选 {after.budget.max_candidates}，最终 {after.budget.final_leads}，预算 {after.budget.total_usd:g} USD")
    return changes[:8]


def _product_summary(keywords: list[str], families: list[str], reasons: list[str]) -> str:
    parts: list[str] = []
    if families:
        parts.append("匹配产品线：" + "、".join(families[:3]))
    if keywords:
        parts.append("建议关键词：" + "、".join(keywords[:5]))
    if reasons:
        parts.append(reasons[0])
    return "；".join(parts)


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = str(value or "").casefold().strip()
        if key and key not in seen:
            seen.add(key)
            result.append(str(value).strip())
    return result


def _join(values: list[str]) -> str:
    return "、".join(str(item) for item in values if str(item).strip())
