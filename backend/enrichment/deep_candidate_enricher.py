"""On-demand deep enrichment for one candidate customer."""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

from config.settings import Settings
from enrichment.email_quality import best_email, rank_email_candidates
from enrichment.tavily_deep_tools import tavily_crawl, tavily_extract, tavily_map, tavily_search
from tools.contact_extractor import extract_phone_numbers, extract_social_media, sanitize_phone_list
from tools.email_finder import extract_emails_from_text
from tools.llm_client import LLMTool
from tools.llm_output import parse_json

logger = logging.getLogger(__name__)


HIGH_VALUE_PATH_MARKERS = (
    "contact", "about", "team", "staff", "faculty", "department", "admission", "international",
    "procurement", "purchase", "supplier", "dealer", "distributor", "support", "impressum", "office",
    "ติดต่อ", "บุคลากร", "คณะ", "หน่วยงาน",
)
BLOCKED_HOST_MARKERS = (
    "facebook.com", "instagram.com", "linkedin.com", "youtube.com", "google.", "maps.google", "researchgate.net",
    "academia.edu", "reddit.com", "wikipedia.org", "yelp.", "tripadvisor.",
)


async def deep_enrich_candidate(
    candidate: dict[str, Any],
    *,
    hunt: dict[str, Any],
    settings: Settings,
    mode: str = "deep",
    max_depth: int = 2,
    max_pages: int = 30,
) -> dict[str, Any]:
    """Return a safe enrichment patch plus evidence for one candidate."""

    if not settings.tavily_api_key:
        return _empty_response(candidate, warnings=["未配置 Tavily API Key，无法执行深度补全。"])

    company_name = _text(candidate.get("company_name") or candidate.get("title") or candidate.get("name"))
    country = _text(candidate.get("country") or candidate.get("country_code") or candidate.get("region"))
    website = _normalize_url(candidate.get("website") or candidate.get("url") or candidate.get("link"))
    trace: list[dict[str, Any]] = []
    warnings: list[str] = []

    if not website or not _looks_like_official_website(website):
        website = await _discover_official_website(settings, company_name, country, trace)
    if not website:
        return _empty_response(candidate, warnings=["没有可信官网，无法进行官网深度补全。"], trace=trace)

    search_rows = await _run_search_sweep(settings, company_name, country, website, trace)
    mapped_urls = await tavily_map(settings, website, max_pages=max(20, min(int(max_pages) * 2, 80)))
    trace.append({"tool": "tavily_map", "query": website, "items": len(mapped_urls)})

    target_urls = _select_target_urls(website, mapped_urls, search_rows, max_urls=max(8, min(int(max_pages), 35)))
    extracted_rows = await tavily_extract(settings, target_urls[:20])
    trace.append({"tool": "tavily_extract", "query": f"{len(target_urls[:20])} selected urls", "items": len(extracted_rows)})

    crawl_rows = await tavily_crawl(settings, website, max_depth=max_depth, max_pages=max_pages)
    trace.append({"tool": "tavily_crawl", "query": website, "items": len(crawl_rows), "max_depth": max_depth, "max_pages": max_pages})

    evidence_rows = _dedupe_rows([*search_rows, *extracted_rows, *crawl_rows])
    signals = _extract_signals(evidence_rows, website=website)
    llm_fields = await _llm_refine(candidate, hunt=hunt, settings=settings, evidence_rows=evidence_rows[:12])
    if llm_fields.get("warnings"):
        warnings.extend([_text(item) for item in llm_fields.get("warnings", []) if _text(item)])

    email_candidates = rank_email_candidates(signals["email_candidates"], website=website)
    phones = sanitize_phone_list([*signals["phones"], *_string_list(llm_fields.get("phone_numbers"))])[:10]
    social = {**signals["social_media"], **_dict_of_text(llm_fields.get("social_media"))}
    contacts = _merge_contacts(signals["contacts"], llm_fields.get("contacts"))
    evidence_items = _evidence_items(evidence_rows, email_candidates=email_candidates, phones=phones, social=social)[:20]

    existing_emails = _string_list(candidate.get("emails")) + ([_text(candidate.get("email"))] if _text(candidate.get("email")) else [])
    merged_emails = _dedupe_text([*existing_emails, *[item["email"] for item in email_candidates]])[:12]
    selected_email = _text(candidate.get("email")) or best_email(email_candidates)

    patch: dict[str, Any] = {
        "website": website,
        "emails": merged_emails,
        "phone_numbers": _dedupe_text([*_string_list(candidate.get("phone_numbers")), *phones])[:10],
        "social_media": social,
        "linkedin_url": social.get("linkedin", ""),
        "instagram_url": social.get("instagram", ""),
        "facebook_url": social.get("facebook", ""),
        "x_url": social.get("x") or social.get("twitter", ""),
        "evidence_urls": _dedupe_text([_text(item.get("source_url") or item.get("url")) for item in evidence_items])[:20],
        "evidence_summary": _summary(company_name, email_candidates, phones, social, evidence_items),
    }
    if selected_email:
        patch["email"] = selected_email
    if phones and not _text(candidate.get("phone")):
        patch["phone"] = phones[0]
    description = _text(llm_fields.get("description") or "")
    if description and _can_update_description(candidate):
        patch["description"] = description[:900]

    return {
        "patch": {key: value for key, value in patch.items() if value not in (None, "", [], {})},
        "summary": {
            "emails_found": len(email_candidates),
            "phones_found": len(phones),
            "contacts_found": len(contacts),
            "social_links_found": len([value for value in social.values() if value]),
            "pages_checked": len(evidence_rows),
            "recommended_email": selected_email,
            "updated_fields": [],
        },
        "email_candidates": email_candidates,
        "contacts": contacts,
        "evidence_items": evidence_items,
        "deep_enrichment_trace": trace,
        "warnings": warnings,
    }


