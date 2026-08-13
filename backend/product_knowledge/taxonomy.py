"""JPS product department and category rules.

This module is intentionally deterministic. The LLM may propose fields, but the
search direction is locked here so dental and medical consumables tasks do not
drift into each other.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


DENTAL = "dental"
MEDICAL_CONSUMABLES = "medical_consumables"
UNCLEAR = "unclear"

DENTAL_TEACHING_LAB = "dental_teaching_lab"
DENTAL_EQUIPMENT = "dental_equipment"
DENTAL_CONSUMABLES = "dental_consumables"
MEDICAL_PPE_CONSUMABLES = "medical_ppe_consumables"
SURGICAL_PACKS = "surgical_packs"
CSSD_STERILIZATION = "cssd_sterilization"
GENERAL_HOSPITAL_CONSUMABLES = "general_hospital_consumables"


DEPARTMENT_LABELS = {
    DENTAL: "牙科",
    MEDICAL_CONSUMABLES: "医疗耗材",
    UNCLEAR: "待确认",
}

CATEGORY_LABELS = {
    DENTAL_TEACHING_LAB: "牙科教学实验室产品",
    DENTAL_EQUIPMENT: "牙科设备",
    DENTAL_CONSUMABLES: "牙科耗材",
    MEDICAL_PPE_CONSUMABLES: "医疗防护/PPE耗材",
    SURGICAL_PACKS: "手术包",
    CSSD_STERILIZATION: "CSSD/灭菌耗材",
    GENERAL_HOSPITAL_CONSUMABLES: "医院通用耗材",
    UNCLEAR: "待确认",
}


@dataclass(frozen=True)
class ProductDirection:
    department: str = UNCLEAR
    category: str = UNCLEAR
    confidence: float = 0.0
    reason: str = ""


def infer_product_direction(
    *,
    text: str = "",
    product_keywords: list[str] | None = None,
    customer_types: list[str] | None = None,
    application_scenarios: list[str] | None = None,
) -> ProductDirection:
    clean_text = _remove_exclusion_clauses(text or "")
    haystack = _norm(" ".join([clean_text, " ".join(product_keywords or []), " ".join(customer_types or []), " ".join(application_scenarios or [])]))
    if not haystack:
        return ProductDirection()

    category = _infer_category(haystack)
    dental_score = _score(haystack, DENTAL_SIGNALS)
    medical_score = _score(haystack, MEDICAL_SIGNALS)

    if category in {DENTAL_TEACHING_LAB, DENTAL_EQUIPMENT, DENTAL_CONSUMABLES}:
        dental_score += 4
    if category in {MEDICAL_PPE_CONSUMABLES, SURGICAL_PACKS, CSSD_STERILIZATION, GENERAL_HOSPITAL_CONSUMABLES}:
        medical_score += 4

    if dental_score == 0 and medical_score == 0:
        return ProductDirection(category=category, confidence=0.25 if category != UNCLEAR else 0.0, reason="未找到明确部门信号")
    if dental_score >= medical_score + 2:
        if category == UNCLEAR:
            category = DENTAL_CONSUMABLES if _score(haystack, DENTAL_CONSUMABLE_SIGNALS) else DENTAL_EQUIPMENT
        return ProductDirection(DENTAL, category, min(0.98, 0.68 + dental_score * 0.04), "命中牙科部门信号")
    if medical_score >= dental_score + 2:
        if category == UNCLEAR:
            category = CSSD_STERILIZATION if _score(haystack, CSSD_SIGNALS) else GENERAL_HOSPITAL_CONSUMABLES
        return ProductDirection(MEDICAL_CONSUMABLES, category, min(0.98, 0.68 + medical_score * 0.04), "命中医疗耗材部门信号")
    return ProductDirection(UNCLEAR, category, 0.45, "牙科与医疗耗材信号接近，需要业务员确认")


def specialize_customer_types(customer_types: list[str], *, department: str, category: str, raw_text: str = "") -> list[str]:
    result: list[str] = []
    text = _norm(raw_text)
    for item in customer_types:
        clean = _clean(item)
        key = clean.lower()
        if not clean:
            continue
        if key == "hospital" and department == MEDICAL_CONSUMABLES and _score(text, CSSD_SCENARIO_SIGNALS):
            continue
        if key in GENERIC_DISTRIBUTION_ROLES:
            result.extend(_specialized_role(key, department=department, category=category))
        else:
            result.append(clean)
    if department == MEDICAL_CONSUMABLES and category == CSSD_STERILIZATION:
        has_cssd_channel = any("cssd" in item.lower() or "sterilization" in item.lower() for item in result)
        if has_cssd_channel and not any(item.lower() == "medical consumables distributor" for item in result):
            result.insert(0, "medical consumables distributor")
        if not any("cssd" in item.lower() for item in result):
            result.append("CSSD supplier")
    return _dedupe(result)


def specialize_exclusions(exclusions: list[str], *, department: str = UNCLEAR, category: str = UNCLEAR) -> list[str]:
    cleaned = _dedupe([_clean(item) for item in exclusions if _clean(item)])
    if any(_is_specific_distribution_exclusion(item) for item in cleaned):
        cleaned = [item for item in cleaned if item.lower() not in GENERIC_DISTRIBUTION_ROLES]
    if any(item.lower() in {"general dental clinic", "dental clinic"} for item in cleaned):
        cleaned = [item for item in cleaned if item.lower() != "clinic"]
    return cleaned


def department_allowed_customer_types(department: str, category: str) -> list[str]:
    if department == DENTAL:
        if category == DENTAL_TEACHING_LAB:
            return ["dental school", "dental training center", "dental equipment distributor"]
        if category == DENTAL_CONSUMABLES:
            return ["dental consumables distributor", "dental supplies importer", "dental equipment distributor"]
        return ["dental equipment distributor", "dental supplies importer", "dental school"]
    if department == MEDICAL_CONSUMABLES:
        if category == CSSD_STERILIZATION:
            return ["medical consumables distributor", "medical consumables importer", "CSSD supplier", "hospital supplies distributor"]
        if category == SURGICAL_PACKS:
            return ["medical consumables distributor", "hospital supplies distributor", "medical supplies wholesaler"]
        return ["medical consumables distributor", "medical consumables importer", "hospital supplies distributor", "medical supplies wholesaler"]
    return []


def direction_summary(department: str, category: str) -> str:
    return f"{DEPARTMENT_LABELS.get(department, department or '待确认')} / {CATEGORY_LABELS.get(category, category or '待确认')}"


def _infer_category(text: str) -> str:
    if _score(text, DENTAL_TEACHING_SIGNALS):
        return DENTAL_TEACHING_LAB
    if _score(text, DENTAL_EQUIPMENT_SIGNALS):
        return DENTAL_EQUIPMENT
    if _score(text, DENTAL_CONSUMABLE_SIGNALS):
        return DENTAL_CONSUMABLES
    if _score(text, CSSD_SIGNALS):
        return CSSD_STERILIZATION
    if _score(text, PPE_SIGNALS):
        return MEDICAL_PPE_CONSUMABLES
    if _score(text, SURGICAL_PACK_SIGNALS):
        return SURGICAL_PACKS
    if _score(text, HOSPITAL_CONSUMABLE_SIGNALS):
        return GENERAL_HOSPITAL_CONSUMABLES
    return UNCLEAR


def _specialized_role(role: str, *, department: str, category: str) -> list[str]:
    if department == DENTAL:
        if role == "importer":
            return ["dental supplies importer"]
        if category == DENTAL_CONSUMABLES:
            return ["dental consumables distributor"]
        return ["dental equipment distributor"]
    if department == MEDICAL_CONSUMABLES:
        if role == "importer":
            return ["medical consumables importer"]
        if category == CSSD_STERILIZATION:
            return ["medical consumables distributor"]
        return ["medical consumables distributor"]
    return [role]


def _is_specific_distribution_exclusion(value: str) -> bool:
    lower = value.lower()
    return any(token in lower for token in ("dental equipment distributor", "dental consumables distributor", "medical consumables distributor", "hospital supplies distributor", "cssd supplier", "sterilization products distributor"))


def _score(text: str, signals: tuple[str, ...]) -> int:
    return sum(1 for signal in signals if signal and signal in text)


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip(" ，,。.;；:'\""))


def _remove_exclusion_clauses(value: str) -> str:
    text = str(value or "")
    return re.sub(
        r"(?:排除|不要(?:包含)?|exclude|without)\s*([^。；;\n]+)",
        " ",
        text,
        flags=re.IGNORECASE,
    )


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = _clean(value)
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result


GENERIC_DISTRIBUTION_ROLES = {"distributor", "supplier", "importer", "dealer", "agent"}

DENTAL_SIGNALS = (
    "dental", "dentistry", "odont", "牙科", "口腔", "dentist", "phantom head", "manikin", "牙科设备", "牙科耗材",
)
MEDICAL_SIGNALS = (
    "medical consumables", "medical disposables", "hospital supplies", "cssd", "cme", "医疗耗材", "医用耗材", "医院耗材", "消毒供应中心", "医用灭菌", "chemical indicator", "biological indicator",
)
DENTAL_TEACHING_SIGNALS = (
    "dental simulator", "phantom head", "dental manikin", "teeth model", "workstation", "simulation lab", "牙科模拟", "仿头模", "牙齿模型", "牙科教学",
)
DENTAL_EQUIPMENT_SIGNALS = (
    "dental unit", "handpiece", "curing light", "ultrasonic scaler", "intraoral camera", "x-ray", "imaging system", "autoclave", "牙椅", "牙科手机", "洁牙机", "口内相机", "牙科设备",
)
DENTAL_CONSUMABLE_SIGNALS = (
    "dental disposable", "dental disposables", "dental bib", "dental burs", "diamond instruments", "dental sterilization packaging", "牙科耗材", "牙科一次性", "牙钻", "金刚砂车针",
)
PPE_SIGNALS = (
    "surgical gown", "isolation gown", "scrub suit", "coverall", "face mask", "headwear", "footwear", "glove", "手术衣", "隔离衣", "口罩", "手套", "鞋套", "帽",
)
SURGICAL_PACK_SIGNALS = ("surgical pack", "手术包")
CSSD_SIGNALS = (
    "cssd", "cme", "central sterile", "sterilization product", "sterilization products", "chemical indicator", "biological indicator", "indicator tape", "indicator label", "sterilization reel", "sterilization roll", "crepe paper", "wrapping sheet", "tyvek", "sealing machine", "medical grade paper", "smms", "seal check", "washer indicator", "消毒供应中心", "灭菌耗材", "灭菌指示", "化学指示", "生物指示", "灭菌卷", "灭菌包装", "皱纹纸", "特卫强", "医用封口", "灭菌篮",
)
HOSPITAL_CONSUMABLE_SIGNALS = (
    "medical material in roll", "incontinence", "bandage", "wound dressing", "syringe", "needle", "gauze", "cotton", "医用胶带", "绷带", "敷料", "纱布", "注射器", "针", "失禁",
)
CSSD_SCENARIO_SIGNALS = ("cssd", "cme", "消毒供应中心", "central sterile", "医院消毒供应中心")
