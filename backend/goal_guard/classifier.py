"""Rule-first target customer classifier for candidate pools."""

from __future__ import annotations

import json
from typing import Any

from goal_guard.rules import (
    ASSOCIATION_MARKERS,
    CLINIC_MARKERS,
    CSSD_MARKERS,
    DENTAL_MARKERS,
    DIRECTORY_MARKERS,
    DISTRIBUTOR_MARKERS,
    MANUFACTURER_MARKERS,
    MEDICAL_MARKERS,
    MEDIA_MARKERS,
    REQUEST_DENTAL_MARKERS,
    REQUEST_DISTRIBUTOR_MARKERS,
    REQUEST_MEDICAL_MARKERS,
    REQUEST_SCHOOL_MARKERS,
    SCHOOL_MARKERS,
    TRAINING_MARKERS,
)
from goal_guard.region import assess_region
from goal_guard.types import TargetType, TargetTypeAssessment, TargetTypeContext


def classify_candidates(candidates: list[dict[str, Any]], context: TargetTypeContext) -> list[dict[str, Any]]:
    return [classify_candidate(candidate, context) for candidate in candidates if isinstance(candidate, dict)]


def classify_candidate(candidate: dict[str, Any], context: TargetTypeContext) -> dict[str, Any]:
    item = dict(candidate)
    assessment = assess_candidate(item, context)
    item.update(assessment.as_dict())
    return item


def assess_candidate(candidate: dict[str, Any], context: TargetTypeContext) -> TargetTypeAssessment:
    text = _candidate_text(candidate)
    requested = _requested_groups(context)
    target_type = _detect_type(text, requested)
    exclusions = _matched_exclusions(text, context.exclusions)
    flags: list[str] = []

    if exclusions:
        flags.append("matches_exclusion")
    if target_type == TargetType.DIRECTORY:
        flags.append("directory_not_customer")
    if target_type == TargetType.MEDIA:
        flags.append("media_not_customer")
    if target_type == TargetType.CLINIC and "clinic" not in requested:
        flags.append("clinic_excluded")
    if target_type == TargetType.MANUFACTURER and "distributor" in requested:
        flags.append("manufacturer_when_distributor_requested")
    if target_type == TargetType.DENTAL_DISTRIBUTOR and "medical" in requested and "dental" not in requested:
        flags.append("dental_when_medical_requested")
    if target_type in {TargetType.MEDICAL_DISTRIBUTOR, TargetType.CSSD_SUPPLIER} and "dental" in requested and "medical" not in requested:
        flags.append("medical_when_dental_requested")

    region = assess_region(candidate, context.target_regions)
    flags.extend(str(flag) for flag in region.get("region_flags", []) if str(flag or ""))

    score = _fit_score(target_type, requested, bool(exclusions))
    confidence = _confidence(target_type, text)
    reason = _reason(target_type, requested, score, exclusions, flags)
    return TargetTypeAssessment(
        target_type=target_type,
        target_type_fit_score=score,
        target_type_confidence=confidence,
        target_type_reason=reason,
        goal_drift_flags=flags,
        region_fit_score=int(region.get("region_fit_score", 100) or 0),
        region_confidence=float(region.get("region_confidence", 0.0) or 0.0),
        region_reason=str(region.get("region_reason", "")),
        detected_region_codes=[str(item) for item in region.get("detected_region_codes", [])],
        target_region_codes=[str(item) for item in region.get("target_region_codes", [])],
    )


def _detect_type(text: str, requested: set[str]) -> TargetType:
    has_dental = _has_any(text, DENTAL_MARKERS)
    has_medical = _has_any(text, MEDICAL_MARKERS)
    has_cssd = _has_any(text, CSSD_MARKERS)
    if _has_any(text, MEDIA_MARKERS):
        return TargetType.MEDIA
    if _has_any(text, DIRECTORY_MARKERS) and not _has_any(text, SCHOOL_MARKERS + DISTRIBUTOR_MARKERS):
        return TargetType.DIRECTORY
    if has_dental and _has_any(text, TRAINING_MARKERS):
        return TargetType.DENTAL_TRAINING_CENTER
    if has_dental and _has_any(text, SCHOOL_MARKERS):
        return TargetType.DENTAL_SCHOOL
    if _has_any(text, ASSOCIATION_MARKERS) and not _has_any(text, DISTRIBUTOR_MARKERS):
        return TargetType.ASSOCIATION
    if has_cssd and _has_any(text, DISTRIBUTOR_MARKERS):
        return TargetType.CSSD_SUPPLIER
    if has_medical and _has_any(text, DISTRIBUTOR_MARKERS):
        return TargetType.MEDICAL_DISTRIBUTOR
    if has_dental and _has_any(text, DISTRIBUTOR_MARKERS):
        return TargetType.DENTAL_DISTRIBUTOR
    if _has_any(text, MANUFACTURER_MARKERS):
        return TargetType.MANUFACTURER
    if has_dental and _has_any(text, CLINIC_MARKERS):
        return TargetType.CLINIC
    if _has_any(text, DISTRIBUTOR_MARKERS):
        if "medical" in requested or "cssd" in requested:
            return TargetType.MEDICAL_DISTRIBUTOR
        return TargetType.DENTAL_DISTRIBUTOR
    return TargetType.UNKNOWN


