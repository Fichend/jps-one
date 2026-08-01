"""Standalone single-customer deep search service.

This module powers the front-end "深度搜索" workbench.  It intentionally reuses
the existing candidate deep-enrichment pipeline, then adds wider discovery
around the known official website with Serper and Apify social actors.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any
from urllib.parse import urlparse

from candidate_pool.calibration import apply_candidate_patch, auto_calibrate_candidate, candidate_identity
from candidate_pool.ranking import rank_candidates
from config.settings import Settings
from enrichment.deep_candidate_enricher import deep_enrich_candidate
from enrichment.tavily_deep_tools import tavily_research
from mcp_tools.search_adapters import ApifySocialSearchAdapter
from scoring.response_scoring import ensure_jps_scores
from tools.contact_extractor import extract_phone_numbers, extract_social_media, sanitize_phone_list
from tools.email_finder import extract_emails_from_text
from tools.google_maps_search import GoogleMapsSearchTool
from tools.google_search import GoogleSearchTool

logger = logging.getLogger(__name__)


async def run_standalone_deep_search(
    payload: dict[str, Any],
    *,
    hunt_id: str,
    settings: Settings,
) -> dict[str, Any]:
    """Run the strongest available single-website enrichment workflow."""

    website = _normalize_url(payload.get("website") or payload.get("website_url"))
    company_name = _text(payload.get("company_name")) or _company_name_from_url(website)
    country = _text(payload.get("country") or payload.get("country_code") or payload.get("region"))
    product_keywords = _string_list(payload.get("product_keywords"))
    max_depth = _bounded_int(payload.get("max_depth"), 2, 1, 3)
    max_pages = _bounded_int(payload.get("max_pages"), 45, 10, 60)

    candidate: dict[str, Any] = {
        "candidate_id": f"deep:{uuid.uuid4().hex[:16]}",
        "company_name": company_name,
        "website": website,
        "country": country,
        "country_code": country,
        "matched_product_keywords": product_keywords,
        "source": "standalone_deep_search",
        "source_channels": ["standalone_deep_search"],
        "candidate_status": "needs_enrichment",
    }

    warnings: list[str] = []
    trace: list[dict[str, Any]] = []

    deep_result = await deep_enrich_candidate(
        candidate,
        hunt={"hunt_id": hunt_id, "request": payload},
        settings=settings,
        mode=str(payload.get("mode") or "deep"),
        max_depth=max_depth,
        max_pages=max_pages,
    )
    if isinstance(deep_result.get("patch"), dict):
        apply_candidate_patch(
            candidate,
            deep_result["patch"],
            actor="deep_search_tavily",
            status="deep_search_enriched",
            notes="Tavily search/map/extract/crawl 深度搜索完成。",
            confidence=0.88,
            issues=_string_list(deep_result.get("warnings")),
        )
    _merge_metadata(candidate, deep_result)
    warnings.extend(_string_list(deep_result.get("warnings")))
    trace.extend(_trace_steps(deep_result, stage="tavily_deep"))

    # Company/country can improve after Tavily + LLM calibration, so build wider
    # follow-up queries from the current candidate snapshot.
    company_name = _text(candidate.get("company_name")) or company_name
    country = _text(candidate.get("country") or candidate.get("country_code") or country)
    website = _normalize_url(candidate.get("website") or website)

    research_query = " ".join(part for part in (company_name, country, website, "contact email social media company profile") if part)
    research_rows = await tavily_research(settings, research_query, model="mini")
    trace.append({"stage": "tavily_research", "tool": "tavily_research", "query": research_query, "items": len(research_rows)})
    _merge_external_rows(candidate, research_rows, source_label="Tavily Research")

    serper_result = await _run_serper_sweep(settings, company_name=company_name, country=country, website=website)
    _merge_external_rows(candidate, serper_result.get("rows", []), source_label="Serper Google/Maps")
    trace.extend(serper_result.get("trace", []))
    warnings.extend(serper_result.get("warnings", []))

    apify_result = await _run_apify_social_sweep(settings, company_name=company_name, country=country, website=website)
    _merge_external_rows(candidate, apify_result.get("rows", []), source_label="Apify Social")
    trace.extend(apify_result.get("trace", []))
    warnings.extend(apify_result.get("warnings", []))

    candidate = await auto_calibrate_candidate(candidate, hunt={"hunt_id": hunt_id, "request": payload}, settings=settings)
    candidate["source_channels"] = _dedupe_text([*(candidate.get("source_channels") or []), "tavily_deep", "serper", "apify_social"])
    candidate["deep_search_trace"] = trace[-80:]
    candidate["deep_search_summary"] = _summary(candidate, trace=trace, warnings=warnings)
    candidate["single_task_label"] = "单独任务"

    scored = ensure_jps_scores([candidate])
    ranked = rank_candidates(
        scored,
        target_final_leads=1,
        hard_filters={},
        exclusions=[],
        customer_types=_string_list(payload.get("customer_types") or payload.get("target_customer_profile")),
        product_keywords=product_keywords,
        target_regions=[country] if country else [],
    )
    final_candidate = ranked[0] if ranked else candidate

    return {
        "website_url": website,
        "description": _text(payload.get("description")) or f"单客户深度搜索：{company_name or website}",
        "product_keywords": product_keywords,
        "target_customer_profile": _text(payload.get("target_customer_profile") or payload.get("customer_type")),
        "target_regions": [country] if country else [],
        "target_lead_count": 1,
        "max_rounds": 1,
        "min_new_leads_threshold": 1,
        "search_sources": ["tavily_search", "tavily_map", "tavily_extract", "tavily_crawl", "tavily_research", "serper_search", "serper_maps", "apify_instagram", "apify_facebook"],
        "search_budget": {
            "final_leads": 1,
            "max_candidates": 1,
            "candidate_pool_enabled": True,
            "merge_multi_source_evidence": True,
        },
        "used_keywords": _dedupe_text([str(step.get("query") or "") for step in trace if isinstance(step, dict)]),
        "search_results": [],
        "candidate_pool": [final_candidate],
        "leads": [final_candidate],
        "rejected_candidates": [],
        "email_sequences": [],
        "hunt_round": 1,
        "current_stage": "completed",
        "deep_search": {
            "website": website,
            "company_name": company_name,
            "country": country,
            "trace": trace[-80:],
            "warnings": _dedupe_text(warnings),
            "candidate_id": candidate_identity(final_candidate),
        },
    }


async def _run_serper_sweep(settings: Settings, *, company_name: str, country: str, website: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    trace: list[dict[str, Any]] = []
    warnings: list[str] = []
    if not settings.serper_api_key:
        return {"rows": rows, "trace": trace, "warnings": ["未配置 Serper API Key，已跳过 Google/Maps 补强。"]}

    domain = _domain(website)
    queries = _dedupe_text([
        f'"{company_name}" contact email phone',
        f'"{company_name}" LinkedIn Instagram Facebook',
        f'"{company_name}" {country} official website',
        f"site:{domain} contact email phone" if domain else "",
        f"site:{domain} team staff faculty procurement" if domain else "",
    ])
    search_tool = GoogleSearchTool(settings=settings)
    try:
        for query in queries[:5]:
            try:
                found = await search_tool.search(query, num=8)
                trace.append({"stage": "serper", "tool": "serper_search", "query": query, "items": len(found)})
                rows.extend(_normalize_serper_rows(found, source="serper_search", query=query))
            except Exception as exc:
                warnings.append(f"Serper Search 失败：{str(exc)[:160]}")
                trace.append({"stage": "serper", "tool": "serper_search", "query": query, "status": "failed", "message": str(exc)[:160]})
    finally:
        await search_tool.close()

    if company_name:
        maps_tool = GoogleMapsSearchTool(settings=settings)
        maps_query = " ".join(part for part in (company_name, country) if part)
        try:
            found = await maps_tool.search(maps_query, num=10)
            trace.append({"stage": "serper", "tool": "serper_maps", "query": maps_query, "items": len(found)})
            rows.extend(_normalize_maps_rows(found, query=maps_query))
        except Exception as exc:
            warnings.append(f"Serper Maps 失败：{str(exc)[:160]}")
            trace.append({"stage": "serper", "tool": "serper_maps", "query": maps_query, "status": "failed", "message": str(exc)[:160]})
        finally:
            await maps_tool.close()
    return {"rows": rows, "trace": trace, "warnings": warnings}


async def _run_apify_social_sweep(settings: Settings, *, company_name: str, country: str, website: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    trace: list[dict[str, Any]] = []
    warnings: list[str] = []
    if not settings.apify_token or not company_name:
        return {"rows": rows, "trace": trace, "warnings": [] if settings.apify_token else ["未配置 Apify Token，已跳过社媒主页补强。"]}

    adapter = ApifySocialSearchAdapter(settings, budget={
        "apify_actor_max_items": min(max(int(settings.apify_actor_max_items or 20), 10), 30),
        "apify_actor_max_total_charge_usd": min(max(float(settings.apify_actor_max_total_charge_usd or 0.2), 0.2), 0.6),
        "apify_dataset_item_limit": min(max(int(settings.apify_dataset_item_limit or 20), 10), 30),
    })
    query = " ".join(part for part in (company_name, country) if part)
    try:
        found = await adapter.instagram_search(query, num=8)
        trace.append({"stage": "apify_social", "tool": "apify_instagram", "query": query, "items": len(found)})
        rows.extend(found)
    except Exception as exc:
        warnings.append(f"Apify Instagram 失败：{str(exc)[:160]}")
        trace.append({"stage": "apify_social", "tool": "apify_instagram", "query": query, "status": "failed", "message": str(exc)[:160]})
    try:
        found = await adapter.facebook_search(query, num=8)
        trace.append({"stage": "apify_social", "tool": "apify_facebook", "query": query, "items": len(found)})
        rows.extend(found)
    except Exception as exc:
        warnings.append(f"Apify Facebook 失败：{str(exc)[:160]}")
        trace.append({"stage": "apify_social", "tool": "apify_facebook", "query": query, "status": "failed", "message": str(exc)[:160]})
    return {"rows": rows, "trace": trace, "warnings": warnings}


def _merge_external_rows(candidate: dict[str, Any], rows: list[dict[str, Any]], *, source_label: str) -> None:
    if not rows:
        return
    current_evidence = candidate.get("evidence_items") if isinstance(candidate.get("evidence_items"), list) else []
    current_urls = _string_list(candidate.get("evidence_urls"))
    social = candidate.get("social_media") if isinstance(candidate.get("social_media"), dict) else {}
    emails: list[str] = _string_list(candidate.get("emails"))
    phones: list[str] = _string_list(candidate.get("phone_numbers"))
    address = _text(candidate.get("address"))
    website = _normalize_url(candidate.get("website"))

    for row in rows:
        if not isinstance(row, dict):
            continue
        url = _normalize_url(row.get("link") or row.get("url") or row.get("website"))
        text = "\n".join(_text(row.get(key)) for key in ("title", "snippet", "description", "address") if _text(row.get(key)))
        emails.extend(extract_emails_from_text(text))
        phones.extend(extract_phone_numbers(text))
        phones.extend(_string_list(row.get("phone_numbers") or row.get("phone_number") or row.get("phone")))
        social.update(extract_social_media("\n".join([text, url])))
        if not address and _text(row.get("address")):
            address = _text(row.get("address"))
        if not website and _looks_official_candidate_url(url):
            website = url
        if url:
            current_urls.append(url)
            current_evidence.append({
                "source": _text(row.get("source")) or source_label,
                "url": url,
                "source_url": url,
                "title": _text(row.get("title")) or source_label,
                "claim": _evidence_claim(row, source_label=source_label),
                "snippet": text[:700],
                "confidence": 0.78,
            })

    patch: dict[str, Any] = {
        "emails": _dedupe_text(emails)[:20],
        "phone_numbers": sanitize_phone_list(_dedupe_text(phones))[:15],
        "social_media": {key: value for key, value in social.items() if value},
        "evidence_urls": _dedupe_text(current_urls)[:40],
        "evidence_summary": _append_summary(_text(candidate.get("evidence_summary")), f"{source_label} 补充 {len(rows)} 条外部证据。"),
    }
    if website:
        patch["website"] = website
    if address:
        patch["address"] = address
    apply_candidate_patch(candidate, patch, actor="deep_search_external", status="deep_search_external_enriched", notes=f"{source_label} 补强完成。", confidence=0.78)
    candidate["evidence_items"] = _dedupe_evidence([*current_evidence])[:80]


def _merge_metadata(candidate: dict[str, Any], enrichment: dict[str, Any]) -> None:
    for key in ("email_candidates", "contacts", "evidence_items"):
        if isinstance(enrichment.get(key), list):
            target = "decision_makers" if key == "contacts" else key
            candidate[target] = _dedupe_dicts([*(candidate.get(target) if isinstance(candidate.get(target), list) else []), *enrichment[key]])
    if isinstance(enrichment.get("summary"), dict):
        candidate["deep_enrichment_summary"] = enrichment["summary"]
    if isinstance(enrichment.get("deep_enrichment_trace"), list):
        candidate["deep_enrichment_trace"] = [{"steps": enrichment["deep_enrichment_trace"]}]


def _trace_steps(enrichment: dict[str, Any], *, stage: str) -> list[dict[str, Any]]:
    steps = enrichment.get("deep_enrichment_trace") if isinstance(enrichment.get("deep_enrichment_trace"), list) else []
    return [{**step, "stage": stage} for step in steps if isinstance(step, dict)]


def _normalize_serper_rows(rows: list[dict[str, Any]], *, source: str, query: str) -> list[dict[str, Any]]:
    result = []
    for index, row in enumerate(rows, start=1):
        result.append({
            "title": row.get("title", ""),
            "link": row.get("link", ""),
            "snippet": row.get("snippet", ""),
            "position": row.get("position") or index,
            "source": source,
            "source_keyword": query,
        })
    return result


def _normalize_maps_rows(rows: list[dict[str, Any]], *, query: str) -> list[dict[str, Any]]:
    result = []
    for index, row in enumerate(rows, start=1):
        result.append({
            "title": row.get("title", ""),
            "link": row.get("website", ""),
            "website": row.get("website", ""),
            "snippet": row.get("description", ""),
            "address": row.get("address", ""),
            "phone_numbers": [row.get("phone_number", "")] if row.get("phone_number") else [],
            "position": index,
            "source": "serper_maps",
            "source_keyword": query,
        })
    return result


def _evidence_claim(row: dict[str, Any], *, source_label: str) -> str:
    if row.get("source") == "serper_maps":
        bits = []
        if row.get("address"):
            bits.append(f"地址 {row.get('address')}")
        phones = row.get("phone_numbers") if isinstance(row.get("phone_numbers"), list) else []
        if phones:
            bits.append(f"电话 {phones[0]}")
        return "；".join(bits) or f"{source_label} 地图结果指向该客户。"
    if "instagram" in str(row.get("source", "")).lower():
        return "Apify 发现疑似 Instagram 公开主页。"
    if "facebook" in str(row.get("source", "")).lower():
        return "Apify 发现疑似 Facebook 公开主页。"
    return f"{source_label} 发现与该客户相关的公开页面。"


def _summary(candidate: dict[str, Any], *, trace: list[dict[str, Any]], warnings: list[str]) -> dict[str, Any]:
    emails = _string_list(candidate.get("emails"))
    phones = _string_list(candidate.get("phone_numbers"))
    social = candidate.get("social_media") if isinstance(candidate.get("social_media"), dict) else {}
    evidence = candidate.get("evidence_items") if isinstance(candidate.get("evidence_items"), list) else []
    by_tool: dict[str, dict[str, int]] = {}
    for step in trace:
        tool = _text(step.get("tool")) or "unknown"
        bucket = by_tool.setdefault(tool, {"calls": 0, "items": 0})
        bucket["calls"] += 1
        try:
            bucket["items"] += int(step.get("items") or 0)
        except (TypeError, ValueError):
            pass
    return {
        "emails_found": len(emails),
        "phones_found": len(phones),
        "social_links_found": len([value for value in social.values() if value]),
        "evidence_count": len(evidence),
        "tools": by_tool,
        "warnings": _dedupe_text(warnings),
    }


def _append_summary(current: str, addition: str) -> str:
    if not current:
        return addition
    if addition in current:
        return current
    return f"{current}{addition}"


def _looks_official_candidate_url(url: str) -> bool:
    domain = _domain(url)
    blocked = ("facebook.com", "instagram.com", "linkedin.com", "tiktok.com", "youtube.com", "google.", "maps.google")
    return bool(domain and not any(marker in domain for marker in blocked))


def _normalize_url(value: Any) -> str:
    raw = _text(value)
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    return raw


def _domain(url: str) -> str:
    raw = _normalize_url(url)
    if not raw:
        return ""
    parsed = urlparse(raw)
    return (parsed.netloc or parsed.path.split("/")[0]).lower().removeprefix("www.")


def _company_name_from_url(url: str) -> str:
    domain = _domain(url)
    if not domain:
        return ""
    stem = domain.split(".")[0]
    return " ".join(part.capitalize() for part in re.split(r"[-_]", stem) if part)


def _bounded_int(value: Any, default: int, floor: int, ceiling: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(floor, min(parsed, ceiling))


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = re.split(r"[;,，\n]", value)
    elif isinstance(value, list):
        raw = value
    else:
        raw = []
    return _dedupe_text([_text(item) for item in raw])


def _dedupe_text(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = _text(value)
        if not clean or clean.lower() in seen:
            continue
        seen.add(clean.lower())
        result.append(clean)
    return result


def _dedupe_dicts(values: list[Any]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        key = repr((value.get("email"), value.get("source_url") or value.get("url"), value.get("name")))
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(value))
    return result


def _dedupe_evidence(values: list[Any]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        key = repr((value.get("source_url") or value.get("url"), str(value.get("claim") or "")[:120]))
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(value))
    return result


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
