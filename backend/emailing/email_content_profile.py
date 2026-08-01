"""Customer-visible variables for one-click outreach emails.

Email contact profiles contain both internal review evidence and public customer
facts. This module creates the small, customer-safe variable set that templates
are allowed to render into outbound email content.
"""

from __future__ import annotations

import re
from typing import Any


DEFAULT_PRODUCT_PITCH = "dental simulators, phantom heads, and dental training equipment"

INTERNAL_NOISE_RE = re.compile(
    r"(目标类型|目标偏离|业务规则扣分|规则扣分|评分|证据|来源|source|tavily|apify|mcp|"
    r"media_not_customer|directory_not_customer|not_customer|goal_drift|ranking_reason|target_type_reason)",
    re.I,
)


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _truncate_sentence(value: Any, *, max_chars: int = 260) -> str:
    text = _text(value)
    if not text or INTERNAL_NOISE_RE.search(text):
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip(" ,.;:") + "."


def _first_clean(values: list[Any], *, max_chars: int = 260) -> str:
    for value in values:
        clean = _truncate_sentence(value, max_chars=max_chars)
        if clean:
            return clean
    return ""


def _product_pitch(profile: dict[str, Any]) -> str:
    products = profile.get("matched_product_keywords")
    if isinstance(products, list):
        clean_products = [_text(item) for item in products if _text(item)]
        if clean_products:
            return ", ".join(clean_products[:4])
    variables = profile.get("variables") if isinstance(profile.get("variables"), dict) else {}
    raw = _text(variables.get("matched_product_keywords"))
    return raw or DEFAULT_PRODUCT_PITCH


def build_email_variables(profile: dict[str, Any]) -> dict[str, str]:
    """Return variables that are safe to expose to recipients."""

    variables = profile.get("variables") if isinstance(profile.get("variables"), dict) else {}
    company = _text(profile.get("company_name") or variables.get("company_name"))
    customer_public_summary = _first_clean([
        profile.get("company_summary"),
        variables.get("company_summary"),
    ])
    public_fit_sentence = _first_clean([
        variables.get("public_fit_sentence"),
        "Their public information suggests a possible fit for dental education or training equipment." if company else "",
    ])
    product_pitch = _product_pitch(profile)

    return {
        "company_name": company,
        "recipient_name": _text(profile.get("recipient_name") or variables.get("recipient_name")) or "there",
        "recipient_email": _text(profile.get("recipient_email") or variables.get("recipient_email")),
        "recipient_title": _text(profile.get("recipient_title") or variables.get("recipient_title")),
        "website": _text(profile.get("website") or variables.get("website")),
        "customer_public_summary": customer_public_summary,
        "product_pitch": product_pitch,
        "public_fit_sentence": public_fit_sentence,
    }


def public_variable_keys() -> list[str]:
    return [
        "company_name",
        "recipient_name",
        "recipient_email",
        "recipient_title",
        "website",
        "customer_public_summary",
        "product_pitch",
        "public_fit_sentence",
    ]


def migrate_template_to_public_variables(template: str) -> str:
    """Replace legacy internal variables with customer-visible equivalents."""

    text = str(template or "")
    replacements = {
        "company_summary": "customer_public_summary",
        "jps_fit_reason": "public_fit_sentence",
        "evidence_summary": "customer_public_summary",
        "matched_product_keywords": "product_pitch",
    }
    for old, new in replacements.items():
        text = re.sub(r"\{\{\s*" + re.escape(old) + r"\s*\}\}", "{{" + new + "}}", text)
    return text