def _requested_groups(context: TargetTypeContext) -> set[str]:
    text = " ".join([*context.customer_types, *context.product_keywords]).lower()
    groups: set[str] = set()
    if _has_any(text, REQUEST_SCHOOL_MARKERS):
        groups.add("school")
    if _has_any(text, TRAINING_MARKERS):
        groups.add("training")
    if _has_any(text, REQUEST_DISTRIBUTOR_MARKERS):
        groups.add("distributor")
    if _has_any(text, REQUEST_MEDICAL_MARKERS):
        groups.add("medical")
    if _has_any(text, CSSD_MARKERS):
        groups.add("cssd")
    if _has_any(text, REQUEST_DENTAL_MARKERS):
        groups.add("dental")
    if _has_any(text, CLINIC_MARKERS):
        groups.add("clinic")
    return groups or {"general_b2b"}


def _fit_score(target_type: TargetType, requested: set[str], excluded: bool) -> int:
    if excluded:
        return 0
    if target_type in {TargetType.DIRECTORY, TargetType.MEDIA}:
        return 5
    if target_type == TargetType.ASSOCIATION:
        return 20
    if target_type == TargetType.CLINIC:
        return 80 if "clinic" in requested else 10
    if target_type == TargetType.DENTAL_SCHOOL:
        return 100 if "school" in requested else 60 if "general_b2b" in requested else 35
    if target_type == TargetType.DENTAL_TRAINING_CENTER:
        return 100 if requested & {"school", "training"} else 60 if "general_b2b" in requested else 40
    if target_type == TargetType.DENTAL_DISTRIBUTOR:
        if "medical" in requested and "dental" not in requested:
            return 30
        return 100 if "distributor" in requested else 45 if requested & {"school", "training"} else 60
    if target_type == TargetType.CSSD_SUPPLIER:
        return 100 if requested & {"cssd", "medical", "distributor"} else 65
    if target_type == TargetType.MEDICAL_DISTRIBUTOR:
        if "dental" in requested and "medical" not in requested:
            return 30
        return 100 if requested & {"medical", "cssd", "distributor"} else 60
    if target_type == TargetType.MANUFACTURER:
        return 15 if "distributor" in requested else 35 if requested & {"school", "training"} else 60
    return 60 if "general_b2b" in requested else 20


def _confidence(target_type: TargetType, text: str) -> float:
    if target_type == TargetType.UNKNOWN:
        return 0.25
    hits = sum(1 for markers in (DENTAL_MARKERS, MEDICAL_MARKERS, CSSD_MARKERS, SCHOOL_MARKERS, TRAINING_MARKERS, DISTRIBUTOR_MARKERS, MANUFACTURER_MARKERS) if _has_any(text, markers))
    return min(0.95, 0.55 + hits * 0.12)


def _reason(target_type: TargetType, requested: set[str], score: int, exclusions: list[str], flags: list[str]) -> str:
    requested_label = "、".join(sorted(requested))
    if exclusions:
        return "命中排除对象：" + "、".join(exclusions)
    if "manufacturer_when_distributor_requested" in flags:
        return "该候选更像制造商/工厂，不符合经销商或代理商优先目标。"
    if "dental_when_medical_requested" in flags:
        return "该候选更像牙科渠道，本次目标是医疗耗材/CSSD 渠道，降低推荐优先级。"
    if "medical_when_dental_requested" in flags:
        return "该候选更像医疗耗材渠道，本次目标是牙科渠道，降低推荐优先级。"
    if "clinic_excluded" in flags:
        return "该候选更像普通牙科诊所，不符合当前目标客户类型。"
    if target_type in {TargetType.DIRECTORY, TargetType.MEDIA}:
        return "该页面更像目录/媒体内容，只适合作为证据来源。"
    if score >= 90:
        return f"目标类型匹配：{target_type.value} 符合本次目标 {requested_label}。"
    if score >= 50:
        return f"目标类型部分匹配：{target_type.value} 可作为候补继续补全。"
    return f"目标类型偏离：{target_type.value} 与本次目标 {requested_label} 匹配较弱。"


def _matched_exclusions(text: str, exclusions: list[str]) -> list[str]:
    matched: list[str] = []
    for exclusion in exclusions:
        clean = str(exclusion or "").strip().lower()
        if clean and clean in text:
            matched.append(str(exclusion))
    return matched


def _candidate_text(candidate: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "company_name", "title", "website", "industry", "description", "address",
        "customer_type", "customer_role", "priority_tier", "source_keyword", "ranking_reason",
    ):
        parts.append(str(candidate.get(key) or ""))
    for value in candidate.get("source_channels") or []:
        parts.append(str(value or ""))
    for item in candidate.get("evidence_items") or candidate.get("evidence") or []:
        if isinstance(item, dict):
            parts.extend(str(item.get(key) or "") for key in ("title", "snippet", "claim", "source", "url"))
            raw = item.get("raw")
            if isinstance(raw, dict):
                parts.append(json.dumps(raw, ensure_ascii=False))
    social = candidate.get("social_media") if isinstance(candidate.get("social_media"), dict) else {}
    parts.extend(str(value or "") for value in social.values())
    return " ".join(parts).lower()


def _has_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker.lower() in text for marker in markers if marker)
