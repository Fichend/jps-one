"""Provider interface for outbound email delivery."""

from __future__ import annotations

from typing import Any, Protocol


class EmailProvider(Protocol):
    def validate_config(self) -> None:
        ...

    def test_connection(self) -> dict[str, Any]:
        ...

    def send(
        self,
        *,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
        reply_to: str | None = None,
        thread_key: str | None = None,
        rfc_message_id: str | None = None,
    ) -> dict[str, Any]:
        ...
