"""Simple scheduler for pending outbound emails."""

from __future__ import annotations

import socket
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Awaitable

from api.hunt_store import load_hunt, save_hunt
from config.settings import get_settings
from emailing.email_sender import send_email
from emailing.send_limits import send_limit_snapshot
from emailing.store import EmailStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str) -> datetime:
    try:
        return datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


def _retry_at(current: str, attempt_no: int) -> str:
    base = _parse_iso(current)
    delay = 30 if attempt_no <= 1 else 120
    return (base + timedelta(seconds=delay)).isoformat()


def _mask_error(value: object) -> str:
    text = str(value or "")
    return text.replace("\n", " ")[:500]


def _refresh_hunt_email_summary(store: EmailStore, hunt_id: str, campaign_id: str) -> None:
    hunt = load_hunt(hunt_id)
    if not hunt:
        return
    campaign = store.get_campaign(campaign_id)
    sequences = store.list_sequences_for_campaign(campaign_id)
    settings = get_settings()
    template_summary = store.get_template_performance_for_campaign(
        campaign_id,
        underperforming_min_assigned=int(getattr(settings, "email_template_underperforming_min_assigned", 10) or 10),
        underperforming_min_reply_rate=float(getattr(settings, "email_template_underperforming_min_reply_rate", 1.0) or 1.0),
    )
    summary = {
        "campaign_id": campaign_id,
        "status": campaign.get("status", "draft") if campaign else "draft",
        "sequences_total": len(sequences),
        "sent_count": store.count_messages_for_campaign(campaign_id, status="sent"),
        "failed_count": store.count_messages_for_campaign(campaign_id, status="failed"),
        "pending_count": store.count_messages_for_campaign(campaign_id, status="pending"),
        "replied_count": sum(1 for seq in sequences if seq.get("status") == "replied"),
        "template_summary": list(template_summary.values()),
    }
    result = hunt.setdefault("result", {})
    result["email_campaign_summary"] = summary
    save_hunt(hunt_id, hunt)


