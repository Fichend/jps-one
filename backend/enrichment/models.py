"""Shared models for candidate enrichment."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


EnrichmentStatus = Literal[
    "not_started",
    "pending",
    "enriched",
    "partial",
    "failed",
    "budget_limited",
    "skipped",
]

TaskType = Literal[
    "find_website",
    "extract_website",
    "crawl_website",
    "search_instagram_by_company",
    "search_facebook_by_company",
]


@dataclass(slots=True)
class EnrichmentTask:
    candidate_id: str
    task_type: TaskType
    query_or_url: str
    missing_fields: list[str] = field(default_factory=list)
    source: str = "candidate_enrichment"
    company_name: str = ""
    country: str = ""
    website: str = ""


@dataclass(slots=True)
class EnrichmentResult:
    candidate_id: str
    task_type: TaskType
    query_or_url: str
    source: str
    status: EnrichmentStatus
    message: str = ""
    items: list[dict[str, Any]] = field(default_factory=list)
    evidence_items: list[dict[str, Any]] = field(default_factory=list)
    cost_usd: float = 0.0

    def trace_item(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type,
            "source": self.source,
            "status": self.status,
            "query_or_url": self.query_or_url,
            "message": self.message,
            "items": len(self.items),
            "cost_usd": self.cost_usd,
        }
