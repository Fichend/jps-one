"""Email quality scoring for customer enrichment.

The score is deliberately explainable: operators need to know why an address is
safe to use for outreach, while the system keeps lower-confidence addresses as
candidates instead of discarding them.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


FREE_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "hotmail.com",
    "outlook.com",
    "live.com",
    "yahoo.com",
    "icloud.com",
    "aol.com",
    "proton.me",
    "protonmail.com",
}

BUSINESS_PREFIXES = {
    "info",
    "contact",
    "sales",
    "business",
    "office",
    "admin",
    "admissions",
    "international",
    "procurement",
    "purchasing",
    "marketing",
    "support",
}

LOW_VALUE_PREFIXES = {"noreply", "no-reply", "webmaster", "postmaster", "abuse", "privacy", "legal"}


def rank_email_candidates(emails: list[dict[str, Any]], *, website: str = "") -> list[dict[str, Any]]:
    domain = _domain(website)
    ranked: dict[str, dict[str, Any]] = {}
    for raw in emails:
        email = _clean_email(raw.get("email"))
        if not email:
            continue
        scored = _score_email(email, source_url=str(raw.get("source_url") or ""), website_domain=domain)
        scored.update({key: value for key, value in raw.items() if key not in scored and value not in (None, "", [])})
        existing = ranked.get(email)
        if not existing or float(scored["confidence"]) > float(existing.get("confidence") or 0):
            ranked[email] = scored
    return sorted(ranked.values(), key=lambda item: (-float(item.get("confidence") or 0), item.get("email", "")))


def best_email(emails: list[dict[str, Any]]) -> str:
    for item in emails:
        if str(item.get("grade") or "") in {"A", "B"}:
            return str(item.get("email") or "")
    return str(emails[0].get("email") or "") if emails else ""


def _score_email(email: str, *, source_url: str, website_domain: str) -> dict[str, Any]:
    local, _, email_domain = email.partition("@")
    source = source_url.lower()
    same_domain = bool(website_domain and _domain_matches(email_domain, website_domain))
    business_prefix = local.lower() in BUSINESS_PREFIXES
    low_prefix = local.lower() in LOW_VALUE_PREFIXES
    free_domain = email_domain.lower() in FREE_EMAIL_DOMAINS
    contact_page = any(token in source for token in ("contact", "admission", "international", "procurement", "sales", "support"))

    confidence = 0.5
    reasons: list[str] = []
    if same_domain:
        confidence += 0.28
        reasons.append("官网同域邮箱")
    if business_prefix:
        confidence += 0.12
        reasons.append("业务联系邮箱")
    if contact_page:
        confidence += 0.08
        reasons.append("来源页面与联系/招生/采购相关")
    if free_domain:
        confidence -= 0.22
        reasons.append("免费邮箱域名")
    if low_prefix:
        confidence -= 0.24
        reasons.append("低价值系统邮箱")
    if re.search(r"^[a-z]+\.[a-z]+$", local.lower()):
        confidence += 0.04
        reasons.append("疑似个人姓名邮箱")

    confidence = max(0.15, min(confidence, 0.98))
    grade = "A" if confidence >= 0.86 else "B" if confidence >= 0.72 else "C" if confidence >= 0.55 else "D"
    return {
        "email": email,
        "source_url": source_url,
        "confidence": round(confidence, 2),
        "grade": grade,
        "reason": "；".join(reasons) or "公开页面出现该邮箱",
    }


def _clean_email(value: Any) -> str:
    text = str(value or "").strip().lower().strip(".,;:()[]{}<>")
    if not re.match(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$", text):
        return ""
    return text


def _domain(url_or_domain: str) -> str:
    raw = str(url_or_domain or "").strip().lower()
    if not raw:
        return ""
    if "@" in raw and not raw.startswith("http"):
        raw = raw.rsplit("@", 1)[-1]
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    host = urlparse(raw).netloc or urlparse(raw).path.split("/")[0]
    return host.removeprefix("www.")


def _domain_matches(email_domain: str, website_domain: str) -> bool:
    email_domain = _domain(email_domain)
    website_domain = _domain(website_domain)
    return bool(email_domain and website_domain and (email_domain == website_domain or email_domain.endswith("." + website_domain)))
