"""Merge deep-extracted lead profiles back into candidate rows."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


def merge_leads_into_candidates(candidates: list[dict[str, Any]], leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return candidate rows enriched with matching deep-extracted lead fields."""

    lead_index = _index_leads(leads)
    merged: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        item = dict(candidate)
        lead = _matching_lead(item, lead_index)
        if lead:
            item = _merge_profile(item, lead)
        item = _ensure_candidate_profile_summary(item)
        merged.append(item)
    return merged


def normalize_candidate_profiles(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure candidate rows have display-ready profile and evidence fields.

    Candidate rows can be produced by Maps, Tavily, Apify, website enrichment or
    LeadExtract. Each source uses slightly different evidence shapes. The UI and
    exporter need a single predictable profile surface, so this function fills
    conservative summaries and normalizes evidence without inventing facts.
    """

    return [_ensure_candidate_profile_summary(dict(candidate)) for candidate in candidates if isinstance(candidate, dict)]


def _index_leads(leads: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for lead in leads:
        if not isinstance(lead, dict):
            continue
        for key in _identity_keys(lead):
            index.setdefault(key, lead)
    return index


def _matching_lead(candidate: dict[str, Any], index: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    for key in _identity_keys(candidate):
        if key in index:
            return index[key]
    return None


def _identity_keys(row: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for value in (row.get("candidate_id"), row.get("lead_id"), row.get("id")):
        clean = _clean(value)
        if clean:
            keys.append(f"id:{clean.lower()}")
    domain = _domain(_clean(row.get("website")))
    if domain:
        keys.append(f"domain:{domain}")
    name = _name_key(_clean(row.get("company_name") or row.get("title")))
    if name:
        keys.append(f"name:{name}")
    emails = row.get("emails") if isinstance(row.get("emails"), list) else []
    for email in emails:
        clean = _clean(email).lower()
        if clean:
            keys.append(f"email:{clean}")
    return _dedupe(keys)


def _merge_profile(candidate: dict[str, Any], lead: dict[str, Any]) -> dict[str, Any]:
    item = dict(candidate)
    prefer_lead_fields = (
        "description", "industry", "business_types", "country_code", "country", "address",
        "contact_person", "decision_makers", "customs_data", "customs_records",
        "customer_role", "competitor_risk", "evidence_strength", "risk_flags",
        "fit_score", "match_score", "contactability_score", "customs_score", "priority_tier",
        "score_breakdown", "lead_grade", "jps_score", "scoring_version",
    )
    for key in prefer_lead_fields:
        if _has_value(lead.get(key)):
            item[key] = lead.get(key)

    for key in ("company_name", "website"):
        if not _has_value(item.get(key)) and _has_value(lead.get(key)):
            item[key] = lead.get(key)

    item["emails"] = _dedupe([*_list_values(item.get("emails")), *_list_values(lead.get("emails"))])
    item["phone_numbers"] = _dedupe([*_list_values(item.get("phone_numbers")), *_list_values(lead.get("phone_numbers"))])
    if item["emails"] and not _has_value(item.get("email")):
        item["email"] = item["emails"][0]
    if item["phone_numbers"] and not _has_value(item.get("phone")):
        item["phone"] = item["phone_numbers"][0]

    social = _merge_social(item.get("social_media"), lead.get("social_media"))
    for platform in ("instagram", "facebook", "linkedin"):
        direct_key = f"{platform}_url"
        value = _clean(lead.get(direct_key) or item.get(direct_key) or social.get(platform))
        if value:
            item[direct_key] = value
            social.setdefault(platform, value)
    item["social_media"] = social

    evidence_items = _list_dicts(item.get("evidence_items"))
    for ev in _list_dicts(lead.get("evidence")):
        evidence_items.append({
            "source": "lead_extract",
            "url": ev.get("source_url") or ev.get("url") or lead.get("website") or item.get("website") or "",
            "title": ev.get("title") or lead.get("company_name") or item.get("company_name") or "",
            "snippet": ev.get("claim") or ev.get("snippet") or "",
            "claim": ev.get("claim") or ev.get("snippet") or "",
            "source_url": ev.get("source_url") or ev.get("url") or "",
            "confidence": ev.get("confidence", 0.8),
        })
    item["evidence_items"] = _dedupe_evidence(evidence_items)
    item["evidence"] = _candidate_evidence_to_lead_evidence(item["evidence_items"])
    item["profile_enriched"] = True
    return item


def _ensure_candidate_profile_summary(item: dict[str, Any]) -> dict[str, Any]:
    item["evidence_items"] = _normalize_evidence_items(item)
    if not _has_value(item.get("description")):
        summary = _best_summary(item)
        if summary:
            item["description"] = summary
        else:
            item["description"] = _fallback_profile_summary(item)
    if not isinstance(item.get("evidence"), list) or not item.get("evidence"):
        item["evidence"] = _candidate_evidence_to_lead_evidence(_list_dicts(item.get("evidence_items")))
    item["evidence_count"] = len(_list_dicts(item.get("evidence_items")))
    item["social_media"] = _normalize_social_media(item)
    return item


def _normalize_evidence_items(item: dict[str, Any]) -> list[dict[str, Any]]:
    evidence_items = _list_dicts(item.get("evidence_items"))

    for ev in _list_dicts(item.get("evidence")):
        evidence_items.append(
            {
                "source": ev.get("source") or "lead_extract",
                "url": ev.get("source_url") or ev.get("url") or item.get("website") or "",
                "title": ev.get("title") or item.get("company_name") or item.get("title") or "公开来源证据",
                "snippet": ev.get("snippet") or ev.get("claim") or "",
                "claim": ev.get("claim") or ev.get("snippet") or "",
                "source_url": ev.get("source_url") or ev.get("url") or "",
                "confidence": ev.get("confidence", item.get("confidence", 0.5)),
            }
        )

    maps_data = item.get("maps_data") if isinstance(item.get("maps_data"), dict) else {}
    maps_url = _clean(maps_data.get("website") or item.get("website"))
    maps_text = _clean(maps_data.get("description") or maps_data.get("type") or maps_data.get("address"))
    if maps_data and (maps_url or maps_text):
        evidence_items.append(
            {
                "source": "google_maps",
                "url": maps_url,
                "title": _clean(maps_data.get("title") or item.get("company_name") or item.get("title")),
                "snippet": maps_text,
                "claim": maps_text or "Google Maps 公开资料识别该候选。",
                "source_url": maps_url,
                "confidence": item.get("confidence", 0.6),
            }
        )

    for platform in ("website", "linkedin_url", "facebook_url", "instagram_url"):
        url = _clean(item.get(platform))
        if not url:
            continue
        evidence_items.append(
            {
                "source": _source_label(platform),
                "url": url,
                "title": _clean(item.get("company_name") or item.get("title") or _source_label(platform)),
                "snippet": f"公开来源包含{_source_name(platform)}链接。",
                "claim": f"公开来源包含{_source_name(platform)}链接。",
                "source_url": url,
                "confidence": item.get("confidence", 0.5),
            }
        )

    if not evidence_items and _has_value(item.get("company_name") or item.get("title")):
        evidence_items.append(
            {
                "source": "candidate_pool",
                "url": _clean(item.get("website")),
                "title": _clean(item.get("company_name") or item.get("title")),
                "snippet": "该候选来自公开搜索结果，仍需要资料补全确认官网、联系方式和社媒。",
                "claim": "该候选来自公开搜索结果，仍需要资料补全确认官网、联系方式和社媒。",
                "source_url": _clean(item.get("website")),
                "confidence": item.get("confidence", 0.3),
            }
        )

    return _dedupe_evidence(evidence_items)


def _best_summary(item: dict[str, Any]) -> str:
    for value in (item.get("snippet"), item.get("maps_data", {}).get("description") if isinstance(item.get("maps_data"), dict) else ""):
        clean = _clean(value)
        if clean:
            return clean
    for ev in _list_dicts(item.get("evidence_items")):
        for key in ("snippet", "claim", "title"):
            clean = _clean(ev.get(key))
            if clean and not _is_generic_evidence_text(clean) and not _is_same_as_candidate_title(clean, item):
                return clean
    for value in (item.get("target_type_reason"), item.get("ranking_reason")):
        clean = _clean(value)
        if clean:
            return clean
    return ""


def _fallback_profile_summary(item: dict[str, Any]) -> str:
    name = _clean(item.get("company_name") or item.get("title")) or "该候选客户"
    target_type = _clean(item.get("target_type"))
    industry = _clean(item.get("industry"))
    country = _clean(item.get("country") or item.get("country_code"))
    parts = [f"{name} 来自公开搜索结果"]
    if target_type and target_type != "unknown":
        parts.append(f"目标类型识别为 {target_type}")
    if industry:
        parts.append(f"行业线索为 {industry}")
    if country:
        parts.append(f"地区线索为 {country}")
    parts.append("仍需结合官网、联系方式和社媒证据继续核验。")
    return "，".join(parts)


def _candidate_evidence_to_lead_evidence(evidence_items: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for ev in evidence_items:
        claim = _clean(ev.get("claim") or ev.get("snippet") or ev.get("title"))
        url = _clean(ev.get("source_url") or ev.get("url"))
        if not claim and not url:
            continue
        rows.append({"claim": claim or "公开来源证据", "source_url": url})
    return _dedupe_evidence(rows)[:20]


def _merge_social(left: Any, right: Any) -> dict[str, str]:
    merged: dict[str, str] = {}
    for source in (left, right):
        if isinstance(source, dict):
            for key, value in source.items():
                clean = _clean(value)
                if clean:
                    normalized = str(key).lower().replace("_url", "")
                    merged.setdefault(normalized, clean)
    return merged


def _normalize_social_media(item: dict[str, Any]) -> dict[str, str]:
    social = _merge_social(item.get("social_media"), {})
    for platform in ("instagram", "facebook", "linkedin"):
        direct = _clean(item.get(f"{platform}_url"))
        if direct:
            social.setdefault(platform, direct)
    return social


def _dedupe_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = "|".join(_clean(item.get(k)) for k in ("source_url", "url", "claim", "snippet", "title"))
        if not key.strip("|") or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _source_label(field: str) -> str:
    return {
        "website": "website",
        "linkedin_url": "linkedin",
        "facebook_url": "facebook",
        "instagram_url": "instagram",
    }.get(field, field)


def _source_name(field: str) -> str:
    return {
        "website": "官网",
        "linkedin_url": "LinkedIn",
        "facebook_url": "Facebook",
        "instagram_url": "Instagram",
    }.get(field, field)


def _is_generic_evidence_text(value: str) -> bool:
    text = value.strip().lower()
    return text in {
        "公开来源证据",
        "public source evidence",
        "search result",
        "website",
    } or text.startswith("公开来源包含")


def _is_same_as_candidate_title(value: str, item: dict[str, Any]) -> bool:
    title = _clean(item.get("company_name") or item.get("title")).lower()
    return bool(title and value.strip().lower() == title)


def _list_values(value: Any) -> list[str]:
    return [_clean(item) for item in value if _clean(item)] if isinstance(value, list) else []


def _list_dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _has_value(value: Any) -> bool:
    if isinstance(value, list):
        return any(_has_value(item) for item in value)
    if isinstance(value, dict):
        return bool(value)
    return bool(_clean(value))


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _domain(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = parsed.netloc.lower().split("@")[-1].split(":")[0]
    return host[4:] if host.startswith("www.") else host


def _name_key(value: str) -> str:
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value.lower())
    return text[:100]


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = _clean(value)
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result
