"""Safety checks for one-click outbound email content."""

from __future__ import annotations

import re
from typing import Any


PROHIBITED_PATTERNS: list[tuple[str, str]] = [
    (r"目标类型|目标偏离|业务规则扣分|规则扣分|评分|证据", "包含内部评分/证据说明"),
    (r"\b(media_not_customer|directory_not_customer|not_customer|clinic_excluded|excluded_by_goal|excluded_by_rule)\b", "包含内部客户筛选标签"),
    (r"\b(tavily|apify|mcp|serper|jina|source_tool|tool_plan|ranking_reason|target_type_reason|goal_drift)\b", "包含内部工具或规则字段"),
]

BLOCKED_TARGET_TYPES = {"media", "directory"}
BLOCKED_STATUS = {"excluded_by_goal", "excluded_by_rule"}
BLOCKED_FLAGS = {"media_not_customer", "directory_not_customer", "clinic_excluded"}


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def blocked_profile_reason(profile: dict[str, Any]) -> str:
    """Return a reason if a profile should not enter default one-click sending."""

    target_type = _text(profile.get("target_type")).lower()
    if target_type in BLOCKED_TARGET_TYPES:
        return f"业务不匹配：目标类型为 {target_type}"

    snapshot = profile.get("lead_snapshot") if isinstance(profile.get("lead_snapshot"), dict) else {}
    status = _text(snapshot.get("candidate_status") or snapshot.get("status")).lower()
    if status in BLOCKED_STATUS:
        return f"业务不匹配：{status}"

    flags: set[str] = set()
    for key in ("goal_drift_flags", "ranking_flags", "ai_risk_flags"):
        raw = snapshot.get(key)
        if isinstance(raw, list):
            flags.update(_text(item).lower() for item in raw if _text(item))
    matched = sorted(flags & BLOCKED_FLAGS)
    if matched:
        return f"业务不匹配：{', '.join(matched)}"
    return ""


def content_violations(subject: str, body_text: str) -> list[str]:
    text = f"{subject}\n{body_text}"
    violations: list[str] = []
    for pattern, reason in PROHIBITED_PATTERNS:
        if re.search(pattern, text, flags=re.I):
            violations.append(reason)
    return list(dict.fromkeys(violations))


def validate_email_content(subject: str, body_text: str) -> tuple[bool, list[str]]:
    issues = content_violations(subject, body_text)
    if not _text(subject):
        issues.append("缺少邮件主题")
    if not _text(body_text):
        issues.append("缺少邮件正文")
    return (not issues, issues)
