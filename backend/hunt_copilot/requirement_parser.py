"""Conservative extraction and sanitation for complete search requirements."""

from __future__ import annotations

import re
from typing import Any

from hunt_copilot.strategy_commands import COUNTRY_ALIASES, HARD_FIELD_ALIASES


_STOP_FIELD_PATTERN = r"(?:排除|不要|必须|硬条件|候选|最终|预算|exclude|must have|required|candidate|final|budget)"
_PRODUCT_NOISE = (
    "必须", "官网", "邮箱", "电话", "地址", "instagram", "facebook", "排除", "不要", "候选", "最终", "预算",
    "must have", "required", "exclude", "candidate", "final leads", "budget", "customer type", "target region",
)


def explicit_requirement_patch(message: str) -> dict[str, Any]:
    text = _clean(message)
    patch: dict[str, Any] = {}
    regions = countries_in_text(text)
    if regions:
        patch["target_regions"] = regions

    customers = _customer_types(text)
    if customers:
        patch["customer_types"] = customers

    products = _product_keywords(text)
    if products:
        patch["product_keywords"] = products

    exclusions = _exclusions(text)
    if exclusions:
        patch["exclusions"] = exclusions

    hard = _hard_filters(text)
    if hard:
        patch["hard_filters"] = hard

    budget = _budget(text)
    if budget:
        patch["budget"] = budget
    return patch


def sanitize_planner_patch(message: str, planner_patch: dict[str, Any]) -> dict[str, Any]:
    explicit = explicit_requirement_patch(message)
    clean = dict(planner_patch or {})
    for field_name in ("target_regions", "customer_types", "product_keywords", "exclusions"):
        if field_name in explicit:
            clean[field_name] = explicit[field_name]

    if "product_keywords" in explicit:
        clean["product_keywords"] = explicit["product_keywords"]
    else:
        # The model may surface catalogue recommendations in its patch. Those
        # remain suggestions until the user explicitly provides/adopts them.
        clean.pop("product_keywords", None)

    if "hard_filters" in explicit:
        current = clean.get("hard_filters") if isinstance(clean.get("hard_filters"), dict) else {}
        clean["hard_filters"] = {**current, **explicit["hard_filters"]}
    if "budget" in explicit:
        current_budget = clean.get("budget") if isinstance(clean.get("budget"), dict) else {}
        clean["budget"] = {**current_budget, **explicit["budget"]}
    return clean


def sanitize_product_keywords(values: Any) -> list[str]:
    incoming = values if isinstance(values, list) else [values]
    countries = {alias.casefold() for alias in COUNTRY_ALIASES} | {value.casefold() for value in COUNTRY_ALIASES.values()}
    result: list[str] = []
    for value in incoming:
        clean = _strip(str(value or ""))
        lower = clean.casefold()
        if not clean or lower in countries:
            continue
        if any(marker in lower for marker in _PRODUCT_NOISE):
            continue
        if clean not in result:
            result.append(clean)
    return result


def countries_in_text(message: str) -> list[str]:
    lower = message.casefold()
    matches: list[tuple[int, str]] = []
    for alias, canonical in COUNTRY_ALIASES.items():
        pattern = rf"(?<![a-z]){re.escape(alias)}(?![a-z])" if alias.isascii() else re.escape(alias)
        match = re.search(pattern, lower, flags=re.IGNORECASE)
        if match:
            matches.append((match.start(), canonical))
    return _unique([value for _, value in sorted(matches)])


