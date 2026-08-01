"""Soft ranking and status annotation for candidate pools.

Contact and social selections from Hunt Copilot are enrichment targets: they add
coverage score when found, but they do not delete a relevant customer. Business
fit, product relevance, source evidence and JPS score must dominate ranking.
"""

from __future__ import annotations

from typing import Any

from goal_guard.rank_integration import apply_goal_guard


REQUIRED_FIELD_MAP = {
    "require_instagram": "instagram",
    "require_facebook": "facebook",
    "require_email": "email",
    "require_phone": "phone",
    "require_website": "website",
    "require_address": "address",
}


FIELD_WEIGHTS = {
    "instagram": 16,
    "facebook": 10,
    "email": 16,
    "phone": 14,
    "website": 10,
    "address": 6,
}


def rank_candidates(
    candidates: list[dict[str, Any]],
    *,
    target_final_leads: int = 10,
    hard_filters: dict[str, Any] | None = None,
    exclusions: list[str] | None = None,
    customer_types: list[str] | None = None,
    product_keywords: list[str] | None = None,
    target_regions: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return all candidates sorted and annotated with rank/status/reasons."""

    preferred = enabled_required_fields(hard_filters or {})
    guarded = apply_goal_guard(
        [candidate for candidate in candidates if isinstance(candidate, dict)],
        customer_types=customer_types or [],
        product_keywords=product_keywords or [],
        target_regions=target_regions or [],
        exclusions=exclusions or [],
    )
    annotated = [annotate_candidate(candidate, preferred=preferred, exclusions=exclusions or []) for candidate in guarded]
    annotated.sort(key=_rank_key, reverse=True)
    target = max(1, int(target_final_leads or 10))
    for index, item in enumerate(annotated, start=1):
        item["rank"] = index
        if item.get("candidate_status") in {"excluded_by_rule", "excluded_by_goal"}:
            continue
        if item.get("candidate_status") == "low_relevance_social":
            continue
        if index <= target:
            item["candidate_status"] = "qualified_recommended" if not item.get("missing_fields") else "ranked_candidate"
        elif item.get("ranking_score", 0) >= 35:
            item["candidate_status"] = "backup_candidate"
        else:
            item["candidate_status"] = "needs_enrichment"
    return annotated


def annotate_candidate(candidate: dict[str, Any], *, preferred: list[str] | None = None, required: list[str] | None = None, exclusions: list[str] | None = None) -> dict[str, Any]:
    item = dict(candidate)
    preferred = preferred if preferred is not None else (required or [])
    matched = [field for field in ("instagram", "facebook", "email", "phone", "website", "address") if has_field(item, field)]
    missing = [field for field in preferred if field not in matched]
    penalties = _business_rule_penalties(item, exclusions or [])
    if _looks_like_low_relevance_social(item):
        penalties += 45
    goal_score = int(item.get("target_type_fit_score", 30) or 0)
    goal_flags = [str(flag) for flag in (item.get("goal_drift_flags") or [])]
    if "matches_exclusion" in goal_flags:
        penalties += 90
    if any(flag in goal_flags for flag in ("directory_not_customer", "media_not_customer")):
        penalties += 70
    if any(flag in goal_flags for flag in ("manufacturer_when_distributor_requested", "clinic_excluded")):
        penalties += 65
    if "region_mismatch_confirmed" in goal_flags:
        penalties += 180
    elif "region_mismatch_suspected" in goal_flags:
        penalties += 80
    elif "region_unknown" in goal_flags:
        penalties += 15
    region_score = int(item.get("region_fit_score", 100) or 0)
    requirement_points = sum(FIELD_WEIGHTS.get(field, 0) for field in matched if field in preferred)
    non_required_contact_points = min(12, sum(3 for field in matched if field not in preferred))
    evidence_points = min(12, len(item.get("evidence_items") or item.get("evidence") or []) * 2)
    source_points = min(10, len(item.get("source_channels") or []) * 3)
    base = min(20, int(item.get("jps_score", 0) or 0) // 4)
    confidence = int(round(float(item.get("confidence", item.get("fit_score", item.get("match_score", 0))) or 0) * 10))
    previous_rank_bonus = _previous_rank_bonus(item)
    ranking_score = max(0, goal_score * 3 + region_score * 2 + base + previous_rank_bonus + requirement_points + non_required_contact_points + evidence_points + source_points + confidence - penalties)
    item["matched_fields"] = matched
    item["missing_fields"] = missing
    item["ranking_score"] = ranking_score
    item["preferred_match_count"] = len(preferred) - len(missing)
    item["preferred_total_count"] = len(preferred)
    # Backward-compatible names for older frontend/tests.
    item["required_match_count"] = item["preferred_match_count"]
    item["required_total_count"] = item["preferred_total_count"]
    item["ranking_reason"] = _ranking_reason(item, preferred=preferred, penalties=penalties)
    if "matches_exclusion" in goal_flags or any(flag in goal_flags for flag in ("directory_not_customer", "media_not_customer", "manufacturer_when_distributor_requested", "clinic_excluded", "region_mismatch_confirmed")):
        item["candidate_status"] = "excluded_by_goal"
    elif penalties >= 40:
        item["candidate_status"] = "low_relevance_social" if _looks_like_low_relevance_social(item) else "excluded_by_rule"
    elif missing:
        item["candidate_status"] = "ranked_candidate"
    else:
        item["candidate_status"] = "enriched"
    return item


def enabled_required_fields(hard_filters: dict[str, Any]) -> list[str]:
    return [label for key, label in REQUIRED_FIELD_MAP.items() if bool(hard_filters.get(key))]


def has_field(item: dict[str, Any], field: str) -> bool:
    if field == "instagram":
        return bool(str(item.get("instagram_url") or "").strip() or _social(item, "instagram"))
    if field == "facebook":
        return bool(str(item.get("facebook_url") or "").strip() or _social(item, "facebook"))
    if field == "email":
        emails = item.get("emails") if isinstance(item.get("emails"), list) else []
        return bool(str(item.get("email") or "").strip() or [value for value in emails if str(value or "").strip()])
    if field == "phone":
        phones = item.get("phone_numbers") if isinstance(item.get("phone_numbers"), list) else []
        return bool(str(item.get("phone") or "").strip() or [value for value in phones if str(value or "").strip()])
    if field == "website":
        return bool(str(item.get("website") or "").strip())
    if field == "address":
        return bool(str(item.get("address") or "").strip())
    return False


def _social(item: dict[str, Any], provider: str) -> str:
    social = item.get("social_media") if isinstance(item.get("social_media"), dict) else {}
    return str(social.get(provider) or social.get(f"{provider}_url") or social.get(provider.title()) or "").strip()


def _rank_key(item: dict[str, Any]) -> tuple[int, int, int, int, int, int, int]:
    status_penalty = -1 if item.get("candidate_status") in {"excluded_by_rule", "excluded_by_goal", "low_relevance_social"} else 0
    return (
        status_penalty,
        int(item.get("region_fit_score", 100) or 0),
        int(item.get("target_type_fit_score", 0) or 0),
        int(item.get("ranking_score", 0) or 0),
        int(item.get("jps_score", 0) or 0),
        int(item.get("preferred_match_count", item.get("required_match_count", 0)) or 0),
        len(item.get("evidence_items") or item.get("evidence") or []),
    )


def _looks_like_low_relevance_social(item: dict[str, Any]) -> bool:
    channels = " ".join(str(source or "") for source in item.get("source_channels") or []).lower()
    social_only = bool(channels) and any(source in channels for source in ("apify_instagram", "apify_facebook")) and not any(
        source in channels for source in ("google_maps", "tavily", "web_search", "tavily_mcp")
    )
    has_business_anchor = bool(item.get("website") or item.get("phone") or item.get("email") or item.get("address"))
    text = " ".join(str(value or "") for value in (item.get("company_name"), item.get("description"), item.get("industry"))).lower()
    dental_or_medical = any(marker in text for marker in ("dental", "dentist", "dentistry", "medical", "nha khoa", "ทันต", "odont", "gigi"))
    return social_only and not has_business_anchor and not dental_or_medical


def _business_rule_penalties(item: dict[str, Any], exclusions: list[str]) -> int:
    text = " ".join(
        str(value or "")
        for value in (
            item.get("company_name"),
            item.get("description"),
            item.get("industry"),
            item.get("address"),
            item.get("ranking_reason"),
            " ".join(str(source or "") for source in item.get("source_channels") or []),
        )
    ).lower()
    for evidence in item.get("evidence_items") or item.get("evidence") or []:
        if isinstance(evidence, dict):
            text += " " + " ".join(str(evidence.get(key) or "") for key in ("title", "snippet", "claim", "source"))
    penalty = 0
    if exclusions:
        for exclusion in exclusions:
            clean = str(exclusion or "").strip().lower()
            if clean and clean in text:
                penalty += 40
    clinic_markers = ("ordinary dental clinic", "general dental clinic", "phòng khám nha khoa", "คลินิกทันตกรรม", "klinik gigi", "dental clinic")
    if any(marker in text for marker in clinic_markers) and not any(term in text for term in ("school", "university", "distributor", "supplier", "dealer", "wholesale")):
        penalty += 35
    return min(penalty, 80)


def _previous_rank_bonus(item: dict[str, Any]) -> int:
    raw_rank = item.get("candidate_rank", item.get("rank"))
    try:
        rank = int(raw_rank or 0)
    except (TypeError, ValueError):
        return 0
    if rank <= 0:
        return 0
    return max(0, 24 - min(rank, 24))


def _ranking_reason(item: dict[str, Any], *, preferred: list[str], penalties: int) -> str:
    matched = item.get("matched_fields") or []
    missing = item.get("missing_fields") or []
    parts: list[str] = []
    if item.get("target_type"):
        parts.append(f"目标类型 {item.get('target_type')}：{item.get('target_type_reason', '')}")
    if item.get("goal_drift_flags"):
        parts.append("目标偏离 " + "、".join(str(flag) for flag in item.get("goal_drift_flags", [])[:3]))
    if item.get("region_reason"):
        parts.append(str(item.get("region_reason")))
    if matched:
        parts.append("命中 " + "、".join(_label(field) for field in matched))
    if missing:
        parts.append("可继续补全 " + "、".join(_label(field) for field in missing))
    if item.get("source_channels"):
        parts.append("来源 " + "、".join(str(source) for source in item.get("source_channels", [])[:4]))
    if preferred and not missing:
        parts.append("重点字段覆盖完整")
    if penalties:
        parts.append(f"业务规则扣分 {penalties}")
    return "；".join(parts) or "证据不足，保留在候选池继续补全"


def _label(field: str) -> str:
    return {
        "instagram": "Instagram",
        "facebook": "Facebook",
        "email": "邮箱",
        "phone": "电话",
        "website": "官网",
        "address": "地址",
    }.get(field, field)
