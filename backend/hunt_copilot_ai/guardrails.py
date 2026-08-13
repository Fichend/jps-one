"""Semantic guardrails for Hunt Copilot strategy slots."""

from __future__ import annotations

from hunt_copilot_ai.domain_normalizer import normalize_application_scenario
from hunt_copilot_ai.schemas import GuardrailResult, SemanticSlots, SlotValue


PRODUCT_BLOCKLIST_MARKERS = (
    "潜在客户",
    "目标客户",
    "客户是",
    "例如",
    "比如",
    "面向",
    "应用场景",
    "需要找",
    "我要找",
    "target customer",
    "potential customer",
)

CUSTOMER_ONLY_VALUES = {"distributor", "agent", "dealer", "importer", "supplier", "manufacturer", "clinic", "hospital", "dental school", "training center"}
SCENARIO_ONLY_VALUES = {"cssd", "central sterile supply department"}


class SemanticGuardrails:
    def review(self, slots: SemanticSlots, *, raw_message: str = "") -> GuardrailResult:
        clean = SemanticSlots.model_validate(slots.model_dump())
        conflicts: list[str] = []
        rejected: dict[str, list[str]] = {}
        business_notes: list[str] = []

        accepted_products: list[SlotValue] = []
        for slot in clean.product_keywords:
            reason = self._reject_product_reason(slot)
            if reason:
                rejected.setdefault("product_keywords", []).append(slot.value)
                conflicts.append(f"{slot.value} 不像产品关键词，已阻止写入产品字段。")
                if slot.value and slot.value not in business_notes:
                    business_notes.append(slot.value)
                continue
            accepted_products.append(slot)
        clean.product_keywords = accepted_products

        # CSSD should never be lost just because a model placed it in the wrong field.
        for value in rejected.get("product_keywords", []):
            if "cssd" in value.casefold() and not _has_value(clean.application_scenarios, "CSSD"):
                clean.application_scenarios.append(
                    SlotValue(value="CSSD", confidence=0.9, source_text=value, source="rule")
                )
        if "cssd" in raw_message.casefold() and not _has_value(clean.application_scenarios, "CSSD"):
            clean.application_scenarios.append(
                SlotValue(value="CSSD", confidence=0.92, source_text="CSSD", source="rule")
            )

        clean.customer_types = [slot for slot in clean.customer_types if slot.value.casefold().strip() not in SCENARIO_ONLY_VALUES]
        clean.application_scenarios = [
            SlotValue(
                value=normalize_application_scenario(slot.value),
                confidence=slot.confidence,
                source_text=slot.source_text,
                source=slot.source,
            )
            for slot in clean.application_scenarios
            if slot.value.casefold().strip() not in CUSTOMER_ONLY_VALUES
        ]

        exclusion_keys = {slot.value.casefold().strip() for slot in clean.exclusions}
        clean.customer_types = [slot for slot in clean.customer_types if slot.value.casefold().strip() not in exclusion_keys]

        for note in business_notes:
            if not _has_value(clean.business_notes, note):
                clean.business_notes.append(SlotValue(value=note, confidence=0.75, source_text=note, source="rule"))

        return GuardrailResult(slots=clean, detected_conflicts=_dedupe(conflicts), rejected_fields=rejected, business_notes=business_notes)

    @staticmethod
    def _reject_product_reason(slot: SlotValue) -> str:
        value = str(slot.value or "").strip()
        lower = value.casefold()
        if not value:
            return "empty"
        if len(value) > 55:
            return "too_long"
        if lower in CUSTOMER_ONLY_VALUES or lower in SCENARIO_ONLY_VALUES:
            return "wrong_field"
        if any(marker.casefold() in lower for marker in PRODUCT_BLOCKLIST_MARKERS):
            return "business_sentence"
        return ""


def _has_value(slots: list[SlotValue], value: str) -> bool:
    key = value.casefold().strip()
    return any(slot.value.casefold().strip() == key for slot in slots)


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold().strip()
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result
