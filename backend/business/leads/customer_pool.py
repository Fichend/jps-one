"""Customer pool grouping and import logic."""

from __future__ import annotations

import hashlib
from typing import Any, Callable

from pydantic import BaseModel, Field

from business.leads.dedupe import dedupe_leads, lead_key
from scoring.response_scoring import ensure_jps_score


class LeadSourceHunt(BaseModel):
    hunt_id: str
    created_at: str = ""
    status: str = ""
    website_url: str = ""
    product_keywords: list[str] = Field(default_factory=list)
    target_regions: list[str] = Field(default_factory=list)


class LeadPoolItem(BaseModel):
    lead_id: str
    company_name: str = ""
    website: str = ""
    country_code: str = ""
    industry: str = ""
    customer_role: str = ""
    description: str = ""
    emails: list[str] = Field(default_factory=list)
    phone_numbers: list[str] = Field(default_factory=list)
    social_media: dict[str, str] = Field(default_factory=dict)
    social_profiles: list[dict[str, Any]] = Field(default_factory=list)
    jps_score: int = 0
    lead_grade: str = ""
    score_breakdown: dict[str, Any] = Field(default_factory=dict)
    scoring_version: str = ""
    fit_score: float = 0.0
    contactability_score: float = 0.0
    priority_tier: str = "low"
    evidence_strength: str = ""
    latest_hunt_at: str = ""
    source_hunts: list[LeadSourceHunt] = Field(default_factory=list)


class LeadPoolSummary(BaseModel):
    total_leads: int
    with_email: int
    high_fit: int
    country_count: int
    source_hunt_count: int


class LeadPoolTaskGroup(BaseModel):
    source: LeadSourceHunt
    imported_at: str = ""
    lead_count: int
    leads: list[LeadPoolItem]


class LeadPoolResponse(BaseModel):
    summary: LeadPoolSummary
    groups: list[LeadPoolTaskGroup]


class ImportHuntLeadsResponse(BaseModel):
    hunt_id: str
    status: str
    imported_at: str
    lead_count: int


class CustomerPoolImportError(ValueError):
    """Raised when a hunt cannot be imported into the customer pool."""


def _lead_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item or "").strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _lead_social(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(k): str(v) for k, v in value.items() if str(v or "").strip()}


def _lead_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _lead_pool_id(key: str) -> str:
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def _lead_social_profiles(lead: dict[str, Any]) -> list[dict[str, Any]]:
    profiles = lead.get("social_profiles") or lead.get("social_enrichment") or []
    if isinstance(profiles, list):
        return [item for item in profiles if isinstance(item, dict)]
    if isinstance(profiles, dict):
        return [profiles]
    return []


