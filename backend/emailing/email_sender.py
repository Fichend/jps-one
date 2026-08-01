"""Unified email sending entrypoint."""

from __future__ import annotations

import asyncio
from typing import Any

from emailing.providers import provider_from_account
from emailing.providers.errors import provider_error_payload


def _send_via_smtp_sync(
    account: dict[str, Any],
    *,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
    reply_to: str | None = None,
    thread_key: str | None = None,
) -> dict[str, Any]:
    return provider_from_account(account).send(
        to_email=to_email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        reply_to=reply_to,
        thread_key=thread_key,
        rfc_message_id=str(account.get("rfc_message_id") or "") or None,
    )


async def send_email(
    account: dict[str, Any],
    *,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
    reply_to: str | None = None,
    thread_key: str | None = None,
) -> dict[str, Any]:
    """Send one email via the configured provider."""
    if not to_email.strip():
        return {
            "ok": False,
            "provider": str(account.get("provider_type", "smtp") or "smtp"),
            "provider_message_id": "",
            "thread_key": thread_key or subject,
            "sent_at": "",
            "error": "missing_recipient",
            "error_type": "invalid_recipient",
        }

    provider = str(account.get("provider_type", "smtp") or "smtp").lower()
    try:
        if provider == "smtp":
            return await asyncio.to_thread(
                _send_via_smtp_sync,
                account,
                to_email=to_email,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                reply_to=reply_to,
                thread_key=thread_key,
            )
        return {
            "ok": False,
            "provider": provider,
            "provider_message_id": "",
            "thread_key": thread_key or subject,
            "sent_at": "",
            "error": f"unsupported_provider:{provider}",
            "error_type": "permanent_failure",
        }
    except Exception as exc:
        payload = provider_error_payload(exc)
        return {
            "provider": provider,
            "provider_message_id": "",
            "thread_key": thread_key or subject,
            "sent_at": "",
            **payload,
        }
