"""Email campaign API routes."""

from __future__ import annotations

import json
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from api.hunt_store import load_hunt, save_hunt, now_iso
from api.security import require_api_access
from config.settings import get_settings
from emailing.contact_profiles import (
    decode_profile,
    discover_email_candidates,
    exclude_contact_profile_from_send,
    extract_profiles_for_hunt,
    restore_contact_profile_to_send,
    set_contact_profile_outreach_selection,
    task_meta,
    update_contact_profile,
)
from emailing.readiness import ensure_imap_tested, ensure_smtp_ready, ensure_smtp_tested
from emailing.reply_detector import run_reply_detection_once
from emailing.scheduler import run_scheduler_once
from emailing.policy import expand_email_targets
from emailing.store import EmailStore
from emailing.template_variables import (
    allowed_variable_keys,
    build_template_variables,
    extract_template_variables,
    parse_template_message,
    render_template,
    validate_template_variables,
)

router = APIRouter(prefix="/api/v1", tags=["email"])


def _store() -> EmailStore:
    store = EmailStore(get_settings().email_db_path)
    store.init_db()
    return store


def _default_account(store: EmailStore) -> dict[str, Any]:
    settings = get_settings()
    account_id = "default"
    existing = store.get_account(account_id)
    current = now_iso()
    payload = {
        "id": account_id,
        "provider_type": settings.email_provider_type,
        "from_name": settings.email_from_name,
        "from_email": settings.email_from_address,
        "reply_to": settings.email_reply_to or settings.email_from_address,
        "smtp_host": settings.email_smtp_host,
        "smtp_port": settings.email_smtp_port,
        "smtp_username": settings.email_smtp_username,
        "smtp_secret_encrypted": settings.email_smtp_password,
        "smtp_security": getattr(settings, "email_smtp_security", ""),
        "smtp_verify_cert": 1 if getattr(settings, "email_smtp_verify_cert", True) else 0,
        "imap_host": settings.email_imap_host,
        "imap_port": settings.email_imap_port,
        "imap_username": settings.email_imap_username,
        "imap_secret_encrypted": settings.email_imap_password,
        "use_tls": 1 if settings.email_use_tls else 0,
        "status": "active",
        "daily_send_limit": settings.email_daily_send_limit,
        "hourly_send_limit": settings.email_hourly_send_limit,
        "last_test_at": "",
        "created_at": existing.get("created_at", current) if existing else current,
        "updated_at": current,
    }
    store.upsert_account(payload)
    return store.get_account(account_id) or payload


def _sequence_is_campaign_ready(sequence: dict[str, Any]) -> bool:
    manual_review = sequence.get("manual_review")
    if isinstance(manual_review, dict):
        decision = str(manual_review.get("decision", "") or "")
        if decision == "approved":
            return True
        if decision == "rejected":
            return False
    if not bool(getattr(get_settings(), "email_require_approval_before_send", True)):
        return True
    return bool(sequence.get("auto_send_eligible"))


def _campaign_summary(store: EmailStore, campaign_id: str) -> dict[str, Any]:
    settings = get_settings()
    campaign = store.get_campaign(campaign_id)
    sequences = store.list_sequences_for_campaign(campaign_id)
    template_summary = store.get_template_performance_for_campaign(
        campaign_id,
        underperforming_min_assigned=int(getattr(settings, "email_template_underperforming_min_assigned", 10) or 10),
        underperforming_min_reply_rate=float(getattr(settings, "email_template_underperforming_min_reply_rate", 1.0) or 1.0),
    )
    return {
        "campaign": campaign,
        "sequence_count": len(sequences),
        "sent_count": store.count_messages_for_campaign(campaign_id, status="sent"),
        "pending_count": store.count_messages_for_campaign(campaign_id, status="pending"),
        "failed_count": store.count_messages_for_campaign(campaign_id, status="failed"),
        "template_summary": list(template_summary.values()),
        "sequences": sequences,
    }


def _write_summary_to_hunt(store: EmailStore, hunt_id: str, campaign_id: str) -> None:
    hunt = load_hunt(hunt_id)
    if not hunt:
        return
    result = hunt.setdefault("result", {})
    settings = get_settings()
    campaign = store.get_campaign(campaign_id)
    sequences = store.list_sequences_for_campaign(campaign_id)
    template_summary = store.get_template_performance_for_campaign(
        campaign_id,
        underperforming_min_assigned=int(getattr(settings, "email_template_underperforming_min_assigned", 10) or 10),
        underperforming_min_reply_rate=float(getattr(settings, "email_template_underperforming_min_reply_rate", 1.0) or 1.0),
    )
    result["email_campaign_summary"] = {
        "campaign_id": campaign_id,
        "status": campaign.get("status", "draft") if campaign else "draft",
        "sequences_total": len(sequences),
        "sent_count": store.count_messages_for_campaign(campaign_id, status="sent"),
        "failed_count": store.count_messages_for_campaign(campaign_id, status="failed"),
        "pending_count": store.count_messages_for_campaign(campaign_id, status="pending"),
        "replied_count": sum(1 for seq in sequences if seq.get("status") == "replied"),
        "template_summary": list(template_summary.values()),
    }
    generated_sequences = result.get("email_sequences")
    if isinstance(generated_sequences, list):
        for sequence in generated_sequences:
            if not isinstance(sequence, dict):
                continue
            template_id = str(sequence.get("template_id") or "")
            if template_id and template_id in template_summary:
                performance = template_summary[template_id]
                sequence["template_assigned_count"] = performance.get("assigned_count", sequence.get("template_assigned_count", 0))
                sequence["template_remaining_capacity"] = performance.get("remaining_capacity", sequence.get("template_remaining_capacity", 0))
                sequence["template_performance"] = {
                    "sent_count": performance.get("sent_count", 0),
                    "replied_count": performance.get("replied_count", 0),
                    "reply_rate": performance.get("reply_rate", 0.0),
                    "status": performance.get("status", "warming_up"),
                    "optimization_needed": bool(performance.get("optimization_needed", False)),
                    "recommended_action": str(performance.get("recommended_action", "keep_collecting_data") or "keep_collecting_data"),
                    "reason": str(performance.get("reason", "") or ""),
                }
    save_hunt(hunt_id, hunt)


