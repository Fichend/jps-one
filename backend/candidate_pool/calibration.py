"""Candidate profile calibration helpers.

Candidate rows are the source of truth for downstream backcheck exports and
one-click email variables.  This module keeps auto/manual corrections scoped to
known customer fields so noisy evidence text cannot overwrite a company name or
email variable accidentally.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from api.hunt_store import now_iso
from config.settings import Settings, get_settings
from tools.llm_client import LLMTool
from tools.llm_output import parse_json


ALLOWED_FIELD_KEYS = {
    "company_name",
    "website",
    "country",
    "country_code",
    "region",
    "address",
    "industry",
    "customer_type",
    "customer_role",
    "target_type",
    "description",
    "ai_profile_summary",
    "company_summary",
    "emails",
    "email",
    "phone_numbers",
    "phone",
    "social_media",
    "linkedin_url",
    "instagram_url",
    "facebook_url",
    "x_url",
    "evidence_summary",
    "evidence_urls",
    "matched_product_keywords",
    "product_pitch",
}

LIST_FIELD_KEYS = {"emails", "phone_numbers", "evidence_urls", "matched_product_keywords"}
SOCIAL_KEYS = {"linkedin", "instagram", "facebook", "x", "twitter"}


def candidate_identity(item: dict[str, Any]) -> str:
    for key in ("candidate_id", "lead_id", "id"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    website = str(item.get("website") or item.get("link") or "").strip().lower()
    if website:
        return f"website:{website}"
    company = str(item.get("company_name") or item.get("title") or "").strip().lower()
    return f"company:{company}" if company else ""


def apply_candidate_patch(
    candidate: dict[str, Any],
    fields: dict[str, Any],
    *,
    actor: str,
    status: str,
    notes: str = "",
    confidence: float = 0.0,
    issues: list[str] | None = None,
) -> dict[str, Any]:
    """Apply a safe field patch to a candidate row in-place and return it."""

    original_snapshot = deepcopy(candidate)
    changed_fields: list[str] = []
    for key, raw_value in (fields or {}).items():
        if key not in ALLOWED_FIELD_KEYS:
            continue
        value = _normalize_field(key, raw_value)
        if _is_empty(value):
            continue
        if key == "twitter_url":
            key = "x_url"
        if key == "social_media" and isinstance(value, dict):
            social = candidate.get("social_media") if isinstance(candidate.get("social_media"), dict) else {}
            next_social = dict(social)
            for platform, url in value.items():
                platform_key = str(platform or "").strip().lower()
                if platform_key == "twitter":
                    platform_key = "x"
                if platform_key in SOCIAL_KEYS and str(url or "").strip():
                    next_social[platform_key] = str(url).strip()
            if next_social != social:
                candidate["social_media"] = next_social
                changed_fields.append("social_media")
            continue
        if candidate.get(key) != value:
            candidate[key] = value
            changed_fields.append(key)

    _mirror_contact_fields(candidate)
    current = now_iso()
    candidate["calibration_status"] = status
    candidate["calibrated_by"] = actor
    candidate["calibrated_at"] = current
    candidate["calibration_notes"] = notes[:1200]
    candidate["calibration_confidence"] = max(0.0, min(float(confidence or 0.0), 1.0))
    candidate["calibration_issues"] = list(issues or [])[:8]
    candidate["calibration_changed_fields"] = list(dict.fromkeys(changed_fields))
    candidate.setdefault("original_snapshot", original_snapshot)
    candidate["updated_at"] = current
    return candidate


async def auto_calibrate_candidate(
    candidate: dict[str, Any],
    *,
    hunt: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Use the configured reasoning LLM to calibrate known customer fields."""

    active_settings = settings or get_settings()
    llm = LLMTool(model_type="reasoning", settings=active_settings, hunt_id=str((hunt or {}).get("hunt_id") or ""), agent="candidate_calibration")
    try:
        try:
            raw = await llm.generate(
                _calibration_prompt(candidate, hunt or {}),
                system="你是 JPS-One 客户资料校准助手。只纠正字段映射，不编造缺失事实。必须返回 JSON。",
                temperature=0.05,
                max_tokens=1200,
                response_format={"type": "json_object"},
                timeout_seconds=45,
            )
            parsed = parse_json(raw, context="CandidateCalibration")
            if isinstance(parsed, dict):
                fields = parsed.get("calibrated_fields") if isinstance(parsed.get("calibrated_fields"), dict) else {}
                return apply_candidate_patch(
                    candidate,
                    fields,
                    actor="llm",
                    status="auto_calibrated",
                    notes=str(parsed.get("notes") or parsed.get("reason") or "").strip(),
                    confidence=_float(parsed.get("confidence"), 0.0),
                    issues=_string_list(parsed.get("issues")),
                )
        except Exception:
            pass
    finally:
        await llm.close()

    return apply_candidate_patch(
        candidate,
        deterministic_candidate_cleanup(candidate),
        actor="fallback",
        status="auto_calibrated_fallback",
        notes="LLM 校准失败，已执行确定性字段清理。",
        confidence=0.35,
        issues=["llm_failed"],
    )


