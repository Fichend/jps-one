"""Build email-ready contact profiles from hunt candidates.

This layer intentionally sits between customer discovery and campaign sending:
hunts can return noisy or incomplete leads, while email sending needs a stable
per-customer variable map and clear sendability status.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from api.hunt_store import load_hunt, now_iso
from emailing.contact_sync import sync_contact_profile_selection_to_hunt, sync_contact_profile_to_hunt
from emailing.email_content_profile import DEFAULT_PRODUCT_PITCH
from emailing.policy import expand_email_targets
from emailing.store import EmailStore


SOCIAL_KEYS = ("linkedin", "instagram", "facebook", "x", "twitter")
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
EMAIL_BLOCKLIST_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js")


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _stable_id(*parts: Any) -> str:
    raw = "|".join(_text(part).lower() for part in parts if _text(part))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


def _first(values: list[Any] | tuple[Any, ...]) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def _emails(lead: dict[str, Any]) -> list[str]:
    values = []
    if _text(lead.get("email")):
        values.append(_text(lead.get("email")))
    values.extend(_text(item) for item in _as_list(lead.get("emails")))
    result: list[str] = []
    seen: set[str] = set()
    for email in values:
        normalized = email.strip().lower()
        if "@" not in normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _valid_email(value: str) -> bool:
    email = _text(value).lower()
    if not EMAIL_RE.fullmatch(email):
        return False
    return not email.endswith(EMAIL_BLOCKLIST_SUFFIXES)


def _normalize_email(value: str) -> str:
    email = _text(value).lower().strip(".,;:()[]{}<>")
    return email if _valid_email(email) else ""


def _phones(lead: dict[str, Any]) -> list[str]:
    values = []
    if _text(lead.get("phone")):
        values.append(_text(lead.get("phone")))
    values.extend(_text(item) for item in _as_list(lead.get("phone_numbers")))
    seen: set[str] = set()
    result: list[str] = []
    for phone in values:
        if phone and phone not in seen:
            seen.add(phone)
            result.append(phone)
    return result


def _social(lead: dict[str, Any]) -> dict[str, str]:
    social = dict(_as_dict(lead.get("social_media")))
    for profile in _as_list(lead.get("social_profiles")):
        item = _as_dict(profile)
        platform = _text(item.get("platform") or item.get("type")).lower()
        url = _text(item.get("url") or item.get("link"))
        if platform and url:
            social[platform] = url
    for key in SOCIAL_KEYS:
        direct = _text(lead.get(f"{key}_url"))
        if direct:
            social[key] = direct
    if "twitter" in social and "x" not in social:
        social["x"] = social["twitter"]
    return {str(k).lower(): _text(v) for k, v in social.items() if _text(v)}


def _evidence(lead: dict[str, Any]) -> tuple[str, list[str]]:
    items = _as_list(lead.get("evidence_items")) or _as_list(lead.get("evidence"))
    snippets: list[str] = []
    urls: list[str] = []
    for raw in items:
        item = _as_dict(raw)
        snippet = _first([item.get("claim"), item.get("snippet"), item.get("summary"), item.get("title")])
        url = _first([item.get("source_url"), item.get("url"), item.get("link")])
        if snippet:
            snippets.append(snippet)
        if url and url not in urls:
            urls.append(url)
    if not snippets:
        fallback = _first([lead.get("ranking_reason"), lead.get("target_type_reason"), lead.get("description")])
        if fallback:
            snippets.append(fallback)
    return "；".join(snippets[:3]), urls[:8]


def _company_summary(lead: dict[str, Any]) -> str:
    return _first([
        lead.get("ai_profile_summary"),
        lead.get("company_summary"),
        lead.get("description"),
        lead.get("target_type_reason"),
        lead.get("ranking_reason"),
    ])


def _language(lead: dict[str, Any], hunt: dict[str, Any]) -> str:
    explicit = _text(lead.get("language") or lead.get("locale"))
    if explicit:
        return explicit
    region = " ".join(_as_list(hunt.get("target_regions")) + _as_list((_as_dict(hunt.get("request"))).get("target_regions"))).lower()
    if any(token in region for token in ["china", "中国"]):
        return "zh"
    if any(token in region for token in ["thailand", "thai", "泰国"]):
        return "en"
    if any(token in region for token in ["vietnam", "越南"]):
        return "en"
    return "en"


def _candidate_source(hunt: dict[str, Any]) -> list[dict[str, Any]]:
    result = _as_dict(hunt.get("result"))
    candidates = _as_list(result.get("candidate_pool"))
    if candidates:
        return [_as_dict(item) for item in candidates if isinstance(item, dict)]
    return [_as_dict(item) for item in _as_list(result.get("leads")) if isinstance(item, dict)]


def build_profile(hunt_id: str, hunt: dict[str, Any], lead: dict[str, Any], *, created_at: str | None = None) -> dict[str, Any]:
    current = now_iso()
    created = created_at or current
    company_name = _first([lead.get("company_name"), lead.get("name"), lead.get("title"), "Unknown company"])
    website = _first([lead.get("website"), lead.get("url"), lead.get("link")])
    candidate_id = _first([lead.get("candidate_id"), lead.get("id"), lead.get("lead_id")])
    if not candidate_id:
        candidate_id = _stable_id(hunt_id, company_name, website, _first(_emails(lead)))
    profile_id = _stable_id("email-profile", hunt_id, candidate_id)
    targets = [item for item in expand_email_targets(lead) if _text(item.get("target_email"))]
    target = targets[0] if targets else {}
    email = _text(target.get("target_email") or _first(_emails(lead))).lower()
    social = _social(lead)
    evidence_summary, evidence_urls = _evidence(lead)
    products = [_text(item) for item in _as_list(lead.get("matched_product_keywords")) if _text(item)]
    if not products:
        products = [_text(item) for item in _as_list((_as_dict(hunt.get("request"))).get("product_keywords")) if _text(item)]
    risk_flags = [_text(item) for item in _as_list(lead.get("ai_risk_flags")) if _text(item)]
    if not email:
        send_eligibility = "missing_email"
        skip_reason = "缺少可发送邮箱"
    elif "@" not in email:
        send_eligibility = "invalid_email"
        skip_reason = "邮箱格式无效"
    else:
        send_eligibility = "sendable"
        skip_reason = ""
    variables = {
        "company_name": company_name,
        "recipient_email": email,
        "recipient_name": _text(target.get("target_name") or lead.get("contact_person")),
        "recipient_title": _text(target.get("target_title")),
        "recipient_type": _text(target.get("target_type")),
        "website": website,
        "country_or_region": _first([lead.get("country_code"), lead.get("country"), lead.get("region")]),
        "customer_type": _first([lead.get("customer_role"), lead.get("customer_type"), lead.get("industry")]),
        "target_type": _text(lead.get("target_type")),
        "company_summary": _company_summary(lead),
        "jps_fit_reason": _first([lead.get("ai_fit_assessment"), lead.get("ranking_reason"), lead.get("target_type_reason")]),
        "matched_product_keywords": ", ".join(products),
        "product_pitch": ", ".join(products) or DEFAULT_PRODUCT_PITCH,
        "customer_public_summary": _company_summary(lead),
        "public_fit_sentence": "Their public information suggests a possible fit for dental education or training equipment.",
        "evidence_summary": evidence_summary,
        "website_or_evidence_url": website or _first(evidence_urls),
        "phone": _first(_phones(lead)),
        "linkedin_url": social.get("linkedin", ""),
        "instagram_url": social.get("instagram", ""),
        "facebook_url": social.get("facebook", ""),
        "x_url": social.get("x", ""),
    }
    selected_for_outreach = bool(lead.get("selected_for_outreach"))
    return {
        "id": profile_id,
        "hunt_id": hunt_id,
        "candidate_id": candidate_id,
        "lead_id": _text(lead.get("lead_id")),
        "company_name": company_name,
        "recipient_email": email,
        "recipient_name": variables["recipient_name"],
        "recipient_title": variables["recipient_title"],
        "recipient_type": variables["recipient_type"],
        "website": website,
        "country_or_region": variables["country_or_region"],
        "customer_type": variables["customer_type"],
        "target_type": variables["target_type"],
        "company_summary": variables["company_summary"],
        "jps_fit_reason": variables["jps_fit_reason"],
        "matched_product_keywords_json": _json(products),
        "evidence_summary": evidence_summary,
        "evidence_urls_json": _json(evidence_urls),
        "phone": variables["phone"],
        "linkedin_url": variables["linkedin_url"],
        "instagram_url": variables["instagram_url"],
        "facebook_url": variables["facebook_url"],
        "x_url": variables["x_url"],
        "language": _language(lead, hunt),
        "send_eligibility": send_eligibility,
        "skip_reason": skip_reason,
        "risk_flags_json": _json(risk_flags),
        "variables_json": _json(variables),
        "lead_snapshot_json": _json(lead),
        "selected_for_outreach": 1 if selected_for_outreach else 0,
        "selection_source": _text(lead.get("selection_source")) if selected_for_outreach else "",
        "selected_at": _text(lead.get("selected_at")) if selected_for_outreach else "",
        "calibration_status": _text(lead.get("calibration_status")),
        "calibration_notes": _text(lead.get("calibration_notes")),
        "calibration_confidence": float(lead.get("calibration_confidence") or 0),
        "created_at": created,
        "updated_at": current,
    }


def extract_profiles_for_hunt(hunt_id: str, store: EmailStore) -> dict[str, Any]:
    hunt = load_hunt(hunt_id)
    if not hunt:
        raise ValueError("Hunt result not found")
    candidates = _candidate_source(hunt)
    existing = {item["id"]: item for item in store.list_contact_profiles_for_hunt(hunt_id)}
    profiles_by_id: dict[str, dict[str, Any]] = {}
    for lead in candidates:
        draft = build_profile(hunt_id, hunt, lead)
        existing_row = existing.get(draft["id"]) or {}
        existing_profile = decode_profile(existing_row) if existing_row else {}
        profile = build_profile(hunt_id, hunt, lead, created_at=existing_row.get("created_at"))
        # Keep operator-entered contact fields when profiles are regenerated from
        # the hunt result. Search re-extraction should not erase manual work.
        if existing_profile.get("recipient_email"):
            profile["recipient_email"] = existing_profile.get("recipient_email")
            if existing_profile.get("send_eligibility") == "manually_excluded":
                profile["send_eligibility"] = "manually_excluded"
                profile["skip_reason"] = existing_profile.get("skip_reason") or "业务员已从本次邮件发送名单移除"
            else:
                profile["send_eligibility"] = "sendable"
                profile["skip_reason"] = ""
            for key in ("recipient_name", "recipient_title"):
                if existing_profile.get(key):
                    profile[key] = existing_profile.get(key)
            variables = _as_dict(json.loads(str(profile.get("variables_json") or "{}")))
            variables.update({
                "recipient_email": profile["recipient_email"],
                "recipient_name": profile.get("recipient_name", ""),
                "recipient_title": profile.get("recipient_title", ""),
            })
            profile["variables_json"] = _json(variables)
        if "selected_for_outreach" not in lead and not draft.get("selected_for_outreach") and existing_profile.get("selected_for_outreach"):
            profile["selected_for_outreach"] = 1
            profile["selection_source"] = existing_profile.get("selection_source") or "email_sending"
            profile["selected_at"] = existing_profile.get("selected_at") or now_iso()
        store.upsert_contact_profile(profile)
        profiles_by_id[profile["id"]] = profile
    profiles = list(profiles_by_id.values())
    sendable = sum(1 for item in profiles if item.get("send_eligibility") == "sendable")
    return {
        "hunt_id": hunt_id,
        "profile_count": len(profiles),
        "sendable_count": sendable,
        "blocked_count": len(profiles) - sendable,
        "profiles": profiles,
    }


def decode_profile(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    for key in ["matched_product_keywords_json", "evidence_urls_json", "risk_flags_json", "variables_json", "lead_snapshot_json"]:
        target = key.replace("_json", "")
        try:
            result[target] = json.loads(str(row.get(key) or "[]" if key != "variables_json" and key != "lead_snapshot_json" else row.get(key) or "{}"))
        except Exception:
            result[target] = {} if key in {"variables_json", "lead_snapshot_json"} else []
    result["selected_for_outreach"] = bool(row.get("selected_for_outreach"))
    try:
        result["calibration_confidence"] = float(row.get("calibration_confidence") or 0)
    except (TypeError, ValueError):
        result["calibration_confidence"] = 0.0
    return result


def task_meta(hunt_id: str, group: dict[str, Any]) -> dict[str, Any]:
    hunt = load_hunt(hunt_id) or {}
    request = _as_dict(hunt.get("request"))
    return {
        "hunt_id": hunt_id,
        "status": _text(hunt.get("status")),
        "created_at": _text(hunt.get("created_at")),
        "updated_at": _text(group.get("updated_at")),
        "product_keywords": _as_list(request.get("product_keywords")) or _as_list(hunt.get("product_keywords")),
        "target_regions": _as_list(request.get("target_regions")) or _as_list(hunt.get("target_regions")),
        "target_customer_profile": _text(request.get("target_customer_profile") or hunt.get("target_customer_profile")),
        "display_name": _text(group.get("display_name")),
        "note": _text(group.get("note")),
        "profile_count": int(group.get("profile_count") or 0),
        "sendable_count": int(group.get("sendable_count") or 0),
        "blocked_count": int(group.get("blocked_count") or 0),
    }


def update_contact_profile(
    store: EmailStore,
    profile_id: str,
    *,
    recipient_email: str = "",
    recipient_name: str = "",
    recipient_title: str = "",
) -> dict[str, Any]:
    row = store.get_contact_profile(profile_id)
    if not row:
        raise ValueError("Email contact profile not found")
    payload = dict(row)
    email = _normalize_email(recipient_email or str(row.get("recipient_email") or ""))
    if recipient_email and not email:
        raise ValueError("Invalid recipient email")
    if recipient_name:
        payload["recipient_name"] = _text(recipient_name)
    if recipient_title:
        payload["recipient_title"] = _text(recipient_title)
    if email:
        payload["recipient_email"] = email
        payload["send_eligibility"] = "sendable"
        payload["skip_reason"] = ""
    else:
        payload["recipient_email"] = ""
        payload["send_eligibility"] = "missing_email"
        payload["skip_reason"] = "缺少可发送邮箱"
    variables = _as_dict(decode_profile(row).get("variables"))
    variables.update({
        "recipient_email": payload["recipient_email"],
        "recipient_name": payload.get("recipient_name", ""),
        "recipient_title": payload.get("recipient_title", ""),
    })
    payload["variables_json"] = _json(variables)
    payload["updated_at"] = now_iso()
    store.upsert_contact_profile(payload)
    refreshed = store.get_contact_profile(profile_id) or payload
    decoded = decode_profile(refreshed)
    sync_result = sync_contact_profile_to_hunt(decoded)
    decoded["sync_result"] = sync_result
    return decoded


def exclude_contact_profile_from_send(store: EmailStore, profile_id: str) -> dict[str, Any]:
    row = store.get_contact_profile(profile_id)
    if not row:
        raise ValueError("Email contact profile not found")
    payload = dict(row)
    payload["send_eligibility"] = "manually_excluded"
    payload["skip_reason"] = "业务员已从本次邮件发送名单移除"
    payload["updated_at"] = now_iso()
    store.upsert_contact_profile(payload)
    refreshed = store.get_contact_profile(profile_id) or payload
    return decode_profile(refreshed)


def restore_contact_profile_to_send(store: EmailStore, profile_id: str) -> dict[str, Any]:
    row = store.get_contact_profile(profile_id)
    if not row:
        raise ValueError("Email contact profile not found")
    payload = dict(row)
    email = _normalize_email(str(row.get("recipient_email") or ""))
    if email:
        payload["recipient_email"] = email
        payload["send_eligibility"] = "sendable"
        payload["skip_reason"] = ""
    else:
        payload["recipient_email"] = ""
        payload["send_eligibility"] = "missing_email"
        payload["skip_reason"] = "缺少可发送邮箱"
    variables = _as_dict(decode_profile(row).get("variables"))
    variables["recipient_email"] = payload["recipient_email"]
    payload["variables_json"] = _json(variables)
    payload["updated_at"] = now_iso()
    store.upsert_contact_profile(payload)
    refreshed = store.get_contact_profile(profile_id) or payload
    return decode_profile(refreshed)


def set_contact_profile_outreach_selection(store: EmailStore, profile_id: str, *, selected: bool) -> dict[str, Any]:
    row = store.get_contact_profile(profile_id)
    if not row:
        raise ValueError("Email contact profile not found")
    payload = dict(row)
    payload["selected_for_outreach"] = 1 if selected else 0
    payload["selection_source"] = "email_sending" if selected else ""
    payload["selected_at"] = now_iso() if selected else ""
    payload["updated_at"] = now_iso()
    store.upsert_contact_profile(payload)
    refreshed = store.get_contact_profile(profile_id) or payload
    decoded = decode_profile(refreshed)
    decoded["sync_result"] = sync_contact_profile_selection_to_hunt(decoded)
    return decoded


def sync_candidate_selection_to_contact_profile(
    store: EmailStore,
    hunt_id: str,
    *,
    hunt: dict[str, Any],
    candidate: dict[str, Any],
    selected: bool,
    source: str = "candidate_pool",
) -> dict[str, Any]:
    """Lightweight sync from one candidate bookmark to its existing email profile.

    This deliberately avoids ``extract_profiles_for_hunt`` because that function
    rebuilds every profile in the task.  Bookmark clicks need to feel instant and
    must not overwrite manually completed email fields.
    """

    draft = build_profile(hunt_id, hunt, candidate)
    profile_id = str(draft.get("id") or "")
    if not profile_id or not store.get_contact_profile(profile_id):
        return {"synced": False, "profile_id": profile_id, "reason": "profile_not_extracted"}
    current = now_iso()
    row = store.update_contact_profile_selection(
        profile_id,
        selected=selected,
        source=source,
        selected_at=current if selected else "",
        updated_at=current,
    )
    return {"synced": bool(row), "profile_id": profile_id, "updated_at": current}


def _base_url(url: str) -> str:
    raw = _text(url)
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    parsed = urllib.parse.urlparse(raw)
    if not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _candidate_pages(url: str) -> list[str]:
    base = _base_url(url)
    if not base:
        return []
    paths = ["/", "/contact", "/contact-us", "/about", "/about-us", "/team", "/support", "/en/contact", "/en/contact-us"]
    return [urllib.parse.urljoin(base, path) for path in paths]


def _fetch_text(url: str, *, timeout: int = 8) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; JPS-One email enrichment; +https://jps-one.com)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - public website enrichment
        content_type = response.headers.get("Content-Type", "")
        if "text" not in content_type and "html" not in content_type and "xml" not in content_type:
            return ""
        raw = response.read(800_000)
    text = raw.decode("utf-8", errors="ignore")
    text = html.unescape(text)
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text)


def discover_email_candidates(store: EmailStore, profile_id: str) -> dict[str, Any]:
    row = store.get_contact_profile(profile_id)
    if not row:
        raise ValueError("Email contact profile not found")
    profile = decode_profile(row)
    lead_snapshot = _as_dict(profile.get("lead_snapshot"))
    website = _first([profile.get("website"), lead_snapshot.get("website"), lead_snapshot.get("url")])
    pages = _candidate_pages(website)
    candidates: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for page_url in pages:
        try:
            text = _fetch_text(page_url)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            errors.append(f"{page_url}: {type(exc).__name__}")
            continue
        for match in EMAIL_RE.findall(text):
            email = _normalize_email(match)
            if not email:
                continue
            existing = candidates.get(email)
            confidence = 0.86 if any(token in page_url.lower() for token in ["contact", "support"]) else 0.72
            if existing and existing["confidence"] >= confidence:
                continue
            candidates[email] = {
                "email": email,
                "source_url": page_url,
                "confidence": confidence,
                "reason": "官网公开页面出现该邮箱" if confidence < 0.8 else "官网联系页面出现该邮箱",
            }
    ordered = sorted(candidates.values(), key=lambda item: (-float(item["confidence"]), item["email"]))
    return {
        "profile_id": profile_id,
        "company_name": profile.get("company_name", ""),
        "website": website,
        "checked_urls": pages,
        "candidates": ordered[:12],
        "errors": errors[:5],
    }
