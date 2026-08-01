"""Evidence-based JPS lead scoring rules.

The rules mirror ``获客评分标准.xlsx`` and are intentionally deterministic:
unknown evidence gets low or zero points instead of inferred credit.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


PUBLIC_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "hotmail.com",
    "outlook.com",
    "live.com",
    "yahoo.com",
    "icloud.com",
    "aol.com",
    "qq.com",
    "163.com",
    "126.com",
}

SOCIAL_DOMAINS = ("instagram.com", "facebook.com", "linkedin.com", "youtube.com", "tiktok.com")
OFFICIAL_SUFFIXES = (
    " ltd",
    " limited",
    " co., ltd",
    " company",
    " corporation",
    " corp",
    " inc",
    " llc",
    " pte",
    " pte ltd",
    " gmbh",
    " sdn bhd",
    " joint stock",
    " jsc",
    " university",
    " college",
    " school",
    " hospital",
)


def score_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """Return JPS score, grade, and explainable breakdown for a candidate or lead."""

    evidence_text = _evidence_text(candidate)
    breakdown = {
        "registered_company_name": _score_company_name(candidate),
        "business_email": _score_email(candidate),
        "phone": _score_phone(candidate),
        "product_match": _score_product_match(candidate, evidence_text),
        "website": _score_website(candidate),
        "company_age": _score_company_age(evidence_text),
        "physical_presence": _score_physical_presence(candidate, evidence_text),
        "decision_maker": _score_decision_maker(candidate),
        "compliance_qualification": _score_compliance(evidence_text),
    }
    total = sum(int(item["points"]) for item in breakdown.values())
    return {
        "jps_score": total,
        "lead_grade": _grade(total),
        "score_breakdown": breakdown,
        "scoring_version": _rules().get("version", "unknown"),
    }


def apply_score(candidate: dict[str, Any]) -> dict[str, Any]:
    candidate.update(score_candidate(candidate))
    return candidate


@lru_cache(maxsize=1)
def _rules() -> dict[str, Any]:
    path = Path(__file__).with_name("jps_lead_scoring_rules.json")
    return json.loads(path.read_text(encoding="utf-8"))


def _grade(total: int) -> str:
    thresholds = _rules().get("grade_thresholds", {})
    for grade in ("A", "B", "C", "D"):
        if total >= int(thresholds.get(grade, 0)):
            return grade
    return "D"


def _points(points: int, reason: str, evidence: str = "") -> dict[str, Any]:
    return {"points": points, "reason": reason, "evidence": evidence[:240]}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _domain(url_or_email: str) -> str:
    value = _clean(url_or_email).lower()
    if "@" in value and not value.startswith("http"):
        return value.rsplit("@", 1)[-1]
    if not value:
        return ""
    parsed = urlparse(value if "://" in value else f"https://{value}")
    host = parsed.netloc.lower().split("@")[-1].split(":")[0]
    return host[4:] if host.startswith("www.") else host


def _list_values(candidate: dict[str, Any], *keys: str) -> list[str]:
    values: list[str] = []
    for key in keys:
        raw = candidate.get(key)
        if isinstance(raw, list):
            values.extend(_clean(item) for item in raw if _clean(item))
        elif _clean(raw):
            values.append(_clean(raw))
    return values


def _social_values(candidate: dict[str, Any]) -> list[str]:
    values = _list_values(candidate, "instagram_url", "facebook_url", "linkedin_url")
    social = candidate.get("social_media")
    if isinstance(social, dict):
        values.extend(_clean(value) for value in social.values() if _clean(value))
    return values


def _evidence_text(candidate: dict[str, Any]) -> str:
    parts = [
        _clean(candidate.get("company_name")),
        _clean(candidate.get("industry")),
        _clean(candidate.get("description")),
        _clean(candidate.get("address")),
        _clean(candidate.get("customs_data")),
        " ".join(_list_values(candidate, "business_types", "risk_flags")),
    ]
    for item in candidate.get("evidence_items") or candidate.get("evidence") or []:
        if isinstance(item, dict):
            parts.extend(_clean(item.get(key)) for key in ("title", "snippet", "claim", "source", "url"))
            raw = item.get("raw")
            if isinstance(raw, dict):
                parts.append(json.dumps(raw, ensure_ascii=False))
    return " ".join(part for part in parts if part).lower()


def _score_company_name(candidate: dict[str, Any]) -> dict[str, Any]:
    name = _clean(candidate.get("company_name"))
    if not name or name.lower() in {"unknown", "n/a", "-"}:
        return _points(0, "无正规名称")
    lower = f" {name.lower()} "
    if any(suffix in lower for suffix in OFFICIAL_SUFFIXES) or len(name.split()) >= 3:
        return _points(10, "完整官方注册名或明确机构名称", name)
    return _points(5, "名称较短或疑似简称", name)


def _score_email(candidate: dict[str, Any]) -> dict[str, Any]:
    emails = _list_values(candidate, "email", "emails")
    if not emails:
        return _points(0, "无邮箱")
    website_domain = _domain(_clean(candidate.get("website")))
    for email in emails:
        email_domain = _domain(email)
        if email_domain and email_domain not in PUBLIC_EMAIL_DOMAINS and (not website_domain or email_domain == website_domain):
            return _points(12, "公司域名邮箱", email)
    return _points(6, "公共邮箱或域名未能匹配官网", emails[0])


def _score_phone(candidate: dict[str, Any]) -> dict[str, Any]:
    phones = _list_values(candidate, "phone", "phone_numbers")
    social_count = len(_social_values(candidate))
    if len(phones) >= 2 or (phones and social_count):
        return _points(12, "多个电话或有社媒联系通道", ", ".join(phones[:3]))
    if phones:
        return _points(6, "单一号码", phones[0])
    return _points(0, "无电话")


def _score_product_match(candidate: dict[str, Any], evidence_text: str) -> dict[str, Any]:
    if _clean(candidate.get("priority_tier")) == "reject" or _clean(candidate.get("customer_role")) == "consumer":
        return _points(0, "已被标记为拒绝或终端消费客户")
    strong = ("distributor", "supplier", "importer", "dealer", "wholesale", "dental equipment", "medical consumable", "dental school", "university", "training lab", "simulation")
    medium = ("medical", "healthcare", "cssd", "sterilization", "hospital supply", "laboratory")
    clinic = ("clinic", "dentist", "patient", "orthodontic clinic")
    if any(term in evidence_text for term in strong):
        return _points(16, "主营牙科/医疗耗材经销或目标采购机构", _first_hit(evidence_text, strong))
    if any(term in evidence_text for term in medium):
        return _points(8, "综合医疗附带牙科/CSSD 消毒供应中心系列", _first_hit(evidence_text, medium))
    if any(term in evidence_text for term in clinic):
        return _points(3, "诊所终端自用", _first_hit(evidence_text, clinic))
    return _points(0, "不相关或证据不足")


def _score_website(candidate: dict[str, Any]) -> dict[str, Any]:
    website = _clean(candidate.get("website"))
    socials = _social_values(candidate)
    if website and not any(host in _domain(website) for host in SOCIAL_DOMAINS):
        return _points(10, "独立官网", website)
    if website or socials:
        return _points(4, "仅社交平台主页", website or socials[0])
    return _points(0, "无线上展示")


def _score_company_age(evidence_text: str) -> dict[str, Any]:
    years = [int(year) for year in re.findall(r"\b(?:est(?:ablished)?\.?|since|founded|成立于|founded in)\D{0,12}(19\d{2}|20\d{2})\b", evidence_text)]
    if not years:
        return _points(0, "成立时间未知")
    age = 2026 - min(years)
    if age >= 8:
        return _points(12, "成立 8 年以上", str(min(years)))
    if age >= 3:
        return _points(8, "成立 3-7 年", str(min(years)))
    if age >= 1:
        return _points(3, "成立 1-2 年", str(min(years)))
    return _points(0, "成立小于 1 年", str(min(years)))


def _score_physical_presence(candidate: dict[str, Any], evidence_text: str) -> dict[str, Any]:
    address = _clean(candidate.get("address"))
    if any(term in evidence_text for term in ("warehouse", "wholesale", "showroom", "store", "branch", "office")):
        return _points(10, "仓库/门店/批发/地址证据较强", address)
    if address:
        return _points(6, "有地址但经营规模未知", address)
    if _social_values(candidate) and not _clean(candidate.get("website")):
        return _points(3, "纯线上或仅社媒展示")
    return _points(0, "无经营形态证据")


def _score_decision_maker(candidate: dict[str, Any]) -> dict[str, Any]:
    decision_makers = candidate.get("decision_makers")
    if isinstance(decision_makers, list):
        for person in decision_makers:
            if isinstance(person, dict) and _clean(person.get("name")) and _clean(person.get("title")):
                return _points(8, "采购/负责人姓名和职位", f"{person.get('name')} {person.get('title')}")
    if _list_values(candidate, "email", "emails") or _clean(candidate.get("contact_person")):
        return _points(4, "仅通用邮箱或通用联系入口")
    return _points(0, "无人名")


def _score_compliance(evidence_text: str) -> dict[str, Any]:
    strong = ("import license", "medical device license", "iso 13485", "fda", "ce certified", "authorized distributor", "registration certificate")
    medium = ("medical device", "importer", "distributor", "health ministry", "licensed", "certificate")
    if any(term in evidence_text for term in strong):
        return _points(10, "本地医疗进口/经销/注册资质证据", _first_hit(evidence_text, strong))
    if any(term in evidence_text for term in medium):
        return _points(5, "资质待核实或有医疗经销信号", _first_hit(evidence_text, medium))
    return _points(0, "无进口/医疗资质证据")


def _first_hit(text: str, terms: tuple[str, ...]) -> str:
    for term in terms:
        idx = text.find(term)
        if idx >= 0:
            return text[max(0, idx - 50): idx + len(term) + 80]
    return ""