def _json_load(value: Any, fallback: Any) -> Any:
    try:
        return json.loads(str(value or ""))
    except Exception:
        return fallback


def _json_list(value: Any) -> list[str]:
    loaded = _json_load(value, [])
    if not isinstance(loaded, list):
        return []
    return [str(item).strip() for item in loaded if str(item).strip()]


def _content_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _new_message_id(from_email: str, seed: str) -> str:
    domain = (from_email or "localhost").split("@")[-1] or "localhost"
    return f"<{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:32]}@{domain}>"


def _delivery_key(hunt_id: str, profile_id: str, email: str, step: int) -> str:
    return "one_click:" + hashlib.sha256(f"{hunt_id}|{profile_id}|{email.strip().lower()}|{step}".encode("utf-8")).hexdigest()


def _preview_from_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    payload = _json_load(row.get("payload_json"), {})
    if isinstance(payload, dict):
        payload.setdefault("preview_id", row.get("id"))
        payload.setdefault("content_hash", row.get("content_hash"))
        payload.setdefault("expires_at", row.get("expires_at"))
    return payload if isinstance(payload, dict) else {}


def _template_library_payload(row: dict[str, Any]) -> dict[str, Any]:
    subject = str(row.get("subject_template") or "")
    body = str(row.get("body_template") or "")
    used_subject, invalid_subject = validate_template_variables(subject)
    used_body, invalid_body = validate_template_variables(body)
    return {
        "id": str(row.get("id") or ""),
        "name": str(row.get("name") or ""),
        "category": str(row.get("category") or "custom"),
        "language": str(row.get("language") or "en"),
        "product_tags": _json_list(row.get("product_tags_json")),
        "customer_type_tags": _json_list(row.get("customer_type_tags_json")),
        "subject_template": subject,
        "body_template": body,
        "variable_keys": _json_list(row.get("variable_keys_json")),
        "used_variables": list(dict.fromkeys([*used_subject, *used_body])),
        "invalid_variables": list(dict.fromkeys([*invalid_subject, *invalid_body])),
        "status": str(row.get("status") or "active"),
        "usage_count": int(row.get("usage_count") or 0),
        "last_used_at": str(row.get("last_used_at") or ""),
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


def _store_template_library_item(store: EmailStore, payload: "EmailTemplateLibraryRequest", *, template_id: str | None = None) -> dict[str, Any]:
    name = payload.name.strip()
    body = payload.body_template.strip()
    subject = payload.subject_template.strip()
    if not name:
        raise ValueError("Template name is required")
    if not body:
        raise ValueError("Template body is required")
    existing = store.get_template_library_item(template_id or "") if template_id else None
    current = now_iso()
    used_subject, _ = validate_template_variables(subject)
    used_body, _ = validate_template_variables(body)
    variable_keys = list(dict.fromkeys([*used_subject, *used_body]))
    item_id = template_id or str(uuid.uuid4())
    store.upsert_template_library_item({
        "id": item_id,
        "name": name,
        "category": payload.category.strip() or "custom",
        "language": payload.language.strip() or "en",
        "product_tags_json": json.dumps([tag.strip() for tag in payload.product_tags if tag.strip()], ensure_ascii=False),
        "customer_type_tags_json": json.dumps([tag.strip() for tag in payload.customer_type_tags if tag.strip()], ensure_ascii=False),
        "subject_template": subject,
        "body_template": body,
        "variable_keys_json": json.dumps(variable_keys, ensure_ascii=False),
        "status": "active",
        "usage_count": int(existing.get("usage_count") or 0) if existing else 0,
        "last_used_at": str(existing.get("last_used_at") or "") if existing else "",
        "created_at": str(existing.get("created_at") or current) if existing else current,
        "updated_at": current,
    })
    stored = store.get_template_library_item(item_id)
    if not stored:
        raise ValueError("Template save failed")
    return _template_library_payload(stored)


def _workspace_payload(store: EmailStore, hunt_id: str) -> dict[str, Any]:
    workspace = store.get_template_workspace(hunt_id) or {}
    return {
        "subject_template": str(workspace.get("subject_template") or ""),
        "body_template": str(workspace.get("body_template") or ""),
        "messages": _json_load(workspace.get("messages_json"), []),
        "variable_keys": allowed_variable_keys(),
    }


def _render_template(template: str, variables: dict[str, Any]) -> str:
    return render_template(template, variables).text


def _default_subject_template() -> str:
    return ""


def _default_body_template() -> str:
    return ""


def _default_variable_keys() -> list[str]:
    return allowed_variable_keys()


def _store_workspace(
    store: EmailStore,
    hunt_id: str,
    *,
    subject_template: str,
    body_template: str,
    messages: list[dict[str, str]],
    variable_keys: list[str],
) -> None:
    existing = store.get_template_workspace(hunt_id) or {}
    created = str(existing.get("created_at") or now_iso())
    current = now_iso()
    store.upsert_template_workspace({
        "hunt_id": hunt_id,
        "subject_template": subject_template,
        "body_template": body_template,
        "messages_json": json.dumps(messages, ensure_ascii=False),
        "variable_keys_json": json.dumps(variable_keys, ensure_ascii=False),
        "created_at": created,
        "updated_at": current,
    })


def _template_from_request_or_workspace(store: EmailStore, hunt_id: str, payload: "OneClickPreviewRequest") -> tuple[str, str]:
    workspace = _workspace_payload(store, hunt_id)
    subject = str(payload.subject_template or workspace.get("subject_template") or _default_subject_template()).strip()
    body = str(payload.body_template or workspace.get("body_template") or _default_body_template()).strip()
    return subject, body


def _override_for_profile(payload: "OneClickPreviewRequest", profile_id: Any) -> "OneClickOverride | None":
    profile_key = str(profile_id or "")
    if not profile_key:
        return None
    override = payload.overrides.get(profile_key)
    if not override:
        return None
    if not override.subject.strip() and not override.body_text.strip():
        return None
    return override


def _profiles_for_hunt(store: EmailStore, hunt_id: str) -> list[dict[str, Any]]:
    return [decode_profile(item) for item in store.list_contact_profiles_for_hunt(hunt_id)]


def _build_one_click_preview(store: EmailStore, hunt_id: str, payload: "OneClickPreviewRequest") -> dict[str, Any]:
    subject_template, body_template = _template_from_request_or_workspace(store, hunt_id, payload)
    profiles = _profiles_for_hunt(store, hunt_id)
    previews: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    duplicate_count = 0
    for profile in profiles:
        variables = build_template_variables(profile)
        recipient = str(profile.get("recipient_email") or variables.get("recipient_email") or "").strip().lower()
        subject_render = render_template(subject_template, variables)
        body_render = render_template(body_template, variables)
        subject = subject_render.text
        body = body_render.text
        override = _override_for_profile(payload, profile.get("id"))
        if override:
            subject = override.subject.strip() or subject
            body = override.body_text.strip() or body
            subject_render = render_template(subject, variables)
            body_render = render_template(body, variables)
        row = {
            "profile_id": profile.get("id"),
            "company_name": profile.get("company_name"),
            "recipient_email": recipient,
            "subject": subject,
            "body_text": body,
            "edited": bool(override),
            "send_eligibility": profile.get("send_eligibility"),
            "skip_reason": profile.get("skip_reason"),
            "recipient_name": profile.get("recipient_name"),
            "recipient_title": profile.get("recipient_title"),
            "website": profile.get("website"),
            "country_or_region": profile.get("country_or_region"),
            "customer_type": profile.get("customer_type"),
            "target_type": profile.get("target_type"),
            "company_summary": profile.get("company_summary"),
            "jps_fit_reason": profile.get("jps_fit_reason"),
            "matched_product_keywords": profile.get("matched_product_keywords") or [],
            "evidence_summary": profile.get("evidence_summary"),
            "evidence_urls": profile.get("evidence_urls") or [],
            "phone": profile.get("phone"),
            "linkedin_url": profile.get("linkedin_url"),
            "instagram_url": profile.get("instagram_url"),
            "facebook_url": profile.get("facebook_url"),
            "x_url": profile.get("x_url"),
            "used_variables": list(dict.fromkeys([*subject_render.used_variables, *body_render.used_variables])),
            "missing_variables": list(dict.fromkeys([*subject_render.missing_variables, *body_render.missing_variables])),
            "invalid_variables": list(dict.fromkeys([*subject_render.invalid_variables, *body_render.invalid_variables])),
            "rendered_variables": {**subject_render.rendered_variables, **body_render.rendered_variables},
            "render_status": "invalid_variables" if subject_render.invalid_variables or body_render.invalid_variables else "missing_variables" if subject_render.missing_variables or body_render.missing_variables else "ready",
        }
        lead_key = f"{str(profile.get('website') or profile.get('company_name') or '').lower()}|{recipient}"
        if profile.get("send_eligibility") == "sendable" and recipient and subject and body and store.has_contact_history_for_lead_key(lead_key):
            row["skip_reason"] = "该客户邮箱已有发送/排队历史"
            row["skip_type"] = "duplicate"
            duplicate_count += 1
            skipped.append(row)
        elif profile.get("send_eligibility") == "sendable" and recipient and subject and body:
            previews.append(row)
        else:
            if not row["skip_reason"]:
                row["skip_reason"] = "缺少主题、正文或可发送邮箱"
            skipped.append(row)
    return {
        "hunt_id": hunt_id,
        "sendable_count": len(previews),
        "skipped_count": len(skipped),
        "duplicate_count": duplicate_count,
        "blocked_reason": "" if previews else "没有可发送客户，请先提取邮箱或检查模板。",
        "previews": previews,
        "skipped": skipped,
    }


class CreateCampaignRequest(BaseModel):
    name: str = "Outbound Campaign"


class CampaignResponse(BaseModel):
    campaign_id: str
    status: str
    sequence_count: int


class EmailProfileExtractResponse(BaseModel):
    hunt_id: str
    profile_count: int
    sendable_count: int
    blocked_count: int
    profiles: list[dict[str, Any]] = Field(default_factory=list)


class EmailTemplateChatRequest(BaseModel):
    message: str


class EmailTemplateChatResponse(BaseModel):
    hunt_id: str
    assistant_message: str
    subject_template: str
    body_template: str
    messages: list[dict[str, str]] = Field(default_factory=list)
    variable_keys: list[str] = Field(default_factory=list)
    used_variables: list[str] = Field(default_factory=list)
    invalid_variables: list[str] = Field(default_factory=list)


class EmailTemplateLibraryRequest(BaseModel):
    name: str
    category: str = "custom"
    language: str = "en"
    product_tags: list[str] = Field(default_factory=list)
    customer_type_tags: list[str] = Field(default_factory=list)
    subject_template: str = ""
    body_template: str = ""


class EmailTemplateLibraryItem(BaseModel):
    id: str
    name: str
    category: str = "custom"
    language: str = "en"
    product_tags: list[str] = Field(default_factory=list)
    customer_type_tags: list[str] = Field(default_factory=list)
    subject_template: str = ""
    body_template: str = ""
    variable_keys: list[str] = Field(default_factory=list)
    used_variables: list[str] = Field(default_factory=list)
    invalid_variables: list[str] = Field(default_factory=list)
    status: str = "active"
    usage_count: int = 0
    last_used_at: str = ""
    created_at: str = ""
    updated_at: str = ""


class EmailTemplateApplyRequest(BaseModel):
    template_id: str


class EmailTemplateApplyResponse(EmailTemplateChatResponse):
    template: EmailTemplateLibraryItem


class OneClickOverride(BaseModel):
    subject: str = ""
    body_text: str = ""


class OneClickPreviewRequest(BaseModel):
    subject_template: str = ""
    body_template: str = ""
    overrides: dict[str, OneClickOverride] = Field(default_factory=dict)


class OneClickStartRequest(OneClickPreviewRequest):
    campaign_name: str = ""
    preview_id: str = ""


class OneClickPreviewResponse(BaseModel):
    hunt_id: str
    preview_id: str = ""
    content_hash: str = ""
    expires_at: str = ""
    sendable_count: int
    skipped_count: int
    duplicate_count: int = 0
    blocked_reason: str = ""
    previews: list[dict[str, Any]] = Field(default_factory=list)
    skipped: list[dict[str, Any]] = Field(default_factory=list)


class OneClickStartResponse(BaseModel):
    hunt_id: str
    campaign_id: str
    send_request_id: str = ""
    status: str
    status_url: str = ""
    queued_count: int
    skipped_count: int
    duplicate_count: int = 0


class SendRequestStatusResponse(BaseModel):
    send_request_id: str
    hunt_id: str
    campaign_id: str = ""
    status: str
    queued_count: int = 0
    duplicate_count: int = 0
    skipped_count: int = 0
    summary: dict[str, int] = Field(default_factory=dict)
    messages: list[dict[str, Any]] = Field(default_factory=list)


class EmailProfileUpdateRequest(BaseModel):
    recipient_email: str = ""
    recipient_name: str = ""
    recipient_title: str = ""


class EmailProfileUpdateResponse(BaseModel):
    profile: dict[str, Any]


class EmailProfileSendListResponse(BaseModel):
    profile: dict[str, Any]


class EmailProfileSelectionRequest(BaseModel):
    selected: bool = False


class EmailProfileEnrichResponse(BaseModel):
    profile_id: str
    company_name: str = ""
    website: str = ""
    checked_urls: list[str] = Field(default_factory=list)
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


@router.post("/hunts/{hunt_id}/email-profiles/extract", response_model=EmailProfileExtractResponse, dependencies=[Depends(require_api_access)])
async def extract_email_profiles(hunt_id: str):
    store = _store()
    try:
        return extract_profiles_for_hunt(hunt_id, store)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/email/tasks", dependencies=[Depends(require_api_access)])
async def list_email_tasks():
    store = _store()
    groups = store.list_contact_profile_groups()
    tasks = []
    for group in groups:
        hunt_id = str(group.get("hunt_id") or "")
        if not hunt_id:
            continue
        tasks.append({
            **task_meta(hunt_id, group),
            "profiles": [],
        })
    return tasks


@router.get("/email/tasks/{hunt_id}", dependencies=[Depends(require_api_access)])
async def get_email_task(hunt_id: str):
    store = _store()
    group = next((item for item in store.list_contact_profile_groups() if str(item.get("hunt_id") or "") == hunt_id), None)
    if not group:
        hunt = load_hunt(hunt_id)
        if not hunt:
            raise HTTPException(status_code=404, detail="Email task not found")
        group = {"hunt_id": hunt_id, "profile_count": 0, "sendable_count": 0, "blocked_count": 0, "updated_at": hunt.get("updated_at", "")}
    return {
        **task_meta(hunt_id, group),
        "workspace": _workspace_payload(store, hunt_id),
        "profiles": _profiles_for_hunt(store, hunt_id),
    }


@router.get("/email/templates", response_model=list[EmailTemplateLibraryItem], dependencies=[Depends(require_api_access)])
async def list_email_templates():
    store = _store()
    return [_template_library_payload(row) for row in store.list_template_library_items()]


@router.post("/email/templates", response_model=EmailTemplateLibraryItem, dependencies=[Depends(require_api_access)])
async def create_email_template(payload: EmailTemplateLibraryRequest):
    store = _store()
    try:
        return EmailTemplateLibraryItem(**_store_template_library_item(store, payload))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/email/templates/{template_id}", response_model=EmailTemplateLibraryItem, dependencies=[Depends(require_api_access)])
async def get_email_template(template_id: str):
    store = _store()
    row = store.get_template_library_item(template_id)
    if not row:
        raise HTTPException(status_code=404, detail="Email template not found")
    return EmailTemplateLibraryItem(**_template_library_payload(row))


@router.put("/email/templates/{template_id}", response_model=EmailTemplateLibraryItem, dependencies=[Depends(require_api_access)])
async def update_email_template(template_id: str, payload: EmailTemplateLibraryRequest):
    store = _store()
    if not store.get_template_library_item(template_id):
        raise HTTPException(status_code=404, detail="Email template not found")
    try:
        return EmailTemplateLibraryItem(**_store_template_library_item(store, payload, template_id=template_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/email/templates/{template_id}", response_model=EmailTemplateLibraryItem, dependencies=[Depends(require_api_access)])
async def delete_email_template(template_id: str):
    store = _store()
    row = store.delete_template_library_item(template_id)
    if not row:
        raise HTTPException(status_code=404, detail="Email template not found")
    return EmailTemplateLibraryItem(**_template_library_payload(row))


@router.post("/email/tasks/{hunt_id}/template/apply", response_model=EmailTemplateApplyResponse, dependencies=[Depends(require_api_access)])
async def apply_email_template(hunt_id: str, payload: EmailTemplateApplyRequest):
    store = _store()
    row = store.get_template_library_item(payload.template_id)
    if not row or str(row.get("status") or "active") != "active":
        raise HTTPException(status_code=404, detail="Active email template not found")
    template = _template_library_payload(row)
    workspace = _workspace_payload(store, hunt_id)
    messages = list(workspace.get("messages") or [])
    messages.append({"role": "assistant", "content": f"已选择模板：{template['name']}。点击预览代发即可按客户资料自动填充。"})
    subject_template = str(template.get("subject_template") or "")
    body_template = str(template.get("body_template") or "")
    variable_keys = _default_variable_keys()
    _store_workspace(
        store,
        hunt_id,
        subject_template=subject_template,
        body_template=body_template,
        messages=messages,
        variable_keys=variable_keys,
    )
    used_subject, invalid_subject = validate_template_variables(subject_template)
    used_body, invalid_body = validate_template_variables(body_template)
    updated_template = _template_library_payload(store.mark_template_library_item_used(payload.template_id, used_at=now_iso()) or row)
    return EmailTemplateApplyResponse(
        hunt_id=hunt_id,
        assistant_message=f"已选择模板：{template['name']}。点击预览代发即可按客户资料自动填充。",
        subject_template=subject_template,
        body_template=body_template,
        messages=messages,
        variable_keys=variable_keys,
        used_variables=list(dict.fromkeys([*used_subject, *used_body])),
        invalid_variables=list(dict.fromkeys([*invalid_subject, *invalid_body])),
        template=EmailTemplateLibraryItem(**updated_template),
    )


@router.post("/email/tasks/{hunt_id}/template/chat", response_model=EmailTemplateChatResponse, dependencies=[Depends(require_api_access)])
async def chat_email_template(hunt_id: str, payload: EmailTemplateChatRequest):
    store = _store()
    profiles = _profiles_for_hunt(store, hunt_id)
    if not profiles:
        raise HTTPException(status_code=404, detail="Please extract email profiles first")

    workspace = _workspace_payload(store, hunt_id)
    messages = list(workspace.get("messages") or [])
    user_message = payload.message.strip()
    messages.append({"role": "user", "content": user_message})
    subject_template, body_template = parse_template_message(
        user_message,
        existing_subject=str(workspace.get("subject_template") or ""),
        existing_body=str(workspace.get("body_template") or ""),
    )
    used_subject, invalid_subject = validate_template_variables(subject_template)
    used_body, invalid_body = validate_template_variables(body_template)
    used_variables = list(dict.fromkeys([*used_subject, *used_body]))
    invalid_variables = list(dict.fromkeys([*invalid_subject, *invalid_body]))
    if invalid_variables:
        assistant_message = f"已识别模板，但发现不可用于邮件映射的变量：{', '.join(invalid_variables)}。这些变量不会被自动补全，请改成右侧列出的合法变量。"
    elif used_variables:
        assistant_message = f"已识别模板变量：{', '.join(used_variables)}。点击预览代发即可按客户资料自动填充。"
    else:
        assistant_message = "已保存模板。当前模板没有使用变量，预览时会按原文展示。"

    messages.append({"role": "assistant", "content": assistant_message})
    variable_keys = _default_variable_keys()
    _store_workspace(store, hunt_id, subject_template=subject_template, body_template=body_template, messages=messages, variable_keys=variable_keys)
    return EmailTemplateChatResponse(
        hunt_id=hunt_id,
        assistant_message=assistant_message,
        subject_template=subject_template,
        body_template=body_template,
        messages=messages,
        variable_keys=variable_keys,
        used_variables=used_variables,
        invalid_variables=invalid_variables,
    )


@router.post("/email/contact-profiles/{profile_id}/update", response_model=EmailProfileUpdateResponse, dependencies=[Depends(require_api_access)])
async def update_email_contact_profile(profile_id: str, payload: EmailProfileUpdateRequest):
    store = _store()
    try:
        profile = update_contact_profile(
            store,
            profile_id,
            recipient_email=payload.recipient_email,
            recipient_name=payload.recipient_name,
            recipient_title=payload.recipient_title,
        )
    except ValueError as exc:
        status = 400 if "Invalid" in str(exc) else 404
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return EmailProfileUpdateResponse(profile=profile)


@router.post("/email/contact-profiles/{profile_id}/exclude-from-send", response_model=EmailProfileSendListResponse, dependencies=[Depends(require_api_access)])
async def exclude_email_contact_profile_from_send(profile_id: str):
    store = _store()
    try:
        profile = exclude_contact_profile_from_send(store, profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return EmailProfileSendListResponse(profile=profile)


@router.post("/email/contact-profiles/{profile_id}/restore-to-send", response_model=EmailProfileSendListResponse, dependencies=[Depends(require_api_access)])
async def restore_email_contact_profile_to_send(profile_id: str):
    store = _store()
    try:
        profile = restore_contact_profile_to_send(store, profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return EmailProfileSendListResponse(profile=profile)


@router.post("/email/contact-profiles/{profile_id}/outreach-selection", response_model=EmailProfileSendListResponse, dependencies=[Depends(require_api_access)])
async def update_email_contact_profile_selection(profile_id: str, payload: EmailProfileSelectionRequest):
    store = _store()
    try:
        profile = set_contact_profile_outreach_selection(store, profile_id, selected=payload.selected)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return EmailProfileSendListResponse(profile=profile)


@router.post("/email/contact-profiles/{profile_id}/enrich-email", response_model=EmailProfileEnrichResponse, dependencies=[Depends(require_api_access)])
async def enrich_email_contact_profile(profile_id: str):
    store = _store()
    try:
        return EmailProfileEnrichResponse(**discover_email_candidates(store, profile_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/email/tasks/{hunt_id}/one-click/preview", response_model=OneClickPreviewResponse, dependencies=[Depends(require_api_access)])
async def preview_one_click_email(hunt_id: str, payload: OneClickPreviewRequest):
    store = _store()
    preview = _build_one_click_preview(store, hunt_id, payload)
    created = now_iso()
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    preview_id = str(uuid.uuid4())
    preview_payload = {**preview, "preview_id": preview_id, "expires_at": expires_at}
    content_hash = _content_hash(preview_payload)
    preview_payload["content_hash"] = content_hash
    store.create_one_click_preview({
        "id": preview_id,
        "hunt_id": hunt_id,
        "content_hash": content_hash,
        "subject_template": payload.subject_template,
        "body_template": payload.body_template,
        "payload_json": json.dumps(preview_payload, ensure_ascii=False),
        "sendable_count": preview["sendable_count"],
        "skipped_count": preview["skipped_count"],
        "duplicate_count": preview["duplicate_count"],
        "expires_at": expires_at,
        "consumed_at": "",
        "created_at": created,
    })
    return OneClickPreviewResponse(**preview_payload)


@router.post("/email/tasks/{hunt_id}/one-click/start", response_model=OneClickStartResponse, dependencies=[Depends(require_api_access)])
async def start_one_click_email(
    hunt_id: str,
    payload: OneClickStartRequest,
    request: Request,
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
):
    store = _store()
    request_path = str(request.url.path)
    request_hash = _content_hash(payload.model_dump())
    if idempotency_key:
        cached = store.get_idempotency_key(idempotency_key)
        if cached:
            if cached.get("request_hash") != request_hash:
                raise HTTPException(status_code=409, detail="Idempotency-Key 已被不同请求使用")
            return OneClickStartResponse(**_json_load(cached.get("response_json"), {}))

    if payload.preview_id:
        preview_row = store.get_one_click_preview(payload.preview_id)
        if not preview_row or str(preview_row.get("hunt_id") or "") != hunt_id:
            raise HTTPException(status_code=404, detail="Preview not found")
        if str(preview_row.get("consumed_at") or ""):
            raise HTTPException(status_code=409, detail="Preview has already been consumed")
        if datetime.fromisoformat(str(preview_row.get("expires_at")).replace("Z", "+00:00")) < datetime.now(timezone.utc):
            raise HTTPException(status_code=409, detail="Preview has expired; please preview again")
        preview = _build_one_click_preview(store, hunt_id, payload) if payload.overrides else _preview_from_snapshot(preview_row)
    else:
        preview = _build_one_click_preview(store, hunt_id, payload)
    if not preview["sendable_count"]:
        raise HTTPException(status_code=409, detail=preview["blocked_reason"] or "No sendable recipients")

    settings = get_settings()
    try:
        ensure_smtp_tested(settings)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    account = _default_account(store)
    campaign_id = str(uuid.uuid4())
    send_request_id = str(uuid.uuid4())
    created = now_iso()
    store.create_campaign({
        "id": campaign_id,
        "hunt_id": hunt_id,
        "email_account_id": account["id"],
        "name": payload.campaign_name.strip() or f"One-click outreach - {hunt_id[:8]}",
        "status": "active",
        "language_mode": settings.email_language_mode,
        "default_language": settings.email_default_language,
        "fallback_language": settings.email_fallback_language,
        "tone": settings.email_tone,
        "step1_delay_days": 0,
        "step2_delay_days": 3,
        "step3_delay_days": 3,
        "min_fit_score": settings.email_min_fit_score_to_send,
        "min_contactability_score": settings.email_min_contactability_score_to_send,
        "created_at": created,
        "updated_at": created,
    })

    if payload.preview_id and not store.consume_one_click_preview(payload.preview_id, consumed_at=created):
        raise HTTPException(status_code=409, detail="Preview has already been consumed")

    queued = 0
    duplicate_count = int(preview.get("duplicate_count") or 0)
    for item in preview["previews"]:
        profile = next((row for row in _profiles_for_hunt(store, hunt_id) if row.get("id") == item.get("profile_id")), None)
        if not profile:
            continue
        recipient_email = str(profile.get("recipient_email") or item.get("recipient_email") or "").strip().lower()
        profile_id = str(profile.get("id") or item.get("profile_id") or "")
        lead_key = f"{str(profile.get('website') or profile.get('company_name') or '').lower()}|{recipient_email}"
        if store.has_contact_history_for_lead_key(lead_key):
            duplicate_count += 1
            continue
        sequence_id = str(uuid.uuid4())
        delivery_key = _delivery_key(hunt_id, profile_id, recipient_email, 1)
        rfc_message_id = _new_message_id(str(account.get("from_email") or ""), delivery_key)
        store.create_sequence({
            "id": sequence_id,
            "campaign_id": campaign_id,
            "hunt_id": hunt_id,
            "lead_key": lead_key,
            "lead_email": recipient_email,
            "lead_name": str(profile.get("company_name") or ""),
            "decision_maker_name": str(profile.get("recipient_name") or ""),
            "decision_maker_title": str(profile.get("recipient_title") or ""),
            "locale": str(profile.get("language") or "en"),
            "generation_mode": "one_click",
            "template_id": f"one_click_{hunt_id}",
            "template_group": "one_click",
            "template_usage_index": 0,
            "template_max_send_count": 0,
            "status": "scheduled",
            "current_step": 0,
            "stop_reason": "",
            "replied_at": "",
            "last_sent_at": "",
            "next_scheduled_at": created,
            "created_at": created,
            "updated_at": created,
        })
        store.create_message({
            "id": str(uuid.uuid4()),
            "sequence_id": sequence_id,
            "step_number": 1,
            "goal": "one_click_outreach",
            "locale": str(profile.get("language") or "en"),
            "subject": str(item.get("subject") or ""),
            "body_text": str(item.get("body_text") or ""),
            "status": "queued",
            "scheduled_at": created,
            "attempt_count": 0,
            "next_attempt_at": created,
            "locked_at": "",
            "lock_owner": "",
            "authorized_at": created,
            "authorization_source": "one_click_confirmation",
            "rfc_message_id": rfc_message_id,
            "delivery_key": delivery_key,
            "sent_at": "",
            "provider_message_id": "",
            "thread_key": "",
            "failure_reason": "",
            "last_error_type": "",
            "last_error_message": "",
            "smtp_code": "",
            "created_at": created,
            "updated_at": created,
        })
        queued += 1

    store.create_send_request({
        "id": send_request_id,
        "hunt_id": hunt_id,
        "campaign_id": campaign_id,
        "preview_id": payload.preview_id,
        "idempotency_key": idempotency_key,
        "status": "queued" if queued else "completed",
        "queued_count": queued,
        "duplicate_count": duplicate_count,
        "skipped_count": int(preview.get("skipped_count") or 0),
        "created_at": created,
        "updated_at": created,
    })

    _write_summary_to_hunt(store, hunt_id, campaign_id)
    response = {
        "hunt_id": hunt_id,
        "campaign_id": campaign_id,
        "send_request_id": send_request_id,
        "status": "queued",
        "status_url": f"/api/v1/email/send-requests/{send_request_id}",
        "queued_count": queued,
        "skipped_count": int(preview.get("skipped_count") or 0),
        "duplicate_count": duplicate_count,
    }
    if idempotency_key:
        store.save_idempotency_key({
            "key": idempotency_key,
            "method": "POST",
            "path": request_path,
            "request_hash": request_hash,
            "response_json": json.dumps(response, ensure_ascii=False),
            "created_at": created,
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
        })
    return OneClickStartResponse(**response)


@router.get("/email/send-requests/{send_request_id}", response_model=SendRequestStatusResponse, dependencies=[Depends(require_api_access)])
async def get_email_send_request(send_request_id: str):
    store = _store()
    row = store.get_send_request(send_request_id)
    if not row:
        raise HTTPException(status_code=404, detail="Send request not found")
    campaign_id = str(row.get("campaign_id") or "")
    sequences = store.list_sequences_for_campaign(campaign_id) if campaign_id else []
    messages: list[dict[str, Any]] = []
    summary = {"queued": 0, "sending": 0, "smtp_accepted": 0, "retry_wait": 0, "failed": 0, "unknown": 0, "cancelled": 0}
    for sequence in sequences:
        for message in store.list_messages_for_sequence(str(sequence.get("id") or "")):
            status = str(message.get("status") or "")
            bucket = "smtp_accepted" if status == "sent" else status
            if bucket in summary:
                summary[bucket] += 1
            messages.append({
                "message_id": message.get("id"),
                "sequence_id": sequence.get("id"),
                "company_name": sequence.get("lead_name"),
                "recipient_email": sequence.get("lead_email"),
                "subject": message.get("subject"),
                "status": bucket,
                "attempt_count": message.get("attempt_count"),
                "next_attempt_at": message.get("next_attempt_at"),
                "sent_at": message.get("sent_at"),
                "provider_message_id": message.get("provider_message_id"),
                "failure_reason": message.get("failure_reason"),
                "last_error_type": message.get("last_error_type"),
                "last_error_message": message.get("last_error_message"),
                "smtp_code": message.get("smtp_code"),
            })
    status = "completed" if messages and all(str(item.get("status")) in {"smtp_accepted", "failed", "unknown", "cancelled"} for item in messages) else str(row.get("status") or "queued")
    store.update_send_request_status(send_request_id, status=status, updated_at=now_iso())
    return SendRequestStatusResponse(
        send_request_id=send_request_id,
        hunt_id=str(row.get("hunt_id") or ""),
        campaign_id=campaign_id,
        status=status,
        queued_count=int(row.get("queued_count") or 0),
        duplicate_count=int(row.get("duplicate_count") or 0),
        skipped_count=int(row.get("skipped_count") or 0),
        summary=summary,
        messages=messages,
    )


@router.post("/hunts/{hunt_id}/email-campaigns", response_model=CampaignResponse, dependencies=[Depends(require_api_access)])
async def create_email_campaign(hunt_id: str, payload: CreateCampaignRequest):
    hunt = load_hunt(hunt_id)
    if not hunt or not isinstance(hunt.get("result"), dict):
        raise HTTPException(status_code=404, detail="Hunt result not found")
    sequences = hunt["result"].get("email_sequences", [])
    if not isinstance(sequences, list) or not sequences:
        raise HTTPException(status_code=400, detail="No generated email sequences found for this hunt")

    settings = get_settings()
    try:
        ensure_smtp_ready(settings)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    store = _store()
    account = _default_account(store)
    campaign_id = str(uuid.uuid4())
    created = now_iso()
    store.create_campaign({
        "id": campaign_id,
        "hunt_id": hunt_id,
        "email_account_id": account["id"],
        "name": payload.name,
        "status": "draft",
        "language_mode": settings.email_language_mode,
        "default_language": settings.email_default_language,
        "fallback_language": settings.email_fallback_language,
        "tone": settings.email_tone,
        "step1_delay_days": settings.email_step1_delay_days,
        "step2_delay_days": settings.email_step2_delay_days,
        "step3_delay_days": settings.email_step3_delay_days,
        "min_fit_score": settings.email_min_fit_score_to_send,
        "min_contactability_score": settings.email_min_contactability_score_to_send,
        "created_at": created,
        "updated_at": created,
    })
    base_time = datetime.now(timezone.utc)
    for seq in sequences:
        lead = seq.get("lead") or {}
        primary_target = seq.get("target") or {}
        raw_targets = []
        if isinstance(primary_target, dict):
            raw_targets.append(primary_target)
        raw_targets.extend(seq.get("targets") or [])
        raw_targets.extend(expand_email_targets(lead) or [])
        seen_target_emails: set[str] = set()
        targets = []
        for target in raw_targets:
            if not isinstance(target, dict):
                continue
            target_email = str(target.get("target_email", "") or "").strip().lower()
            if not target_email or target_email in seen_target_emails:
                continue
            seen_target_emails.add(target_email)
            targets.append(target)
        emails = seq.get("emails") or []
        template_perf = seq.get("template_performance") or {}
        template_status = str(template_perf.get("status", "") or "")
        if not targets or not emails:
            continue
        if not _sequence_is_campaign_ready(seq):
            continue
        if template_status in {"underperforming", "exhausted"}:
            continue
        for target in targets:
            lead_key = (
                str((lead.get("website") or lead.get("company_name") or "")).lower()
                + "|"
                + str(target.get("target_email") or "").lower()
            )
            if store.has_contact_history_for_lead_key(lead_key):
                continue
            sequence_id = str(uuid.uuid4())
            store.create_sequence({
                "id": sequence_id,
                "campaign_id": campaign_id,
                "hunt_id": hunt_id,
                "lead_key": lead_key or (sequence_id.lower() + "|" + str(target.get("target_email") or "").lower()),
                "lead_email": str(target.get("target_email") or ""),
                "lead_name": str(lead.get("company_name") or ""),
                "decision_maker_name": str(target.get("target_name") or ""),
                "decision_maker_title": str(target.get("target_title") or ""),
                "locale": str(seq.get("locale") or "en_US"),
                "generation_mode": str(seq.get("generation_mode") or "personalized"),
                "template_id": str(seq.get("template_id") or ""),
                "template_group": str(seq.get("template_group") or ""),
                "template_usage_index": int(seq.get("template_usage_index", 0) or 0),
                "template_max_send_count": int(seq.get("template_max_send_count", 0) or 0),
                "status": "scheduled",
                "current_step": 0,
                "stop_reason": "",
                "replied_at": "",
                "last_sent_at": "",
                "next_scheduled_at": "",
                "created_at": created,
                "updated_at": created,
            })
            next_scheduled = ""
            for email in emails:
                step_number = int(email.get("sequence_number", 1) or 1)
                delay_days = int(email.get("suggested_send_day", 0) or 0)
                scheduled_at = (base_time + timedelta(days=delay_days)).isoformat()
                if step_number == 1:
                    next_scheduled = scheduled_at
                store.create_message({
                    "id": str(uuid.uuid4()),
                    "sequence_id": sequence_id,
                    "step_number": step_number,
                    "goal": str(email.get("email_type", "") or ""),
                    "locale": str(seq.get("locale") or "en_US"),
                    "subject": str(email.get("subject", "") or ""),
                    "body_text": str(email.get("body_text", "") or ""),
                    "status": "pending",
                    "scheduled_at": scheduled_at,
                    "sent_at": "",
                    "provider_message_id": "",
                    "thread_key": "",
                    "failure_reason": "",
                    "created_at": created,
                    "updated_at": created,
                })
            store.update_sequence_status(sequence_id, status="scheduled", updated_at=created, next_scheduled_at=next_scheduled)

    _write_summary_to_hunt(store, hunt_id, campaign_id)
    summary = _campaign_summary(store, campaign_id)
    return CampaignResponse(campaign_id=campaign_id, status="draft", sequence_count=summary["sequence_count"])


@router.get("/hunts/{hunt_id}/email-campaigns", dependencies=[Depends(require_api_access)])
async def list_email_campaigns(hunt_id: str):
    store = _store()
    campaigns = store.list_campaigns_for_hunt(hunt_id)
    return [{"campaign": c, **_campaign_summary(store, c["id"])} for c in campaigns]


@router.post("/email-campaigns/{campaign_id}/start", dependencies=[Depends(require_api_access)])
async def start_email_campaign(campaign_id: str):
    store = _store()
    campaign = store.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    settings = get_settings()
    try:
        ensure_smtp_tested(settings)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if str(campaign.get("email_account_id", "")) == "default":
        _default_account(store)
    updated = now_iso()
    store.update_campaign_status(campaign_id, "active", updated_at=updated)
    _write_summary_to_hunt(store, str(campaign["hunt_id"]), campaign_id)
    return {"campaign_id": campaign_id, "status": "active"}


@router.post("/email-campaigns/{campaign_id}/pause", dependencies=[Depends(require_api_access)])
async def pause_email_campaign(campaign_id: str):
    store = _store()
    campaign = store.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    updated = now_iso()
    store.update_campaign_status(campaign_id, "paused", updated_at=updated)
    _write_summary_to_hunt(store, str(campaign["hunt_id"]), campaign_id)
    return {"campaign_id": campaign_id, "status": "paused"}


@router.get("/email-sequences/{sequence_id}", dependencies=[Depends(require_api_access)])
async def get_email_sequence(sequence_id: str):
    store = _store()
    sequence = store.get_sequence(sequence_id)
    if not sequence:
        raise HTTPException(status_code=404, detail="Sequence not found")
    messages = store.list_messages_for_sequence(sequence_id)
    reply_events = store.list_reply_events_for_sequence(sequence_id)
    return {"sequence": sequence, "messages": messages, "reply_events": reply_events}


@router.post("/email-scheduler/run", dependencies=[Depends(require_api_access)])
async def run_email_scheduler():
    store = _store()
    try:
        ensure_smtp_tested(get_settings())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return await run_scheduler_once(store)


@router.post("/email-replies/check", dependencies=[Depends(require_api_access)])
async def run_email_reply_check():
    store = _store()
    settings = get_settings()
    try:
        ensure_imap_tested(settings)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    account = _default_account(store)
    return await run_reply_detection_once(store, account)
