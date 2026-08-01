"""Plan bounded enrichment tasks from candidate gaps."""

from __future__ import annotations

from typing import Any

from candidate_pool.ranking import enabled_required_fields, has_field
from enrichment.models import EnrichmentTask


CONTACT_FIELDS = {"email", "phone", "instagram", "facebook", "website", "address"}
DEFAULT_ENRICHMENT_FIELDS = ["website", "email", "phone", "instagram", "facebook", "address"]


def plan_enrichment_tasks(
    candidates: list[dict[str, Any]],
    *,
    hard_filters: dict[str, Any] | None = None,
    max_candidates: int = 0,
    max_tasks: int = 80,
) -> tuple[list[EnrichmentTask], list[dict[str, Any]]]:
    """Return enrichment tasks plus skipped trace records.

    The planner never changes the user's requested candidate count or budget. It
    only caps operational load, then records any skipped work for transparency.
    """
    required = enabled_required_fields(hard_filters or {})
    task_cap = max(0, int(max_tasks or 0))
    candidate_limit = max(0, int(max_candidates or 0)) or len(candidates)
    tasks: list[EnrichmentTask] = []
    skipped: list[dict[str, Any]] = []

    for candidate in candidates[:candidate_limit]:
        if not isinstance(candidate, dict):
            continue
        candidate_id = str(candidate.get("candidate_id") or "").strip()
        company_name = str(candidate.get("company_name") or candidate.get("title") or "").strip()
        country = str(candidate.get("country") or "").strip()
        website = str(candidate.get("website") or "").strip()
        if not candidate_id or not company_name:
            continue

        missing = _missing_fields(candidate, required)
        candidate_tasks = _tasks_for_candidate(candidate_id, company_name, country, website, missing)
        for task in candidate_tasks:
            if task_cap and len(tasks) >= task_cap:
                skipped.append(
                    {
                        "candidate_id": candidate_id,
                        "task_type": task.task_type,
                        "status": "budget_limited",
                        "query_or_url": task.query_or_url,
                        "message": "补全任务达到系统负载上限，候选仍保留排序。",
                    }
                )
                continue
            tasks.append(task)

    for candidate in candidates[candidate_limit:]:
        if not isinstance(candidate, dict):
            continue
        skipped.append(
            {
                "candidate_id": str(candidate.get("candidate_id") or ""),
                "task_type": "candidate_limit",
                "status": "skipped",
                "query_or_url": "",
                "message": "超出用户填写的候选池数量，本轮不做二次补全。",
            }
        )

    return tasks, skipped


def _missing_fields(candidate: dict[str, Any], required: list[str]) -> list[str]:
    hinted: list[str] = []
    if isinstance(candidate.get("missing_fields"), list):
        hinted = [str(item).replace("require_", "").strip() for item in candidate.get("missing_fields", [])]

    fields: list[str] = []
    for field in [*required, *hinted, *DEFAULT_ENRICHMENT_FIELDS]:
        if field in CONTACT_FIELDS and field not in fields:
            fields.append(field)
    return [field for field in fields if not has_field(candidate, field)]


def _tasks_for_candidate(
    candidate_id: str,
    company_name: str,
    country: str,
    website: str,
    missing: list[str],
) -> list[EnrichmentTask]:
    if not missing:
        return []
    tasks: list[EnrichmentTask] = []
    query_base = " ".join(part for part in (company_name, country) if part).strip()

    if "website" in missing and query_base:
        tasks.append(
            EnrichmentTask(
                candidate_id=candidate_id,
                task_type="find_website",
                query_or_url=f"{query_base} official website contact",
                missing_fields=missing,
                company_name=company_name,
                country=country,
            )
        )

    if website and ({"email", "phone", "instagram", "facebook", "address"} & set(missing)):
        tasks.append(
            EnrichmentTask(
                candidate_id=candidate_id,
                task_type="extract_website",
                query_or_url=website,
                missing_fields=missing,
                company_name=company_name,
                country=country,
                website=website,
            )
        )
        tasks.append(
            EnrichmentTask(
                candidate_id=candidate_id,
                task_type="crawl_website",
                query_or_url=website,
                missing_fields=missing,
                company_name=company_name,
                country=country,
                website=website,
            )
        )

    if "instagram" in missing and query_base:
        tasks.append(
            EnrichmentTask(
                candidate_id=candidate_id,
                task_type="search_instagram_by_company",
                query_or_url=query_base,
                missing_fields=missing,
                company_name=company_name,
                country=country,
                website=website,
            )
        )
    if "facebook" in missing and query_base:
        tasks.append(
            EnrichmentTask(
                candidate_id=candidate_id,
                task_type="search_facebook_by_company",
                query_or_url=query_base,
                missing_fields=missing,
                company_name=company_name,
                country=country,
                website=website,
            )
        )
    return tasks
