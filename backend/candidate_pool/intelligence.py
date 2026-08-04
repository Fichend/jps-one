"""LLM-assisted candidate profile synthesis and business review.

The deterministic guards decide target type, region and ranking. This module
uses the configured LLM (MiniMax in production when selected) to make the result
more readable for sales users: concise profile, fit reason, risks and next step.
It never deletes candidates and never overrides explicit rule exclusions.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from config.settings import Settings
from tools.llm_client import LLMTool
from tools.llm_output import parse_json

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是 JPS-One 的 B2B 获客复核助手。你只能基于输入的候选客户字段和公开证据进行判断，不能编造事实。

任务：把候选客户解释给业务员看清楚：它是谁、为什么符合或不符合本次目标、缺什么、下一步应该怎么补全。

必须返回 JSON，不要输出 Markdown。"""


def candidate_intelligence_available(settings: Settings) -> bool:
    enabled = getattr(settings, "candidate_intelligence_enabled", True)
    if enabled is False:
        return False
    return _has_llm_key(settings)


async def apply_candidate_intelligence(
    candidates: list[dict[str, Any]],
    *,
    settings: Settings,
    hunt_id: str = "",
    hunt_round: int = 0,
    search_budget: dict[str, Any] | None = None,
    insight: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return candidates annotated with LLM-readable business intelligence."""

    if not candidates or not candidate_intelligence_available(settings):
        return candidates

    budget = search_budget or {}
    # Review every non-excluded candidate in the pool. Earlier versions capped
    # this to candidate_intelligence_max_candidates, which meant a good customer
    # ranked below the cap could miss the LLM-readable profile and fit review.
    selected = [candidate for candidate in candidates if _needs_intelligence(candidate)]
    if not selected:
        return candidates

    llm = LLMTool(model_type="reasoning", settings=settings, hunt_id=hunt_id, agent="candidate_intelligence", hunt_round=hunt_round)
    semaphore = asyncio.Semaphore(max(1, _as_int(getattr(settings, "candidate_intelligence_concurrency", 3), 3)))
    timeout = max(5, _as_int(getattr(settings, "candidate_intelligence_timeout_seconds", 30), 30))
    context = _task_context(budget, insight or {})

    async def run(candidate: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
        async with semaphore:
            candidate_id = str(candidate.get("candidate_id") or candidate.get("website") or candidate.get("company_name") or "")
            try:
                raw = await llm.generate(
                    _prompt(context, candidate),
                    system=SYSTEM_PROMPT,
                    temperature=0.1,
                    max_tokens=900,
                    response_format={"type": "json_object"},
                    timeout_seconds=timeout,
                )
                parsed = parse_json(raw, context="CandidateIntelligence")
                if isinstance(parsed, dict):
                    return candidate_id, _normalize_review(parsed)
            except Exception as exc:
                logger.info("[CandidateIntelligence] review failed candidate=%s: %s", candidate_id, exc)
            return candidate_id, None

    try:
        results = await asyncio.gather(*(run(candidate) for candidate in selected))
    finally:
        await llm.close()

    by_id = {candidate_id: review for candidate_id, review in results if candidate_id and review}
    if not by_id:
        return candidates

    enriched: list[dict[str, Any]] = []
    for candidate in candidates:
        item = dict(candidate)
        candidate_id = str(item.get("candidate_id") or item.get("website") or item.get("company_name") or "")
        review = by_id.get(candidate_id)
        if review:
            _merge_review(item, review)
        enriched.append(item)
    return enriched


def _needs_intelligence(candidate: dict[str, Any]) -> bool:
    status = str(candidate.get("candidate_status") or "")
    if status in {"excluded_by_rule", "excluded_by_goal", "low_relevance_social"}:
        return False
    if candidate.get("candidate_intelligence"):
        return False
    return True


def _task_context(budget: dict[str, Any], insight: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_regions": budget.get("target_regions") or insight.get("recommended_regions") or [],
        "customer_types": budget.get("customer_types") or [],
        "product_keywords": budget.get("product_keywords") or insight.get("products") or [],
        "exclusions": budget.get("exclusions") or insight.get("negative_targeting_criteria") or [],
        "target_customer_profile": insight.get("target_customer_profile") or "",
    }


def _prompt(context: dict[str, Any], candidate: dict[str, Any]) -> str:
    compact = _compact_candidate(candidate)
    return (
        "请复核下面这个候选客户。只根据 candidate 和 evidence 中已有事实判断。\n\n"
        f"task_context = {json.dumps(context, ensure_ascii=False)}\n\n"
        f"candidate = {json.dumps(compact, ensure_ascii=False)}\n\n"
        "返回 JSON schema：\n"
        "{\n"
        '  "ai_profile_summary": "中文，1-2句话说明这家机构/公司是谁以及已知业务",\n'
        '  "ai_fit_assessment": "中文，说明它为什么适合/不适合本次搜索目标，必须引用已有证据",\n'
        '  "ai_risk_flags": ["不超过4个中文风险或缺口"],\n'
        '  "ai_missing_info": ["仍需补全的信息"],\n'
        '  "ai_recommended_action": "keep_recommended | enrich_more | backup | reject",\n'
        '  "ai_confidence": 0.0\n'
        "}\n"
    )


def _compact_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    evidence = []
    for item in candidate.get("evidence_items") or candidate.get("evidence") or []:
        if isinstance(item, dict):
            evidence.append(
                {
                    "source": item.get("source"),
                    "title": item.get("title"),
                    "claim": item.get("claim") or item.get("snippet"),
                    "url": item.get("source_url") or item.get("url"),
                }
            )
    return {
        "company_name": candidate.get("company_name"),
        "website": candidate.get("website"),
        "description": candidate.get("description"),
        "industry": candidate.get("industry"),
        "country": candidate.get("country") or candidate.get("country_code"),
        "address": candidate.get("address"),
        "target_type": candidate.get("target_type"),
        "target_type_fit_score": candidate.get("target_type_fit_score"),
        "target_type_reason": candidate.get("target_type_reason"),
        "region_fit_score": candidate.get("region_fit_score"),
        "region_reason": candidate.get("region_reason"),
        "matched_fields": candidate.get("matched_fields"),
        "missing_fields": candidate.get("missing_fields"),
        "source_channels": candidate.get("source_channels"),
        "emails": candidate.get("emails"),
        "phone_numbers": candidate.get("phone_numbers"),
        "social_media": candidate.get("social_media"),
        "evidence": evidence[:8],
    }


def _normalize_review(data: dict[str, Any]) -> dict[str, Any]:
    action = str(data.get("ai_recommended_action") or "enrich_more").strip()
    if action not in {"keep_recommended", "enrich_more", "backup", "reject"}:
        action = "enrich_more"
    return {
        "ai_profile_summary": str(data.get("ai_profile_summary") or "").strip()[:600],
        "ai_fit_assessment": str(data.get("ai_fit_assessment") or "").strip()[:800],
        "ai_risk_flags": _list_strings(data.get("ai_risk_flags"))[:4],
        "ai_missing_info": _list_strings(data.get("ai_missing_info"))[:6],
        "ai_recommended_action": action,
        "ai_confidence": _clamp_float(data.get("ai_confidence"), 0.0, 1.0),
    }


def _merge_review(candidate: dict[str, Any], review: dict[str, Any]) -> None:
    candidate["candidate_intelligence"] = review
    candidate["ai_profile_summary"] = review.get("ai_profile_summary", "")
    candidate["ai_fit_assessment"] = review.get("ai_fit_assessment", "")
    candidate["ai_recommended_action"] = review.get("ai_recommended_action", "")
    candidate["ai_confidence"] = review.get("ai_confidence", 0.0)
    if review.get("ai_profile_summary"):
        current = str(candidate.get("description") or "").strip()
        if not current or current.startswith("该候选来自公开搜索结果") or "仍需结合官网" in current:
            candidate["description"] = review["ai_profile_summary"]
    if review.get("ai_fit_assessment"):
        candidate["ranking_reason"] = _append_reason(str(candidate.get("ranking_reason") or ""), "AI复核", review["ai_fit_assessment"])
    trace = candidate.get("enrichment_trace") if isinstance(candidate.get("enrichment_trace"), list) else []
    trace.append(
        {
            "task_type": "candidate_intelligence",
            "source": "llm",
            "status": "enriched",
            "message": review.get("ai_fit_assessment", "")[:240],
            "items": 1,
        }
    )
    candidate["enrichment_trace"] = trace


def _append_reason(current: str, label: str, value: str) -> str:
    addition = f"{label}：{value}"
    if not current:
        return addition
    if addition in current:
        return current
    return f"{current}；{addition}"


def _has_llm_key(settings: Settings) -> bool:
    keys = (
        settings.openai_api_key,
        settings.anthropic_api_key,
        settings.openrouter_api_key,
        settings.groq_api_key,
        settings.zai_api_key,
        settings.moonshot_api_key,
        settings.minimax_api_key,
    )
    if any(isinstance(key, str) and key.strip() for key in keys):
        return True
    return any(os.environ.get(name) for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "MINIMAX_API_KEY"))


def _list_strings(value: Any) -> list[str]:
    return [str(item).strip() for item in value if str(item or "").strip()] if isinstance(value, list) else []


def _clamp_float(value: Any, low: float, high: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return low
    return max(low, min(high, parsed))


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
