"""Compatibility wrappers around the unified SMTP provider."""

from __future__ import annotations

from config.settings import Settings
from emailing.providers import provider_from_settings


def test_smtp_connection(settings: Settings) -> dict[str, str]:
    """Validate that SMTP settings can connect and authenticate."""
    result = provider_from_settings(settings).test_connection()
    return {
        "status": "ok",
        "host": str(result.get("host") or settings.email_smtp_host),
        "username": str(result.get("username") or settings.email_smtp_username),
        "security": str(result.get("security") or ""),
    }


def send_smtp_email(
    settings: Settings,
    *,
    to_address: str,
    subject: str,
    body_text: str,
) -> dict[str, str]:
    """Send a plain-text email using the configured SMTP account."""
    result = provider_from_settings(settings).send(
        to_email=to_address,
        subject=subject,
        body_text=body_text,
        reply_to=settings.email_reply_to,
    )
    return {
        "status": "sent" if result.get("ok") else "failed",
        "to_address": to_address,
        "subject": subject,
        "provider_message_id": str(result.get("provider_message_id") or ""),
    }