def build_lead_pool(hunts: dict[str, dict[str, Any]]) -> LeadPoolResponse:
    groups: list[LeadPoolTaskGroup] = []
    global_keys: set[str] = set()
    source_hunt_ids: set[str] = set()
    with_email_keys: set[str] = set()
    high_fit_keys: set[str] = set()
    countries: set[str] = set()

    for hunt_id, hunt in hunts.items():
        imported_at = str(hunt.get("customer_pool_imported_at") or "")
        if not imported_at:
            continue
        result = hunt.get("result") or {}
        raw_leads = result.get("leads") or []
        if not isinstance(raw_leads, list):
            continue

        source = LeadSourceHunt(
            hunt_id=hunt_id,
            created_at=str(hunt.get("created_at") or ""),
            status=str(hunt.get("status") or ""),
            website_url=str(hunt.get("website_url") or result.get("website_url") or ""),
            product_keywords=list(hunt.get("product_keywords") or result.get("product_keywords") or []),
            target_regions=list(hunt.get("target_regions") or result.get("target_regions") or []),
        )
        task_items: dict[str, dict[str, Any]] = {}

        for lead in raw_leads:
            if not isinstance(lead, dict):
                continue
            lead = ensure_jps_score(lead)
            key = lead_key(lead)
            existing = task_items.get(key)
            if existing is None:
                existing = {
                    "lead_id": _lead_pool_id(key),
                    "company_name": str(lead.get("company_name") or ""),
                    "website": str(lead.get("website") or ""),
                    "country_code": str(lead.get("country_code") or lead.get("country") or ""),
                    "industry": str(lead.get("industry") or ""),
                    "customer_role": str(lead.get("customer_role") or ""),
                    "description": str(lead.get("description") or ""),
                    "emails": _lead_list(lead.get("emails")),
                    "phone_numbers": _lead_list(lead.get("phone_numbers") or lead.get("phones")),
                    "social_media": _lead_social(lead.get("social_media")),
                    "social_profiles": _lead_social_profiles(lead),
                    "jps_score": int(_lead_float(lead.get("jps_score"))),
                    "lead_grade": str(lead.get("lead_grade") or ""),
                    "score_breakdown": lead.get("score_breakdown") if isinstance(lead.get("score_breakdown"), dict) else {},
                    "scoring_version": str(lead.get("scoring_version") or ""),
                    "fit_score": _lead_float(lead.get("fit_score") or lead.get("match_score")),
                    "contactability_score": _lead_float(lead.get("contactability_score")),
                    "priority_tier": str(lead.get("priority_tier") or "low"),
                    "evidence_strength": str(lead.get("evidence_strength") or ""),
                    "latest_hunt_at": source.created_at,
                    "source_hunts": [],
                }
                task_items[key] = existing
            else:
                existing["emails"] = sorted(set(existing["emails"]) | set(_lead_list(lead.get("emails"))))
                existing["phone_numbers"] = sorted(set(existing["phone_numbers"]) | set(_lead_list(lead.get("phone_numbers") or lead.get("phones"))))
                existing["social_media"] = {**existing["social_media"], **_lead_social(lead.get("social_media"))}
                existing["social_profiles"].extend(_lead_social_profiles(lead))
                if int(_lead_float(lead.get("jps_score"))) > int(existing.get("jps_score", 0) or 0):
                    existing["jps_score"] = int(_lead_float(lead.get("jps_score")))
                    existing["lead_grade"] = str(lead.get("lead_grade") or existing.get("lead_grade") or "")
                    existing["score_breakdown"] = lead.get("score_breakdown") if isinstance(lead.get("score_breakdown"), dict) else existing.get("score_breakdown", {})
                    existing["scoring_version"] = str(lead.get("scoring_version") or existing.get("scoring_version") or "")
                existing["fit_score"] = max(existing["fit_score"], _lead_float(lead.get("fit_score") or lead.get("match_score")))
                existing["contactability_score"] = max(existing["contactability_score"], _lead_float(lead.get("contactability_score")))
                if source.created_at > existing.get("latest_hunt_at", ""):
                    existing["latest_hunt_at"] = source.created_at
                for field in ("company_name", "website", "country_code", "industry", "customer_role", "description", "evidence_strength"):
                    if not existing.get(field):
                        existing[field] = str(lead.get(field) or "")

            if not any(item.hunt_id == hunt_id for item in existing["source_hunts"]):
                existing["source_hunts"].append(source)
                source_hunt_ids.add(hunt_id)

            global_keys.add(key)
            if existing["emails"]:
                with_email_keys.add(key)
            if existing.get("jps_score", 0) >= 80 or existing["fit_score"] >= 0.7:
                high_fit_keys.add(key)
            if existing["country_code"]:
                countries.add(existing["country_code"])

        leads = [LeadPoolItem(**item) for item in task_items.values()]
        leads.sort(key=lambda item: (item.jps_score, item.fit_score, item.company_name.lower()), reverse=True)
        if leads:
            groups.append(LeadPoolTaskGroup(source=source, imported_at=imported_at, lead_count=len(leads), leads=leads))

    groups.sort(key=lambda group: (group.imported_at, group.source.created_at), reverse=True)
    return LeadPoolResponse(
        summary=LeadPoolSummary(
            total_leads=len(global_keys),
            with_email=len(with_email_keys),
            high_fit=len(high_fit_keys),
            country_count=len(countries),
            source_hunt_count=len(source_hunt_ids),
        ),
        groups=groups,
    )


def mark_hunt_imported(hunts: dict[str, dict[str, Any]], hunt_id: str, now_fn: Callable[[], str]) -> ImportHuntLeadsResponse:
    hunt = hunts.get(hunt_id)
    if hunt is None:
        raise KeyError(hunt_id)
    result = hunt.get("result") or {}
    leads = dedupe_leads(result.get("leads", []) or [])
    if not leads:
        raise CustomerPoolImportError("This task has no customer leads to import")

    imported_at = str(hunt.get("customer_pool_imported_at") or now_fn())
    hunt["customer_pool_imported_at"] = imported_at
    return ImportHuntLeadsResponse(hunt_id=hunt_id, status="imported", imported_at=imported_at, lead_count=len(leads))