async def run_scheduler_once(
    store: EmailStore,
    *,
    now_iso: str | None = None,
    sender: Callable[..., Awaitable[dict[str, Any]]] = send_email,
) -> dict[str, int]:
    """Send pending email jobs that are ready."""
    current = now_iso or _now_iso()
    jobs = store.list_pending_messages_ready(current)
    lock_owner = f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"
    settings = get_settings()
    sent = 0
    failed = 0
    skipped = 0
    for job in jobs:
        if not send_limit_snapshot(store, settings, requested=1, now_iso=current, reserve_pending=False).allowed:
            skipped += 1
            break
        if not store.claim_message_for_sending(str(job["id"]), locked_at=current, lock_owner=lock_owner):
            skipped += 1
            continue
        job = store.get_message(str(job["id"])) or job
        attempt_no = int(job.get("attempt_count") or 0) + 1
        sequence = store.get_sequence(str(job.get("sequence_id", "")))
        if not sequence or sequence.get("status") in {"replied", "stopped", "completed", "failed"}:
            store.mark_message_failed(str(job["id"]), failure_reason="sequence_not_sendable", updated_at=current, error_type="sequence_not_sendable")
            skipped += 1
            continue
        campaign = store.get_campaign(str(sequence.get("campaign_id", "")))
        if not campaign or campaign.get("status") != "active":
            skipped += 1
            continue
        account = store.get_account(str(campaign.get("email_account_id", "")))
        if not account or account.get("status") != "active":
            store.mark_message_failed(str(job["id"]), failure_reason="inactive_email_account", updated_at=current, error_type="config_error")
            failed += 1
            continue
        template_id = str(sequence.get("template_id", "") or "")
        if template_id:
            template_summary = store.get_template_performance_for_campaign(
                str(sequence.get("campaign_id", "")),
                underperforming_min_assigned=int(getattr(settings, "email_template_underperforming_min_assigned", 10) or 10),
                underperforming_min_reply_rate=float(getattr(settings, "email_template_underperforming_min_reply_rate", 1.0) or 1.0),
            )
            template_perf = template_summary.get(template_id)
            template_status = str((template_perf or {}).get("status", "") or "")
            if template_status in {"underperforming", "exhausted"}:
                store.cancel_future_pending_messages(str(sequence["id"]), updated_at=current)
                store.update_sequence_status(
                    str(sequence["id"]),
                    status="stopped",
                    updated_at=current,
                    stop_reason=f"template_{template_status}",
                    next_scheduled_at="",
                )
                skipped += 1
                _refresh_hunt_email_summary(store, str(sequence["hunt_id"]), str(sequence["campaign_id"]))
                continue

        started_at = _now_iso()
        account = {**account, "rfc_message_id": str(job.get("rfc_message_id") or "")}
        result = await sender(
            account,
            to_email=str(sequence.get("lead_email", "") or ""),
            subject=str(job.get("subject", "") or ""),
            body_text=str(job.get("body_text", "") or ""),
            body_html=str(job.get("body_html", "") or ""),
            reply_to=str(account.get("reply_to", "") or ""),
            thread_key=str(job.get("thread_key", "") or ""),
        )
        finished_at = _now_iso()
        if result.get("ok"):
            store.record_send_attempt({
                "id": str(uuid.uuid4()),
                "message_id": str(job["id"]),
                "attempt_no": attempt_no,
                "status": "smtp_accepted",
                "started_at": started_at,
                "finished_at": finished_at,
                "smtp_code": str(result.get("smtp_code") or "250"),
                "error_type": "",
                "error_message_masked": "",
                "provider_message_id": str(result.get("provider_message_id", "") or ""),
                "created_at": started_at,
            })
            store.mark_message_sent(
                str(job["id"]),
                provider_message_id=str(result.get("provider_message_id", "") or ""),
                thread_key=str(result.get("thread_key", "") or ""),
                sent_at=current,
            )
            step_number = int(job.get("step_number", 1) or 1)
            next_message = store.get_message_for_step(str(sequence["id"]), step_number + 1)
            next_scheduled = str(next_message.get("scheduled_at", "") or "") if next_message else ""
            store.update_sequence_status(
                str(sequence["id"]),
                status="completed" if not next_message else "running",
                updated_at=current,
                current_step=step_number,
                last_sent_at=current,
                next_scheduled_at=next_scheduled,
            )
            sent += 1
        else:
            error_type = str(result.get("error_type") or result.get("error") or "send_failed")
            error_message = _mask_error(result.get("error"))
            smtp_code = str(result.get("smtp_code") or "")
            retryable = bool(result.get("retryable")) and error_type not in {"auth_error", "certificate_error", "recipient_rejected", "invalid_recipient", "permanent_failure", "unknown_after_data"}
            store.record_send_attempt({
                "id": str(uuid.uuid4()),
                "message_id": str(job["id"]),
                "attempt_no": attempt_no,
                "status": "failed",
                "started_at": started_at,
                "finished_at": finished_at,
                "smtp_code": smtp_code,
                "error_type": error_type,
                "error_message_masked": error_message,
                "provider_message_id": "",
                "created_at": started_at,
            })
            if error_type == "unknown_after_data":
                store.mark_message_unknown(str(job["id"]), failure_reason=error_type, error_message=error_message, updated_at=current)
                store.update_sequence_status(str(sequence["id"]), status="failed", updated_at=current, stop_reason=error_type)
                failed += 1
            elif retryable and attempt_no < 3:
                store.mark_message_retry_wait(
                    str(job["id"]),
                    failure_reason=error_type,
                    error_type=error_type,
                    error_message=error_message,
                    smtp_code=smtp_code,
                    next_attempt_at=_retry_at(current, attempt_no),
                    updated_at=current,
                )
                store.update_sequence_status(str(sequence["id"]), status="scheduled", updated_at=current, stop_reason=error_type)
                skipped += 1
            else:
                store.mark_message_failed(
                    str(job["id"]),
                    failure_reason=error_type,
                    updated_at=current,
                    error_type=error_type,
                    error_message=error_message,
                    smtp_code=smtp_code,
                )
                store.update_sequence_status(
                    str(sequence["id"]),
                    status="failed",
                    updated_at=current,
                    stop_reason=error_type,
                )
                failed += 1
        _refresh_hunt_email_summary(store, str(sequence["hunt_id"]), str(sequence["campaign_id"]))
    return {"sent": sent, "failed": failed, "skipped": skipped}
