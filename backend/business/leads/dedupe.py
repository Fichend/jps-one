"""Lead identity and deduplication helpers."""

from __future__ import annotations

import json
from typing import Any


def lead_key(lead: dict[str, Any]) -> str:
    """Build a stable key for one lead using website, company, email, then raw content."""
    website = str(lead.get("website", "") or "").strip().lower()
    if website:
        return f"w:{website}"
    company_name = str(lead.get("company_name", "") or "").strip().lower()
    if company_name:
        return f"c:{company_name}"
    emails = lead.get("emails") or []
    if isinstance(emails, list) and emails:
        return f"e:{str(emails[0]).strip().lower()}"
    return "raw:" + json.dumps(lead, sort_keys=True, ensure_ascii=False)


def dedupe_leads(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for lead in leads:
        if isinstance(lead, dict):
            merged[lead_key(lead)] = lead
    return list(merged.values())


def unique_leads_count(leads: list[dict[str, Any]]) -> int:
    return len(dedupe_leads(leads))
