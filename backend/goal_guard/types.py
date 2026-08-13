"""Shared schemas for target-customer type enforcement."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class TargetType(StrEnum):
    DENTAL_SCHOOL = "dental_school"
    DENTAL_TRAINING_CENTER = "dental_training_center"
    DENTAL_DISTRIBUTOR = "dental_distributor"
    MEDICAL_DISTRIBUTOR = "medical_consumables_distributor"
    CSSD_SUPPLIER = "cssd_supplier"
    MANUFACTURER = "manufacturer"
    CLINIC = "clinic"
    ASSOCIATION = "association"
    DIRECTORY = "directory"
    MEDIA = "media"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TargetTypeContext:
    customer_types: list[str] = field(default_factory=list)
    product_keywords: list[str] = field(default_factory=list)
    target_regions: list[str] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TargetTypeAssessment:
    target_type: TargetType
    target_type_fit_score: int
    target_type_confidence: float
    target_type_reason: str
    goal_drift_flags: list[str] = field(default_factory=list)
    region_fit_score: int = 100
    region_confidence: float = 0.0
    region_reason: str = "未指定目标地区，地区不参与降权。"
    detected_region_codes: list[str] = field(default_factory=list)
    target_region_codes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "target_type": self.target_type.value,
            "target_type_fit_score": self.target_type_fit_score,
            "target_type_confidence": self.target_type_confidence,
            "target_type_reason": self.target_type_reason,
            "goal_drift_flags": list(self.goal_drift_flags),
            "region_fit_score": self.region_fit_score,
            "region_confidence": self.region_confidence,
            "region_reason": self.region_reason,
            "detected_region_codes": list(self.detected_region_codes),
            "target_region_codes": list(self.target_region_codes),
        }
