"""Structured email provider errors."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class EmailProviderError(Exception):
    error_type: str
    message: str
    retryable: bool = False
    smtp_code: str = ""

    def __str__(self) -> str:
        return self.message


def provider_error_payload(exc: Exception) -> dict[str, object]:
    if isinstance(exc, EmailProviderError):
        return {
            "ok": False,
            "error_type": exc.error_type,
            "error": exc.message,
            "smtp_code": exc.smtp_code,
            "retryable": exc.retryable,
        }
    return {
        "ok": False,
        "error_type": "provider_error",
        "error": str(exc),
        "smtp_code": "",
        "retryable": False,
    }
