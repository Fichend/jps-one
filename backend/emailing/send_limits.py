"""Outbound email send limit checks.

Limits are enforced before a one-click batch enters the queue and again by the
background scheduler before each SMTP send.  Pending queued messages reserve
capacity so simultaneous operators cannot exceed the configured ceiling.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from emailing.store import EmailStore


ACCEPTED_STATUSES = ("sent", "smtp_accepted")


@dataclass(frozen=True)
class SendLimitSnapshot:
    hourly_limit: int
    daily_limit: int
    hour_sent: int
    day_sent: int
    pending_reserved: int
    requested: int

    @property
    def hour_remaining(self) -> int:
        return max(self.hourly_limit - self.hour_sent - self.pending_reserved, 0)

    @property
    def day_remaining(self) -> int:
        return max(self.daily_limit - self.day_sent - self.pending_reserved, 0)

    @property
    def allowed(self) -> bool:
        return self.requested <= self.hour_remaining and self.requested <= self.day_remaining

    def rejection_reason(self) -> str:
        if self.allowed:
            return ""
        parts: list[str] = []
        if self.requested > self.hour_remaining:
            parts.append(f"本小时剩余可发送 {self.hour_remaining} 封，本次准备发送 {self.requested} 封")
        if self.requested > self.day_remaining:
            parts.append(f"今日剩余可发送 {self.day_remaining} 封，本次准备发送 {self.requested} 封")
        return "；".join(parts) + "。请减少客户数或稍后再发送。"

    def as_dict(self) -> dict[str, int | bool | str]:
        return {
            "hourly_limit": self.hourly_limit,
            "daily_limit": self.daily_limit,
            "hour_sent": self.hour_sent,
            "day_sent": self.day_sent,
            "pending_reserved": self.pending_reserved,
            "requested": self.requested,
            "hour_remaining": self.hour_remaining,
            "day_remaining": self.day_remaining,
            "allowed": self.allowed,
            "rejection_reason": self.rejection_reason(),
        }


def _as_positive_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def _now(value: str | None = None) -> datetime:
    if value:
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _timezone(settings: Any) -> ZoneInfo:
    try:
        return ZoneInfo(str(getattr(settings, "email_timezone", "Asia/Shanghai") or "Asia/Shanghai"))
    except Exception:
        return ZoneInfo("Asia/Shanghai")


def _day_start_utc(now_utc: datetime, settings: Any) -> str:
    local_now = now_utc.astimezone(_timezone(settings))
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return local_start.astimezone(timezone.utc).isoformat()


def send_limit_snapshot(store: EmailStore, settings: Any, *, requested: int, now_iso: str | None = None, reserve_pending: bool = True) -> SendLimitSnapshot:
    current = _now(now_iso).astimezone(timezone.utc)
    hour_start = (current - timedelta(hours=1)).isoformat()
    day_start = _day_start_utc(current, settings)
    hourly_limit = _as_positive_int(getattr(settings, "email_hourly_send_limit", 40), 40)
    daily_limit = _as_positive_int(getattr(settings, "email_daily_send_limit", 100), 100)
    hour_sent = store.count_messages_statuses_since(ACCEPTED_STATUSES, since_iso=hour_start, time_field="sent_at")
    day_sent = store.count_messages_statuses_since(ACCEPTED_STATUSES, since_iso=day_start, time_field="sent_at")
    pending_reserved = store.count_pending_send_capacity_reservations() if reserve_pending else 0
    return SendLimitSnapshot(
        hourly_limit=hourly_limit,
        daily_limit=daily_limit,
        hour_sent=hour_sent,
        day_sent=day_sent,
        pending_reserved=pending_reserved,
        requested=max(int(requested or 0), 0),
    )


def assert_send_capacity(store: EmailStore, settings: Any, *, requested: int, now_iso: str | None = None, reserve_pending: bool = True) -> SendLimitSnapshot:
    snapshot = send_limit_snapshot(store, settings, requested=requested, now_iso=now_iso, reserve_pending=reserve_pending)
    if not snapshot.allowed:
        raise ValueError(snapshot.rejection_reason())
    return snapshot
