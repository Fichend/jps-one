"""Semantic slot extraction for Hunt Copilot requirements."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import re

from config.settings import Settings, get_settings
from hunt_copilot.schemas import HuntStrategy
from hunt_copilot_ai.domain_normalizer import (
    APPLICATION_SCENARIO_ALIASES,
    CUSTOMER_ROLE_ALIASES,
    PRODUCT_KEYWORD_ALIASES,
    find_aliases,
    find_countries,
    has_explicit_product_marker,
    marker_present,
    normalize_application_scenario,
    normalize_contact_field,
    normalize_country,
    normalize_customer_role,
    normalize_product_keyword,
    split_values,
)
from hunt_copilot_ai.schemas import SemanticExtraction, SemanticSlots, SlotValue
from tools.llm_client import LLMTool
from tools.llm_output import parse_json

logger = logging.getLogger(__name__)


class SemanticExtractor:
    """Extract semantic slots, with LLM first and deterministic repair/fallback."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def extract(
        self,
        message: str,
        strategy: HuntStrategy,
        *,
        state: str,
        recent_messages: list[dict] | None = None,
        conversation_summary: str = "",
        clarification_focus: str = "",
    ) -> SemanticExtraction:
        fallback = self._fallback(message)
        if not self._enabled():
            return fallback
        try:
            ai = _run_coro_with_timeout(
                self._extract_async(
                    message,
                    strategy,
                    state=state,
                    recent_messages=recent_messages or [],
                    conversation_summary=conversation_summary,
                    clarification_focus=clarification_focus,
                ),
                timeout_seconds=max(2, int(self.settings.hunt_copilot_planner_timeout_seconds) + 1),
            )
            return self._merge_with_deterministic(message, ai, fallback)
        except TimeoutError:
            logger.warning("SemanticExtractor timed out; using deterministic fallback")
            return fallback
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("SemanticExtractor failed; using deterministic fallback: %s", exc)
            return fallback

    async def _extract_async(
        self,
        message: str,
        strategy: HuntStrategy,
        *,
        state: str,
        recent_messages: list[dict],
        conversation_summary: str,
        clarification_focus: str,
    ) -> SemanticExtraction:
        model = self.settings.hunt_copilot_model.strip()
        llm_settings = self.settings.model_copy(update={"llm_model": model}) if model else self.settings
        llm = LLMTool(settings=llm_settings, agent="hunt_copilot_semantic_extractor")
        prompt = json.dumps(
            {
                "task": "Extract Hunt Copilot semantic slots from the user message. Return JSON only.",
                "current_state": state,
                "current_strategy": strategy.model_dump(mode="json"),
                "conversation_summary": conversation_summary,
                "clarification_focus": clarification_focus,
                "recent_messages": recent_messages[-10:],
                "user_message": message,
                "field_definitions": {
                    "target_regions": "countries or regions to search in",
                    "customer_types": "who the salesperson wants to find, such as distributor, agent, dental school, training center",
                    "product_keywords": "JPS product or product family only; never put a whole business sentence here",
                    "application_scenarios": "where or for whom the product is used, e.g. CSSD, dental education, training lab",
                    "exclusions": "regions, customer types, pages or entities to exclude",
                    "business_notes": "extra requirement notes that are not a strategy field",
                },
                "critical_rules": [
                    "If user says CSSD potential customers, CSSD is application_scenarios, not product_keywords.",
                    "If user says 经销商 or 代理商, put them in customer_types as distributor/agent.",
                    "If a phrase contains 潜在客户, 例如, 面向, 应用场景, it is not a product keyword.",
                    "Only fill product_keywords when the user explicitly provides a product or a known product term.",
                    "Low confidence fields should go to uncertain_fields, not strategy slots.",
                ],
                "response_schema": {
                    "intent": "provide_requirement | modify_strategy | answer_question | smalltalk",
                    "slots": {
                        "target_regions": [{"value": "Brazil", "confidence": 0.0, "source_text": "Brazil", "source": "explicit"}],
                        "customer_types": [{"value": "distributor", "confidence": 0.0, "source_text": "经销商", "source": "explicit"}],
                        "product_keywords": [{"value": "sterilization", "confidence": 0.0, "source_text": "sterilization", "source": "explicit"}],
                        "application_scenarios": [{"value": "CSSD", "confidence": 0.0, "source_text": "CSSD", "source": "explicit"}],
                        "exclusions": [{"value": "Spain", "confidence": 0.0, "source_text": "排除 Spain", "source": "explicit"}],
                        "required_fields": [],
                        "preferred_fields": [],
                        "business_notes": [],
                        "budget": {},
                    },
                    "uncertain_fields": ["product_keywords"],
                    "assistant_message": "natural Chinese reply",
                },
            },
            ensure_ascii=False,
        )
        response_format = None if "minimax" in llm_settings.llm_model.lower() else {"type": "json_object"}
        raw = await asyncio.wait_for(
            llm.generate(
                prompt,
                system="You are a careful B2B search requirement semantic extractor. Return JSON only.",
                temperature=0.0,
                max_tokens=2200,
                response_format=response_format,
                timeout_seconds=max(1, int(self.settings.hunt_copilot_planner_timeout_seconds)),
            ),
            timeout=max(1, int(self.settings.hunt_copilot_planner_timeout_seconds)),
        )
        data = parse_json(raw, context="SemanticExtractor")
        if not isinstance(data, dict):
            raise ValueError("semantic extractor returned non-JSON response")
        data["raw_model_output"] = dict(data)
        return SemanticExtraction.model_validate(data)

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

    def _fallback(self, message: str) -> SemanticExtraction:
        text = str(message or "").strip()
        slots = SemanticSlots()

        exclusions_text = _exclusion_text(text)
        exclusion_countries = {normalize_country(country) for country, _ in find_countries(exclusions_text)} if exclusions_text else set()
        for country, source_text in find_countries(text):
            value = normalize_country(country)
            slot = SlotValue(value=value, confidence=0.98, source_text=source_text, source="explicit")
            if value in exclusion_countries:
                _append_slot(slots.exclusions, slot)
            else:
                _append_slot(slots.target_regions, slot)

        for value, source_text in find_aliases(text, CUSTOMER_ROLE_ALIASES):
            confidence = 0.96 if source_text in text else 0.86
            _append_slot(
                slots.customer_types,
                SlotValue(value=normalize_customer_role(value), confidence=confidence, source_text=source_text, source="explicit"),
            )

        if exclusions_text:
            for value, source_text in find_aliases(exclusions_text, CUSTOMER_ROLE_ALIASES):
                _append_slot(
                    slots.exclusions,
                    SlotValue(value=normalize_customer_role(value), confidence=0.96, source_text=source_text, source="explicit"),
                )
            for country, source_text in find_countries(exclusions_text):
                _append_slot(
                    slots.exclusions,
                    SlotValue(value=normalize_country(country), confidence=0.98, source_text=source_text, source="explicit"),
                )

        for value, source_text in find_aliases(text, APPLICATION_SCENARIO_ALIASES):
            _append_slot(
                slots.application_scenarios,
                SlotValue(value=normalize_application_scenario(value), confidence=0.94, source_text=source_text, source="explicit"),
            )

        for product in _explicit_product_values(text):
            _append_slot(
                slots.product_keywords,
                SlotValue(value=normalize_product_keyword(product), confidence=0.96, source_text=product, source="explicit"),
            )

        if not slots.product_keywords:
            for value, source_text in find_aliases(text, PRODUCT_KEYWORD_ALIASES):
                if _source_is_business_context(text, source_text):
                    continue
                source = "explicit" if has_explicit_product_marker(text) else "inferred"
                confidence = 0.88 if source == "inferred" else 0.96
                _append_slot(
                    slots.product_keywords,
                    SlotValue(value=normalize_product_keyword(value), confidence=confidence, source_text=source_text, source=source),
                )

        hard = _contact_fields(text)
        for label in hard:
            _append_slot(slots.required_fields, SlotValue(value=label, confidence=0.97, source_text=label, source="explicit"))

        budget = _budget(text)
        if budget:
            slots.budget = budget

        if _business_note_text(text):
            _append_slot(
                slots.business_notes,
                SlotValue(value=_business_note_text(text), confidence=0.85, source_text=text, source="inferred"),
            )

        uncertain: list[str] = []
        if slots.customer_types and not slots.product_keywords:
            uncertain.append("product_keywords")
        if not slots.target_regions:
            uncertain.append("target_regions")

        return SemanticExtraction(intent="provide_requirement", slots=slots, uncertain_fields=uncertain)

    def _merge_with_deterministic(
        self,
        message: str,
        ai: SemanticExtraction,
        fallback: SemanticExtraction,
    ) -> SemanticExtraction:
        # Deterministic high-confidence signals repair common MiniMax omissions.
        for field_name in ("target_regions", "customer_types", "application_scenarios", "exclusions", "required_fields"):
            target = getattr(ai.slots, field_name)
            for slot in getattr(fallback.slots, field_name):
                _append_slot(target, slot)

        # Products are more dangerous: deterministic products only repair known explicit/product-term cases.
        for slot in fallback.slots.product_keywords:
            if slot.source == "explicit" or marker_present(message, slot.source_text):
                _append_slot(ai.slots.product_keywords, slot)
        if fallback.slots.budget:
            ai.slots.budget = {**ai.slots.budget, **fallback.slots.budget}
        ai.uncertain_fields = _dedupe([*ai.uncertain_fields, *fallback.uncertain_fields])
        return ai