async def _discover_official_website(settings: Settings, company_name: str, country: str, trace: list[dict[str, Any]]) -> str:
    if not company_name:
        return ""
    query = " ".join(part for part in (company_name, country, "official website contact") if part)
    rows = await tavily_search(settings, query, num=8)
    trace.append({"tool": "tavily_search", "query": query, "items": len(rows), "purpose": "official_website"})
    for row in rows:
        url = _normalize_url(row.get("link") or row.get("url"))
        if url and _looks_like_official_website(url):
            return url
    return ""


async def _run_search_sweep(settings: Settings, company_name: str, country: str, website: str, trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    domain = _domain(website)
    queries = _dedupe_text([
        f'"{company_name}" email contact',
        f'"{company_name}" sales admissions procurement email',
        f"site:{domain} email contact",
        f"site:{domain} staff faculty department contact",
        f"site:{domain} procurement admissions international",
    ])
    rows: list[dict[str, Any]] = []
    for query in queries[:5]:
        try:
            found = await tavily_search(settings, query, num=6)
            trace.append({"tool": "tavily_search", "query": query, "items": len(found)})
            rows.extend(found)
        except Exception as exc:
            trace.append({"tool": "tavily_search", "query": query, "status": "failed", "message": str(exc)[:160]})
    return rows


def _select_target_urls(website: str, mapped_urls: list[str], search_rows: list[dict[str, Any]], *, max_urls: int) -> list[str]:
    urls = [website]
    urls.extend(_common_contact_urls(website))
    urls.extend(mapped_urls)
    urls.extend([_text(row.get("link") or row.get("url")) for row in search_rows])
    scored = []
    root_domain = _domain(website)
    for url in _dedupe_text([_normalize_url(item) for item in urls]):
        if not url or (root_domain and _domain(url) != root_domain):
            continue
        low = url.lower()
        score = 10 if url.rstrip("/") == website.rstrip("/") else 0
        score += sum(8 for marker in HIGH_VALUE_PATH_MARKERS if marker in low)
        if low.endswith(".pdf"):
            score += 6
        scored.append((score, url))
    return [url for _, url in sorted(scored, key=lambda item: (-item[0], len(item[1])))[:max_urls]]


def _extract_signals(rows: list[dict[str, Any]], *, website: str) -> dict[str, Any]:
    email_candidates: list[dict[str, Any]] = []
    phones: list[str] = []
    social: dict[str, str] = {}
    contacts: list[dict[str, str]] = []
    for row in rows:
        url = _text(row.get("link") or row.get("url") or row.get("source_url") or website)
        text = _row_text(row)
        for email in extract_emails_from_text(text):
            email_candidates.append({"email": email, "source_url": url})
            context = _email_context(text, email)
            contacts.extend(_contacts_from_email_context(email, context, url))
        phones.extend(extract_phone_numbers(text))
        social.update(extract_social_media(text))
    return {"email_candidates": email_candidates, "phones": phones, "social_media": social, "contacts": contacts}


async def _llm_refine(candidate: dict[str, Any], *, hunt: dict[str, Any], settings: Settings, evidence_rows: list[dict[str, Any]]) -> dict[str, Any]:
    compact_pages = [
        {"url": _text(row.get("link") or row.get("url")), "title": _text(row.get("title")), "text": _row_text(row)[:1400]}
        for row in evidence_rows[:10]
    ]
    if not compact_pages:
        return {}
    llm = LLMTool(model_type="reasoning", settings=settings, hunt_id=str(hunt.get("hunt_id") or ""), agent="deep_candidate_enrichment")
    try:
        raw = await llm.generate(
            "请从公开网页证据中校准客户资料。不要编造，不要把介绍当公司名。返回 JSON。\n\n"
            f"candidate={json.dumps(candidate, ensure_ascii=False, default=str)[:3000]}\n\n"
            f"pages={json.dumps(compact_pages, ensure_ascii=False, default=str)}\n\n"
            "JSON schema: {\"description\":\"企业/机构一句话介绍\",\"phone_numbers\":[\"...\"],"
            "\"social_media\":{\"linkedin\":\"\",\"instagram\":\"\",\"facebook\":\"\",\"x\":\"\"},"
            "\"contacts\":[{\"name\":\"\",\"title\":\"\",\"email\":\"\",\"source_url\":\"\"}],\"warnings\":[]}",
            system="你是 JPS-One 客户官网深度补全助手，只抽取有来源的公开事实。",
            temperature=0.05,
            max_tokens=1400,
            response_format={"type": "json_object"},
            timeout_seconds=60,
        )
        parsed = parse_json(raw, context="DeepCandidateEnrichment")
        return parsed if isinstance(parsed, dict) else {}
    except Exception as exc:
        logger.info("[DeepEnrich] LLM refine skipped: %s", exc)
        return {"warnings": ["LLM 校准失败，已使用规则抽取结果。"]}
    finally:
        await llm.close()


def _evidence_items(rows: list[dict[str, Any]], *, email_candidates: list[dict[str, Any]], phones: list[str], social: dict[str, str]) -> list[dict[str, Any]]:
    signal_urls = {_text(item.get("source_url")) for item in email_candidates if _text(item.get("source_url"))}
    items: list[dict[str, Any]] = []
    for row in rows:
        url = _text(row.get("link") or row.get("url") or row.get("source_url"))
        text = _row_text(row)
        if not url or (url not in signal_urls and not any(value and value in text for value in phones) and not any(value and value in text for value in social.values())):
            continue
        claim_bits = []
        emails = [item["email"] for item in email_candidates if item.get("source_url") == url][:3]
        if emails:
            claim_bits.append("邮箱 " + ", ".join(emails))
        page_phones = [phone for phone in phones if phone in text][:2]
        if page_phones:
            claim_bits.append("电话 " + ", ".join(page_phones))
        page_social = [platform for platform, value in social.items() if value and value in text]
        if page_social:
            claim_bits.append("社媒 " + ", ".join(page_social))
        items.append({
            "source": _text(row.get("source")) or "deep_enrichment",
            "url": url,
            "source_url": url,
            "title": _text(row.get("title")) or "官网补全证据",
            "claim": "；".join(claim_bits) or "官网公开页面包含客户补全信号。",
            "snippet": text[:500],
            "confidence": 0.86,
        })
    return _dedupe_evidence(items)


def _summary(company_name: str, emails: list[dict[str, Any]], phones: list[str], social: dict[str, str], evidence: list[dict[str, Any]]) -> str:
    bits = []
    if emails:
        bits.append(f"发现 {len(emails)} 个邮箱，推荐 {emails[0].get('email')}（{emails[0].get('grade')}级）。")
    if phones:
        bits.append(f"发现 {len(phones)} 个电话。")
    if social:
        bits.append("发现社媒：" + "、".join(sorted(social.keys())) + "。")
    bits.append(f"新增 {len(evidence)} 条可追溯官网证据。")
    return "".join(bits) or f"已对 {company_name or '该客户'} 官网执行深度补全。"


def _empty_response(candidate: dict[str, Any], *, warnings: list[str], trace: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "patch": {},
        "summary": {"emails_found": 0, "phones_found": 0, "contacts_found": 0, "social_links_found": 0, "pages_checked": 0, "recommended_email": "", "updated_fields": []},
        "email_candidates": [],
        "contacts": [],
        "evidence_items": [],
        "deep_enrichment_trace": trace or [],
        "warnings": warnings,
    }


def _common_contact_urls(website: str) -> list[str]:
    root = website.rstrip("/")
    return [f"{root}/{path}" for path in ("contact", "contact-us", "about", "about-us", "team", "staff", "faculty", "department", "admissions", "international", "procurement", "support")]


def _contacts_from_email_context(email: str, context: str, source_url: str) -> list[dict[str, str]]:
    contacts: list[dict[str, str]] = []
    local = email.split("@", 1)[0]
    if "." in local and not any(token in local for token in ("info", "sales", "contact", "admin")):
        name = " ".join(part.capitalize() for part in re.split(r"[._\-]", local) if part)
        contacts.append({"name": name, "title": "", "email": email, "source_url": source_url})
    title_match = re.search(r"(Director|Manager|Dean|Professor|Admissions|Procurement|Sales|International[^,.;\n]{0,40})", context, re.I)
    if title_match and contacts:
        contacts[0]["title"] = title_match.group(0).strip()
    return contacts


def _email_context(text: str, email: str) -> str:
    index = text.lower().find(email.lower())
    if index < 0:
        return ""
    return text[max(0, index - 220): index + 220]


def _merge_contacts(rule_contacts: list[dict[str, str]], llm_contacts: Any) -> list[dict[str, str]]:
    contacts = [item for item in rule_contacts if isinstance(item, dict)]
    if isinstance(llm_contacts, list):
        contacts.extend([item for item in llm_contacts if isinstance(item, dict)])
    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for item in contacts:
        email = _text(item.get("email")).lower()
        name = _text(item.get("name"))
        key = email or name.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append({"name": name, "title": _text(item.get("title")), "email": email, "source_url": _text(item.get("source_url"))})
    return result[:8]


def _row_text(row: dict[str, Any]) -> str:
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    raw = evidence.get("raw") if isinstance(evidence.get("raw"), dict) else {}
    return "\n".join(_text(value) for value in (row.get("title"), row.get("snippet"), raw.get("raw_content"), raw.get("content"), raw.get("text")) if _text(value))


def _looks_like_official_website(url: str) -> bool:
    host = _domain(url)
    return bool(host and not any(marker in host for marker in BLOCKED_HOST_MARKERS))


def _normalize_url(value: Any) -> str:
    raw = _text(value)
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    return raw


def _domain(url: str) -> str:
    raw = _normalize_url(url)
    parsed = urlparse(raw)
    return (parsed.netloc or parsed.path.split("/")[0]).lower().removeprefix("www.")


def _can_update_description(candidate: dict[str, Any]) -> bool:
    status = _text(candidate.get("calibration_status")).lower()
    current = _text(candidate.get("description") or candidate.get("company_summary"))
    return "manual" not in status and (not current or current.startswith("Prospective buyer") or len(current) < 80)


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = _text(row.get("link") or row.get("url") or row.get("title")).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _dedupe_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = (_text(item.get("source_url") or item.get("url")), _text(item.get("claim"))[:80])
        marker = repr(key)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(item)
    return result


def _dedupe_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = _text(value)
        if not clean or clean.lower() in seen:
            continue
        seen.add(clean.lower())
        result.append(clean)
    return result


def _dict_of_text(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    result = {}
    for key, raw in value.items():
        clean_key = _text(key).lower()
        clean_value = _text(raw)
        if clean_key == "twitter":
            clean_key = "x"
        if clean_key in {"linkedin", "instagram", "facebook", "x"} and clean_value:
            result[clean_key] = clean_value
    return result


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = re.split(r"[;,，\n]", value)
    elif isinstance(value, list):
        raw = value
    else:
        raw = []
    return _dedupe_text([_text(item) for item in raw])


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