def deterministic_candidate_cleanup(candidate: dict[str, Any]) -> dict[str, Any]:
    """Fallback cleanup for common extraction mistakes."""

    fields: dict[str, Any] = {}
    name = _text(candidate.get("company_name") or candidate.get("name") or candidate.get("title"))
    name = re.sub(r"\s*[-|•].{60,}$", "", name).strip()
    if len(name) > 90:
        name = name[:90].rsplit(" ", 1)[0].strip() or name[:90]
    if name:
        fields["company_name"] = name
    for key in ("website", "linkedin_url", "instagram_url", "facebook_url", "x_url"):
        value = _text(candidate.get(key))
        if value:
            fields[key] = value
    if candidate.get("social_media"):
        fields["social_media"] = candidate.get("social_media")
    for key in ("email", "phone"):
        value = _text(candidate.get(key))
        if value:
            fields[key] = value
    for key in ("emails", "phone_numbers"):
        values = _string_list(candidate.get(key))
        if values:
            fields[key] = values
    summary = _text(candidate.get("ai_profile_summary") or candidate.get("description") or candidate.get("company_summary"))
    if summary:
        fields["description"] = summary[:800]
    return fields


def set_candidate_outreach_selection(candidate: dict[str, Any], selected: bool, *, source: str = "candidate_pool") -> dict[str, Any]:
    current = now_iso()
    candidate["selected_for_outreach"] = bool(selected)
    candidate["selection_source"] = source if selected else ""
    candidate["selected_at"] = current if selected else ""
    candidate["updated_at"] = current
    return candidate


def _calibration_prompt(candidate: dict[str, Any], hunt: dict[str, Any]) -> str:
    compact = {key: candidate.get(key) for key in sorted(ALLOWED_FIELD_KEYS) if key in candidate}
    compact["evidence_items"] = (candidate.get("evidence_items") or candidate.get("evidence") or [])[:8]
    request = hunt.get("request") if isinstance(hunt.get("request"), dict) else {}
    context = {
        "target_regions": request.get("target_regions") or hunt.get("target_regions") or [],
        "product_keywords": request.get("product_keywords") or hunt.get("product_keywords") or [],
        "target_customer_profile": request.get("target_customer_profile") or hunt.get("target_customer_profile") or "",
    }
    return (
        "请校准这个候选客户的字段。重点：company_name 必须是机构/公司名称，不能是一段介绍；"
        "description/company_summary 才放介绍；邮箱/电话/社媒链接必须放到对应字段。不要新增没有证据的信息。\n\n"
        f"hunt_context = {json.dumps(context, ensure_ascii=False)}\n\n"
        f"candidate = {json.dumps(compact, ensure_ascii=False, default=str)}\n\n"
        "返回 JSON：{\"calibrated_fields\": {允许字段...}, \"confidence\": 0-1, \"issues\": [], \"notes\": \"中文说明\"}"
    )


def _mirror_contact_fields(candidate: dict[str, Any]) -> None:
    emails = _string_list(candidate.get("emails"))
    direct_email = _text(candidate.get("email"))
    if direct_email and direct_email not in emails:
        emails.insert(0, direct_email)
    if emails:
        candidate["emails"] = list(dict.fromkeys(emails))
        candidate["email"] = candidate["emails"][0]
    phones = _string_list(candidate.get("phone_numbers"))
    direct_phone = _text(candidate.get("phone"))
    if direct_phone and direct_phone not in phones:
        phones.insert(0, direct_phone)
    if phones:
        candidate["phone_numbers"] = list(dict.fromkeys(phones))
        candidate["phone"] = candidate["phone_numbers"][0]
    social = candidate.get("social_media") if isinstance(candidate.get("social_media"), dict) else {}
    for key in ("linkedin", "instagram", "facebook", "x"):
        direct = _text(candidate.get(f"{key}_url"))
        if direct:
            social = {**social, key: direct}
        elif _text(social.get(key)):
            candidate[f"{key}_url"] = _text(social.get(key))
    if social:
        candidate["social_media"] = social


def _normalize_field(key: str, value: Any) -> Any:
    if key in LIST_FIELD_KEYS:
        return _string_list(value)
    if key == "social_media" and isinstance(value, dict):
        return {str(k).strip().lower(): _text(v) for k, v in value.items() if _text(v)}
    if isinstance(value, str):
        return _text(value)
    return value


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict)):
        return not value
    return False


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = re.split(r"[;,，\n]", value)
    elif isinstance(value, list):
        raw = value
    else:
        raw = []
    return list(dict.fromkeys(_text(item) for item in raw if _text(item)))


def _float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback
