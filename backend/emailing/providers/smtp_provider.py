"""SMTP provider with one connection policy for tests and sends."""

from __future__ import annotations

import email.utils
import smtplib
import socket
import ssl
from email.message import EmailMessage
from typing import Any
from uuid import uuid4

from emailing.body_format import format_plaintext_email_body
from emailing.html_sanitizer import sanitize_html
from emailing.providers.errors import EmailProviderError


def smtp_security_from_config(value: Any, *, port: int, use_tls: Any = True) -> str:
    explicit = str(value or "").strip().lower()
    if explicit in {"ssl", "starttls", "none"}:
        return explicit
    enabled = str(use_tls).strip().lower() not in {"0", "false", "no", "off", ""}
    if not enabled:
        return "none"
    return "ssl" if int(port or 0) == 465 else "starttls"


class SmtpEmailProvider:
    def __init__(self, account: dict[str, Any]) -> None:
        self.account = account
        self.host = str(account.get("smtp_host", "") or "").strip()
        self.port = int(account.get("smtp_port", 0) or 0)
        self.username = str(account.get("smtp_username", "") or "").strip()
        self.password = str(account.get("smtp_secret_encrypted") or account.get("smtp_password") or "")
        self.from_name = str(account.get("from_name", "") or "")
        self.from_email = str(account.get("from_email", "") or "").strip()
        self.security = smtp_security_from_config(account.get("smtp_security"), port=self.port, use_tls=account.get("use_tls", True))
        self.verify_cert = str(account.get("smtp_verify_cert", "true") if account.get("smtp_verify_cert") is not None else "true").strip().lower() not in {"0", "false", "no", "off"}
        self.timeout = int(account.get("smtp_timeout_seconds", 20) or 20)

    def validate_config(self) -> None:
        missing = []
        for label, value in [
            ("EMAIL_SMTP_HOST", self.host),
            ("EMAIL_SMTP_PORT", self.port),
            ("EMAIL_SMTP_USERNAME", self.username),
            ("EMAIL_SMTP_PASSWORD", self.password),
            ("EMAIL_FROM_ADDRESS", self.from_email),
        ]:
            if not str(value or "").strip():
                missing.append(label)
        if missing:
            raise EmailProviderError("config_error", "Missing SMTP settings: " + ", ".join(missing), retryable=False)
        if self.security == "none":
            raise EmailProviderError("config_error", "Plain SMTP is disabled for production sending.", retryable=False)

    def _ssl_context(self) -> ssl.SSLContext:
        if self.verify_cert:
            return ssl.create_default_context()
        context = ssl._create_unverified_context()  # noqa: SLF001 - explicit operator opt-out.
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    def _connect(self) -> smtplib.SMTP:
        self.validate_config()
        context = self._ssl_context()
        try:
            if self.security == "ssl":
                client: smtplib.SMTP = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout, context=context)
                client.ehlo()
            elif self.security == "starttls":
                client = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
                client.ehlo()
                client.starttls(context=context)
                client.ehlo()
            else:
                raise EmailProviderError("config_error", "Plain SMTP is disabled for production sending.", retryable=False)
            client.login(self.username, self.password)
            return client
        except ssl.SSLCertVerificationError as exc:
            raise EmailProviderError("certificate_error", str(exc), retryable=False) from exc
        except smtplib.SMTPAuthenticationError as exc:
            raise EmailProviderError("auth_error", _smtp_message(exc), retryable=False, smtp_code=str(exc.smtp_code)) from exc
        except smtplib.SMTPConnectError as exc:
            raise EmailProviderError("temporary_failure", _smtp_message(exc), retryable=True, smtp_code=str(exc.smtp_code)) from exc
        except smtplib.SMTPResponseException as exc:
            retryable = 400 <= int(exc.smtp_code or 0) < 500
            raise EmailProviderError("temporary_failure" if retryable else "permanent_failure", _smtp_message(exc), retryable=retryable, smtp_code=str(exc.smtp_code)) from exc
        except socket.gaierror as exc:
            raise EmailProviderError("dns_error", str(exc), retryable=True) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise EmailProviderError("timeout", str(exc), retryable=True) from exc
        except OSError as exc:
            raise EmailProviderError("network_error", str(exc), retryable=True) from exc

    def test_connection(self) -> dict[str, Any]:
        client = self._connect()
        try:
            return {"ok": True, "status": "ok", "host": self.host, "port": self.port, "security": self.security, "username": self.username}
        finally:
            _quit(client)

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
        if not str(to_email or "").strip():
            raise EmailProviderError("invalid_recipient", "missing_recipient", retryable=False)

        message_id = rfc_message_id or _new_message_id(self.from_email)
        msg = EmailMessage()
        msg["From"] = email.utils.formataddr((self.from_name, self.from_email))
        msg["To"] = to_email
        msg["Subject"] = subject
        msg["Message-ID"] = message_id
        msg["Date"] = email.utils.formatdate(localtime=True)
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.set_content(format_plaintext_email_body(body_text))
        clean_html = sanitize_html(body_html or "")
        if clean_html:
            msg.add_alternative(clean_html, subtype="html")

        client = self._connect()
        try:
            refused = client.send_message(msg)
            if refused:
                raise EmailProviderError("recipient_rejected", str(refused), retryable=False)
            return {
                "ok": True,
                "provider": "smtp",
                "provider_message_id": message_id,
                "thread_key": thread_key or subject,
                "sent_at": email.utils.formatdate(localtime=False),
                "smtp_code": "250",
                "error": "",
                "error_type": "",
                "retryable": False,
            }
        except smtplib.SMTPRecipientsRefused as exc:
            raise EmailProviderError("recipient_rejected", str(exc), retryable=False) from exc
        except smtplib.SMTPDataError as exc:
            code = int(exc.smtp_code or 0)
            retryable = 400 <= code < 500
            raise EmailProviderError("temporary_failure" if retryable else "permanent_failure", _smtp_message(exc), retryable=retryable, smtp_code=str(exc.smtp_code)) from exc
        except smtplib.SMTPServerDisconnected as exc:
            raise EmailProviderError("unknown_after_data", str(exc), retryable=False) from exc
        finally:
            _quit(client)


def provider_from_settings(settings: Any) -> SmtpEmailProvider:
    return SmtpEmailProvider({
        "provider_type": getattr(settings, "email_provider_type", "smtp"),
        "from_name": getattr(settings, "email_from_name", ""),
        "from_email": getattr(settings, "email_from_address", ""),
        "smtp_host": getattr(settings, "email_smtp_host", ""),
        "smtp_port": getattr(settings, "email_smtp_port", 0),
        "smtp_username": getattr(settings, "email_smtp_username", ""),
        "smtp_secret_encrypted": getattr(settings, "email_smtp_password", ""),
        "smtp_security": getattr(settings, "email_smtp_security", ""),
        "smtp_verify_cert": getattr(settings, "email_smtp_verify_cert", True),
        "use_tls": getattr(settings, "email_use_tls", True),
    })


def provider_from_account(account: dict[str, Any]) -> SmtpEmailProvider:
    return SmtpEmailProvider(account)


def _new_message_id(from_email: str) -> str:
    domain = (from_email or "localhost").split("@")[-1] or "localhost"
    return f"<{uuid4()}@{domain}>"


def _smtp_message(exc: smtplib.SMTPResponseException) -> str:
    raw = exc.smtp_error.decode(errors="replace") if isinstance(exc.smtp_error, bytes) else str(exc.smtp_error)
    return f"{exc.smtp_code} {raw}".strip()


def _quit(client: smtplib.SMTP) -> None:
    try:
        client.quit()
    except Exception:
        client.close()