def _run_coro_with_timeout(coro, *, timeout_seconds: int):
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="hunt-copilot-semantic")
    future = executor.submit(asyncio.run, coro)
    try:
        return future.result(timeout=max(1, timeout_seconds))
    except concurrent.futures.TimeoutError as exc:
        future.cancel()
        raise TimeoutError from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _append_slot(target: list[SlotValue], slot: SlotValue) -> None:
    key = slot.value.casefold().strip()
    if not key:
        return
    for index, existing in enumerate(target):
        if existing.value.casefold().strip() == key:
            if slot.confidence > existing.confidence:
                target[index] = slot
            return
    target.append(slot)


def _exclusion_text(text: str) -> str:
    match = re.search(r"(?:排除|不要(?:包含)?|exclude|without)\s*(.+)$", text, flags=re.IGNORECASE)
    if not match:
        return ""
    return re.split(r"(?:必须|硬条件|候选|最终|预算|产品|关键词|must have|required|candidate|final|budget|product)", match.group(1), maxsplit=1, flags=re.IGNORECASE)[0]


def _explicit_product_values(text: str) -> list[str]:
    patterns = (
        r"(?:产品关键词|产品|关键词)(?:是|为|[:：])\s*(.+?)(?=$|[,，;；]\s*(?:排除|不要|必须|硬条件|候选|最终|预算|应用场景|场景))",
        r"(?:只要|只用|只保留|仅保留)\s*(.+?)(?=$|[,，;；]\s*(?:排除|不要|必须|硬条件|候选|最终|预算))",
        r"\bproduct(?:\s+keywords?)?\s*(?:is|are|:)?\s*(.+?)(?=$|[,;]\s*(?:exclude|must|candidate|final|budget))",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        values = []
        for value in split_values(match.group(1), split_chinese_and=False):
            if _looks_like_business_sentence(value):
                continue
            values.append(value)
        if values:
            return values
    return []


def _contact_fields(text: str) -> list[str]:
    lower = text.casefold()
    has_contact = any(marker_present(lower, alias) for alias in ("instagram", "ins", "facebook", "邮箱", "email", "电话", "phone", "官网", "website", "地址", "address"))
    if not has_contact:
        return []
    if not any(marker in lower for marker in ("必须", "硬条件", "must have", "required")) and not _looks_like_search_requirement(lower):
        return []
    labels: list[str] = []
    for alias in ("instagram", "ins", "facebook", "邮箱", "email", "电话", "phone", "官网", "website", "地址", "address"):
        if marker_present(lower, alias):
            normalized = normalize_contact_field(alias)
            if normalized not in labels:
                labels.append(normalized)
    return labels


def _looks_like_search_requirement(text: str) -> bool:
    return any(marker in text for marker in ("找", "客户", "经销商", "代理商", "distributor", "dealer", "agent", "school", "hospital", "candidate", "top"))


def _budget(text: str) -> dict[str, int | float]:
    lower = text.casefold()
    result: dict[str, int | float] = {}
    candidate = re.search(r"(?:候选|candidate(?:s)?)(?:池|数量|先找)?\s*(\d+)", lower)
    final = re.search(r"(?:最终|入库|top|final(?: leads?)?)(?:推荐|客户|只要|数量)?\s*(\d+)", lower)
    money = re.search(r"(?:预算|budget)\s*(?:控制在|为|是|:)?\s*(\d+(?:\.\d+)?)\s*(?:usd|美元|美金|\$)?", lower)
    if candidate:
        result["max_candidates"] = int(candidate.group(1))
    if final:
        result["final_leads"] = int(final.group(1))
    if money:
        result["total_usd"] = float(money.group(1))
    return result


def _source_is_business_context(text: str, source_text: str) -> bool:
    lower = text.casefold()
    source = source_text.casefold()
    if source == "cssd":
        return True
    return any(marker in lower for marker in ("潜在客户", "目标客户", "客户是", "面向", "应用场景")) and source in {"cssd"}


def _looks_like_business_sentence(value: str) -> bool:
    lower = str(value or "").casefold()
    return len(value) > 55 or any(marker in lower for marker in ("潜在客户", "例如", "客户", "面向", "应用场景", "target customer"))


def _business_note_text(text: str) -> str:
    clean = re.sub(r"\s+", " ", str(text or "").strip())
    if any(marker in clean.casefold() for marker in ("潜在客户", "面向", "应用场景", "for cssd")):
        return clean[:160]
    return ""


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = str(value or "").strip().casefold()
        if key and key not in seen:
            seen.add(key)
            result.append(str(value).strip())
    return result
