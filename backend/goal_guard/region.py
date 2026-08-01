"""Rule-first region fit assessment for candidate pools.

Search APIs can return globally relevant companies even when the query contains
a country name. RegionGuard keeps those rows for audit, but makes confirmed
out-of-region candidates lose Top N priority.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


COUNTRY_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "TH": {
        "names": ("thailand", "thai", "泰国", "ประเทศไทย"),
        "tlds": ("th",),
        "cities": ("bangkok", "chiang mai", "phuket", "นนทบุรี", "กรุงเทพ", "กรุงเทพมหานคร"),
    },
    "VN": {
        "names": ("vietnam", "viet nam", "越南", "việt nam"),
        "tlds": ("vn",),
        "cities": ("hanoi", "ha noi", "ho chi minh", "saigon", "da nang", "can tho", "hồ chí minh"),
    },
    "CA": {
        "names": ("canada", "canadian", "加拿大"),
        "tlds": ("ca",),
        "cities": ("toronto", "vancouver", "montreal", "ottawa", "calgary"),
    },
    "US": {
        "names": ("united states", "usa", "u.s.a", "america", "美国"),
        "tlds": ("us",),
        "cities": ("new york", "los angeles", "chicago", "houston", "boston"),
    },
    "CN": {
        "names": ("china", "chinese", "中国", "mainland china"),
        "tlds": ("cn",),
        "cities": ("shanghai", "beijing", "guangzhou", "shenzhen", "上海", "北京", "广州", "深圳"),
    },
    "JP": {
        "names": ("japan", "japanese", "日本"),
        "tlds": ("jp",),
        "cities": ("tokyo", "osaka", "kyoto", "東京", "大阪"),
    },
    "IN": {
        "names": ("india", "indian", "印度"),
        "tlds": ("in",),
        "cities": ("mumbai", "delhi", "bangalore", "chennai", "hyderabad"),
    },
    "FR": {
        "names": ("france", "french", "法国"),
        "tlds": ("fr",),
        "cities": ("paris", "lyon", "marseille"),
    },
    "DE": {
        "names": ("germany", "german", "德国", "deutschland"),
        "tlds": ("de",),
        "cities": ("berlin", "munich", "hamburg", "frankfurt"),
    },
    "AU": {
        "names": ("australia", "australian", "澳大利亚", "澳洲"),
        "tlds": ("au",),
        "cities": ("sydney", "melbourne", "brisbane", "perth"),
    },
    "MY": {"names": ("malaysia", "马来西亚"), "tlds": ("my",), "cities": ("kuala lumpur", "selangor")},
    "ID": {"names": ("indonesia", "印度尼西亚", "印尼"), "tlds": ("id",), "cities": ("jakarta", "surabaya", "bandung")},
    "PH": {"names": ("philippines", "菲律宾"), "tlds": ("ph",), "cities": ("manila", "cebu")},
    "SG": {"names": ("singapore", "新加坡"), "tlds": ("sg",), "cities": ("singapore",)},
    "KH": {"names": ("cambodia", "柬埔寨"), "tlds": ("kh",), "cities": ("phnom penh",)},
    "LA": {"names": ("laos", "老挝"), "tlds": ("la",), "cities": ("vientiane",)},
}

REGION_GROUPS: dict[str, set[str]] = {
    "southeast asia": {"TH", "VN", "MY", "ID", "PH", "SG", "KH", "LA"},
    "sea": {"TH", "VN", "MY", "ID", "PH", "SG", "KH", "LA"},
    "东南亚": {"TH", "VN", "MY", "ID", "PH", "SG", "KH", "LA"},
    "asean": {"TH", "VN", "MY", "ID", "PH", "SG", "KH", "LA"},
}


def assess_region(candidate: dict[str, Any], target_regions: list[str]) -> dict[str, Any]:
    """Return region score/reason/flags for a candidate.

    The assessment is intentionally conservative: explicit country, address or
    ccTLD signals override weak page text. Unknown region is not rejected, only
    marked for later enrichment.
    """

    requested = _requested_country_codes(target_regions)
    if not requested:
        return {
            "region_fit_score": 100,
            "region_confidence": 0.0,
            "region_reason": "未指定目标地区，地区不参与降权。",
            "detected_region_codes": [],
            "target_region_codes": [],
            "region_flags": [],
        }

    direct_hits = _direct_country_hits(candidate)
    weak_hits = _weak_country_hits(candidate)
    detected = sorted(direct_hits | weak_hits)
    flags: list[str] = []

    if direct_hits & requested:
        matched = sorted(direct_hits & requested)
        return _result(100, 0.95, f"地区匹配：明确定位在 {_label_codes(matched)}。", detected, requested, flags)
    if direct_hits and not (direct_hits & requested):
        flags.append("region_mismatch_confirmed")
        return _result(
            0,
            0.9,
            f"地区偏离：明确定位在 {_label_codes(sorted(direct_hits))}，不属于目标地区 {_label_codes(sorted(requested))}。",
            detected,
            requested,
            flags,
        )
    if weak_hits & requested:
        matched = sorted(weak_hits & requested)
        return _result(85, 0.65, f"地区可能匹配：公开文本提到 {_label_codes(matched)}。", detected, requested, flags)
    if weak_hits:
        flags.append("region_mismatch_suspected")
        return _result(
            25,
            0.55,
            f"地区疑似偏离：公开文本更像 {_label_codes(sorted(weak_hits))}，目标为 {_label_codes(sorted(requested))}。",
            detected,
            requested,
            flags,
        )

    flags.append("region_unknown")
    return _result(55, 0.25, f"地区未知：未找到可确认是否属于 {_label_codes(sorted(requested))} 的证据。", [], requested, flags)


def _result(score: int, confidence: float, reason: str, detected: list[str], requested: set[str], flags: list[str]) -> dict[str, Any]:
    return {
        "region_fit_score": score,
        "region_confidence": confidence,
        "region_reason": reason,
        "detected_region_codes": detected,
        "target_region_codes": sorted(requested),
        "region_flags": list(flags),
    }


def _requested_country_codes(target_regions: list[str]) -> set[str]:
    requested: set[str] = set()
    for region in target_regions:
        text = str(region or "").strip().lower()
        if not text:
            continue
        requested.update(REGION_GROUPS.get(text, set()))
        for code, meta in COUNTRY_ALIASES.items():
            if text == code.lower() or text in meta["names"]:
                requested.add(code)
    return requested


def _direct_country_hits(candidate: dict[str, Any]) -> set[str]:
    hits: set[str] = set()
    for value in (candidate.get("country_code"), candidate.get("country")):
        hits.update(_codes_from_text(str(value or "")))
    maps_data = candidate.get("maps_data") if isinstance(candidate.get("maps_data"), dict) else {}
    for value in (candidate.get("address"), maps_data.get("address")):
        hits.update(_codes_from_text(str(value or ""), include_cities=True))
    for value in (candidate.get("website"), candidate.get("link")):
        code = _code_from_domain(str(value or ""))
        if code:
            hits.add(code)
    return hits


def _weak_country_hits(candidate: dict[str, Any]) -> set[str]:
    parts: list[str] = []
    for key in ("company_name", "title", "industry", "description"):
        parts.append(str(candidate.get(key) or ""))
    maps_data = candidate.get("maps_data") if isinstance(candidate.get("maps_data"), dict) else {}
    parts.extend(str(maps_data.get(key) or "") for key in ("title", "description", "type"))
    for item in candidate.get("evidence_items") or candidate.get("evidence") or []:
        if isinstance(item, dict):
            parts.extend(str(item.get(key) or "") for key in ("title", "snippet", "claim", "url", "source_url"))
    return _codes_from_text(" ".join(parts), include_cities=True) | {code for code in (_code_from_domain(url) for url in _urls_from_text(" ".join(parts))) if code}


def _codes_from_text(value: str, *, include_cities: bool = False) -> set[str]:
    text = f" {value.lower()} "
    hits: set[str] = set()
    for code, meta in COUNTRY_ALIASES.items():
        markers = meta["names"] + (meta["cities"] if include_cities else ())
        for marker in markers:
            marker_text = marker.lower()
            if _contains_marker(text, marker_text):
                hits.add(code)
                break
        if _contains_marker(text, code.lower()):
            hits.add(code)
    return hits


def _contains_marker(text: str, marker: str) -> bool:
    if not marker:
        return False
    if re.search(r"[\u4e00-\u9fff\u0e00-\u0e7f]", marker):
        return marker in text
    return re.search(rf"(?<![a-z0-9]){re.escape(marker)}(?![a-z0-9])", text) is not None


def _code_from_domain(url: str) -> str:
    if not url:
        return ""
    host = urlparse(url if "://" in url else f"https://{url}").netloc.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    parts = [part for part in host.split(".") if part]
    if not parts:
        return ""
    tld = parts[-1]
    for code, meta in COUNTRY_ALIASES.items():
        if tld in meta["tlds"]:
            return code
    return ""


def _urls_from_text(text: str) -> list[str]:
    return re.findall(r"https?://[^\s)\]}>\"]+", text or "")


def _label_codes(codes: list[str]) -> str:
    labels = []
    for code in codes:
        names = COUNTRY_ALIASES.get(code, {}).get("names", ())
        labels.append(str(names[0]).title() if names else code)
    return "、".join(labels) or "未知地区"