def _product_keywords(text: str) -> list[str]:
    exclusive = re.search(
        rf"(?:只要|只用|只保留|仅保留|use only|keep only)\s*(?P<value>.+?)(?=\s*[,，;；]\s*{_STOP_FIELD_PATTERN}|$)",
        text,
        flags=re.IGNORECASE,
    )
    if exclusive:
        sanitized = sanitize_product_keywords(_split(exclusive.group("value"), split_chinese_and=False))
        if sanitized:
            return sanitized
    patterns = (
        rf"(?:产品关键词|产品)(?:是|为|[:：])?\s*(?P<value>.+?)(?=\s*[,，;；]\s*{_STOP_FIELD_PATTERN}|$)",
        rf"\bproduct(?:\s+keywords?)?\s*(?:is|are|:)?\s*(?P<value>.+?)(?=\s*[,;]\s*{_STOP_FIELD_PATTERN}|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        values = _split(match.group("value"), split_chinese_and=False)
        sanitized = sanitize_product_keywords(values)
        if sanitized:
            return sanitized
    implicit = _implicit_product_phrase(text)
    if implicit:
        return sanitize_product_keywords([implicit])
    return []


def _customer_types(text: str) -> list[str]:
    lower = text.casefold()
    known_roles = (
        ("普通牙科诊所", "general dental clinic"), ("牙科学校", "dental school"),
        ("培训中心", "training center"), ("经销商", "distributor"), ("代理商", "distributor"),
        ("进口商", "importer"), ("供应商", "supplier"), ("制造商", "manufacturer"),
        ("医院", "hospital"), ("诊所", "clinic"),
        ("distributors", "distributor"), ("distributor", "distributor"),
        ("dealers", "distributor"), ("dealer", "distributor"),
        ("importers", "importer"), ("importer", "importer"),
        ("suppliers", "supplier"), ("supplier", "supplier"),
        ("manufacturers", "manufacturer"), ("manufacturer", "manufacturer"),
        ("hospitals", "hospital"), ("hospital", "hospital"),
        ("clinics", "clinic"), ("clinic", "clinic"),
        ("dental schools", "dental school"), ("dental school", "dental school"),
    )
    detected = [canonical for marker, canonical in known_roles if _token_present(lower, marker)]
    if detected:
        return _unique(detected)
    prefix = re.split(r"(?:产品关键词|产品|排除|必须|硬条件|候选|最终|预算|\bproduct\b|\bexclude\b|\bmust have\b)", text, maxsplit=1, flags=re.IGNORECASE)[0]
    for alias in sorted(COUNTRY_ALIASES, key=len, reverse=True):
        prefix = re.sub(re.escape(alias), " ", prefix, flags=re.IGNORECASE)
    prefix = re.sub(r"^(?:我要找|我需要|帮我找|帮我整点|寻找|找|need|find|looking for)\s*", "", prefix, flags=re.IGNORECASE)
    prefix = re.sub(r"^(?:的|做|一些|一批)\s*", "", prefix).strip(" ,，;；的")

    role_markers = (
        "经销商", "进口商", "供应商", "代理商", "培训中心", "牙科学校", "学校", "医院", "诊所",
        "distributor", "distributors", "importer", "importers", "supplier", "suppliers", "dealer", "dealers",
        "hospital", "hospitals", "clinic", "clinics", "school", "schools", "training center", "training centers",
    )
    if not any(marker in prefix.casefold() for marker in role_markers):
        return []
    values = _split(prefix, split_chinese_and=True)
    return _unique([_strip_customer(value) for value in values if _strip_customer(value)])


def _implicit_product_phrase(text: str) -> str:
    clean = text
    clean = re.sub(r"^(?:我要找|我需要|帮我找|帮我整点|寻找|找|need|find|looking for)\s*", "", clean, flags=re.IGNORECASE)
    for alias in sorted(COUNTRY_ALIASES, key=len, reverse=True):
        clean = re.sub(rf"(?<![a-z]){re.escape(alias)}(?![a-z])" if alias.isascii() else re.escape(alias), " ", clean, flags=re.IGNORECASE)
    role_pattern = (
        r"(?:医疗耗材|牙科设备)?(?:经销商|代理商|进口商|供应商|制造商|医院|诊所|牙科学校|培训中心)"
        r"|(?:medical consumables?\s+)?(?:distributors?|dealers?|importers?|suppliers?|manufacturers?|hospitals?|clinics?|dental schools?)"
    )
    prefix = re.split(role_pattern, clean, maxsplit=1, flags=re.IGNORECASE)[0]
    prefix = re.split(r"(?:排除|不要|必须|硬条件|候选|最终|预算|exclude|without|must have|required|candidate|final|budget)", prefix, maxsplit=1, flags=re.IGNORECASE)[0]
    prefix = _strip(prefix)
    prefix = re.sub(r"^(?:的|做|一些|一批)\s*", "", prefix).strip()
    return prefix if 2 <= len(prefix) <= 80 else ""


def _exclusions(text: str) -> list[str]:
    match = re.search(
        rf"(?:排除|不要(?:包含)?|exclude|without)\s*(?P<value>.+?)(?=\s*[,，;；]\s*(?:必须|硬条件|候选|最终|预算|产品|must have|required|candidate|final|budget|product)|$)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return []
    return _unique([_normalize_exclusion(value) for value in _split(match.group("value"), split_chinese_and=True) if _normalize_exclusion(value)])


def _hard_filters(text: str) -> dict[str, bool]:
    lower = text.casefold()
    if not any(marker in lower for marker in ("必须", "要官网", "要邮箱", "要电话", "must have", "required", "硬条件")):
        return {}
    result: dict[str, bool] = {}
    for alias, field_name in HARD_FIELD_ALIASES.items():
        if _token_present(lower, alias):
            result[field_name] = True
    return result


def _budget(text: str) -> dict[str, Any]:
    lower = text.casefold()
    result: dict[str, Any] = {}
    candidate = re.search(r"(?:候选|candidate(?:s)?)\s*(?:池|数量|先找)?\s*(\d+)", lower)
    final = re.search(r"(?:最终|入库|top|final(?: leads?)?)\s*(?:只要|数量)?\s*(\d+)", lower)
    money = re.search(r"(?:预算|budget)\s*(?:控制在|为|是|:)?\s*(\d+(?:\.\d+)?)\s*(?:usd|美元|美金|\$)?", lower)
    if candidate:
        result["max_candidates"] = int(candidate.group(1))
    if final:
        result["final_leads"] = int(final.group(1))
    if money:
        result["total_usd"] = float(money.group(1))
    return result


def _split(value: str, *, split_chinese_and: bool) -> list[str]:
    separators = r",|，|、|;|；|\band\b|以及"
    if split_chinese_and:
        separators += r"|和"
    return [_strip(item) for item in re.split(rf"\s*(?:{separators})\s*", value, flags=re.IGNORECASE) if _strip(item)]


def _strip_customer(value: str) -> str:
    clean = _strip(value)
    clean = re.sub(r"^(?:的|做|一些|一批)", "", clean).strip()
    return clean


def _normalize_exclusion(value: str) -> str:
    clean = _strip(value)
    return {
        "医院": "hospital", "诊所": "clinic", "普通牙科诊所": "general dental clinic", "制造商": "manufacturer",
        "电商平台": "e-commerce platform", "个人账号": "personal account",
    }.get(clean.casefold(), clean)


def _token_present(text: str, token: str) -> bool:
    if token.isascii():
        return bool(re.search(rf"(?<![a-z]){re.escape(token)}(?![a-z])", text, flags=re.IGNORECASE))
    return token in text


def _strip(value: str) -> str:
    return str(value or "").strip(" '\"：:，,。.;；")


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value or "").strip()
        key = clean.casefold()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result
