"""Structured semantic output used by the new Hunt Copilot brain."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field


SlotSource = Literal["explicit", "inferred", "catalogue", "memory", "rule"]


class SlotValue(BaseModel):
    value: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_text: str = ""
    source: SlotSource = "inferred"


class SemanticSlots(BaseModel):
    target_regions: list[SlotValue] = Field(default_factory=list)
    customer_types: list[SlotValue] = Field(default_factory=list)
    product_keywords: list[SlotValue] = Field(default_factory=list)
    application_scenarios: list[SlotValue] = Field(default_factory=list)
    exclusions: list[SlotValue] = Field(default_factory=list)
    required_fields: list[SlotValue] = Field(default_factory=list)
    preferred_fields: list[SlotValue] = Field(default_factory=list)
    business_notes: list[SlotValue] = Field(default_factory=list)
    budget: dict[str, Any] = Field(default_factory=dict)


class SemanticExtraction(BaseModel):
    intent: str = "provide_requirement"
    slots: SemanticSlots = Field(default_factory=SemanticSlots)
    uncertain_fields: list[str] = Field(default_factory=list)
    assistant_message: str = ""
    raw_model_output: dict[str, Any] = Field(default_factory=dict)


@dataclass
class GuardrailResult:
    slots: SemanticSlots
    detected_conflicts: list[str] = field(default_factory=list)
    rejected_fields: dict[str, list[str]] = field(default_factory=dict)
    business_notes: list[str] = field(default_factory=list)


@dataclass
class ComposeResult:
    strategy: Any
    changed: bool
    recent_changes: list[str] = field(default_factory=list)
