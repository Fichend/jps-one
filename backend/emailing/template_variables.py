"""Template variable parsing and rendering for one-click emails.

The email workspace is a variable mapper, not a copywriter. It renders only the
template text supplied by the operator and reports variable coverage per
recipient.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


VARIABLE_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

ALLOWED_VARIABLES: tuple[str, ...] = (
    "company_name",
    "recipient_name",
    "recipient_email",
    "recipient_title",
    "website",
    "country_or_region",
    "customer_type",
    "product_pitch",
    "phone",
    "linkedin_url",
    "instagram_url",
    "facebook_url",
    "x_url",
)

INTERNAL_VARIABLES: tuple[str, ...] = (
    "jps_fit_reason",
    "evidence_summary",
    "ranking_reason",
    "target_type_reason",
    "score_breakdown",
    "goal_drift_flags",
    "source_tool",
    "target_type",
    "candidate_status",
)


@dataclass(frozen=True)
class RenderedTemplate:
    text: str
    used_variables: list[str]
    missing_variables: list[str]
    invalid_variables: list[str]
    rendered_variables: dict[str, str]

    @property
    def render_status(self) -> str:
        if self.invalid_variables:
            return "invalid_variables"
        if self.missing_variables:
            return "missing_variables"
        return "ready"


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _list_text(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    if _text(value):
        return [_text(value)]
    return []


def allowed_variable_keys() -> list[str]:
    return list(ALLOWED_VARIABLES)


def extract_template_variables(template: str) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for match in VARIABLE_RE.finditer(str(template or "")):
        key = match.group(1).strip()
        if key and key not in seen:
            seen.add(key)
            ordered.append(key)
    return ordered


def validate_template_variables(template: str) -> tuple[list[str], list[str]]:
    used = extract_template_variables(template)
    allowed = set(ALLOWED_VARIABLES)
    invalid = [key for key in used if key not in allowed]
    return used, invalid


def build_template_variables(profile: dict[str, Any]) -> dict[str, str]:
    variables = profile.get("variables") if isinstance(profile.get("variables"), dict) else {}
    products = _list_text(profile.get("matched_product_keywords"))
    if not products:
        products = _list_text(variables.get("matched_product_keywords"))
    return {
        "company_name": _text(profile.get("company_name") or variables.get("company_name")),
        "recipient_name": _text(profile.get("recipient_name") or variables.get("recipient_name")),
        "recipient_email": _text(profile.get("recipient_email") or variables.get("recipient_email")),
        "recipient_title": _text(profile.get("recipient_title") or variables.get("recipient_title")),
        "website": _text(profile.get("website") or variables.get("website")),
        "country_or_region": _text(profile.get("country_or_region") or variables.get("country_or_region")),
        "customer_type": _text(profile.get("customer_type") or variables.get("customer_type")),
        "product_pitch": ", ".join(products),
        "phone": _text(profile.get("phone") or variables.get("phone")),
        "linkedin_url": _text(profile.get("linkedin_url") or variables.get("linkedin_url")),
        "instagram_url": _text(profile.get("instagram_url") or variables.get("instagram_url")),
        "facebook_url": _text(profile.get("facebook_url") or variables.get("facebook_url")),
        "x_url": _text(profile.get("x_url") or variables.get("x_url")),
    }


def render_template(template: str, variables: dict[str, Any]) -> RenderedTemplate:
    used = extract_template_variables(template)
    allowed = set(ALLOWED_VARIABLES)
    invalid = [key for key in used if key not in allowed]
    rendered_variables = {key: _text(variables.get(key)) for key in used if key in allowed}
    missing = [key for key in used if key in allowed and not rendered_variables.get(key)]

    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        if key not in allowed:
            return match.group(0)
        return rendered_variables.get(key, "")

    text = VARIABLE_RE.sub(replace, str(template or ""))
    return RenderedTemplate(
        text=text,
        used_variables=used,
        missing_variables=missing,
        invalid_variables=invalid,
        rendered_variables=rendered_variables,
    )


def parse_template_message(message: str, existing_subject: str = "", existing_body: str = "") -> tuple[str, str]:
    """Extract subject/body from an operator message without rewriting text."""

    raw = str(message or "").strip()
    if not raw:
        return existing_subject, existing_body

    subject = ""
    body_lines: list[str] = []
    in_body = False
    for line in raw.splitlines():
        stripped = line.strip()
        subject_match = re.match(r"^(subject|主题)\s*[:：]\s*(.*)$", stripped, flags=re.I)
        body_match = re.match(r"^(body|正文|邮件正文)\s*[:：]\s*(.*)$", stripped, flags=re.I)
        if subject_match:
            subject = subject_match.group(2).strip()
            in_body = False
            continue
        if body_match:
            in_body = True
            first = body_match.group(2)
            if first:
                body_lines.append(first)
            continue
        if in_body:
            body_lines.append(line)

    body = "\n".join(body_lines).strip()
    if subject or body:
        return subject or existing_subject, body or existing_body
    return existing_subject, raw
