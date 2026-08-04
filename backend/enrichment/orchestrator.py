"""Bounded orchestration for candidate website and social enrichment."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any

from candidate_pool import build_candidate_pool
from config.settings import Settings
from enrichment.models import EnrichmentResult, EnrichmentTask
from enrichment.planner import plan_enrichment_tasks
from enrichment.social_enricher import SocialEnricher
from enrichment.website_enricher import WebsiteEnricher

logger = logging.getLogger(__name__)


async def enrich_candidate_pool(
    candidates: list[dict[str, Any]],
    *,
    settings: Settings,
    budget: dict[str, Any] | None = None,
    hunt_id: str = "",
    target_final_leads: int = 10,
    hard_filters: dict[str, Any] | None = None,
    exclusions: list[str] | None = None,
    customer_types: list[str] | None = None,
    product_keywords: list[str] | None = None,
    target_regions: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Enrich candidate entities, then rebuild the ranked pool.

    Search produces broad recall. This stage works entity-by-entity: it crawls a
    known website for contacts and searches Instagram/Facebook by company name,
    then merges the new evidence into the same candidate before ranking.
    """
    if not candidates or not getattr(settings, "candidate_enrichment_enabled", True):
        return candidates

    budget = budget or {}
    max_candidates = _as_int(budget.get("max_candidates"), len(candidates))
    configured_max_tasks = _as_int(getattr(settings, "candidate_enrichment_max_tasks", 80), 80)
    # A candidate can need up to five bounded tasks: find website, extract,
    # crawl, Instagram, and Facebook. Scale the cap with the user's candidate
    # pool so large pools are still fully considered, while preserving the
    # existing setting as the lower bound for small hunts.
    max_tasks = max(configured_max_tasks, max_candidates * 5)
    tasks, skipped = plan_enrichment_tasks(
        candidates,
        hard_filters=hard_filters or {},
        max_candidates=max_candidates,
        max_tasks=max_tasks,
    )
    if not tasks and not skipped:
        return _annotate_noop(candidates)

    logger.info("[Enrichment] planned tasks=%d skipped=%d candidates=%d", len(tasks), len(skipped), len(candidates))
    website = WebsiteEnricher(settings)
    social = SocialEnricher(settings, budget=budget)
    semaphore = asyncio.Semaphore(max(1, _as_int(getattr(settings, "candidate_enrichment_concurrency", 4), 4)))
    timeout = max(10, _as_int(getattr(settings, "candidate_enrichment_timeout_seconds", 90), 90))

    async def run_task(task: EnrichmentTask) -> EnrichmentResult:
        async with semaphore:
            try:
                coro = social.run(task) if task.task_type.startswith("search_") else website.run(task)
                return await asyncio.wait_for(coro, timeout=timeout)
            except asyncio.TimeoutError:
                return EnrichmentResult(task.candidate_id, task.task_type, task.query_or_url, task.source, "failed", f"补全超时 {timeout}s")
            except Exception as exc:
                logger.warning("[Enrichment] task failed candidate=%s task=%s: %s", task.candidate_id, task.task_type, exc)
                return EnrichmentResult(task.candidate_id, task.task_type, task.query_or_url, task.source, "failed", str(exc))

    try:
        results = await asyncio.gather(*(run_task(task) for task in tasks))
    finally:
        await website.close()

    enriched_rows: list[dict[str, Any]] = []
    trace_by_candidate: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        trace_by_candidate[result.candidate_id].append(result.trace_item())
        for row in result.items:
            if isinstance(row, dict):
                item = dict(row)
                item.setdefault("candidate_id", result.candidate_id)
                item.setdefault("enrichment_source", result.source)
                item.setdefault("enrichment_task_type", result.task_type)
                enriched_rows.append(item)
    for item in skipped:
        candidate_id = str(item.get("candidate_id") or "")
        if candidate_id:
            trace_by_candidate[candidate_id].append(item)

    merged = build_candidate_pool(
        [dict(candidate) for candidate in candidates] + enriched_rows,
        hunt_id=hunt_id,
        target_final_leads=target_final_leads,
        hard_filters=hard_filters or {},
        exclusions=exclusions or [],
        customer_types=customer_types or _list_from_budget(budget, "customer_types"),
        product_keywords=product_keywords or _list_from_budget(budget, "product_keywords"),
        target_regions=target_regions or _list_from_budget(budget, "target_regions"),
    )
    return _annotate_enrichment(merged, trace_by_candidate)


def _list_from_budget(budget: dict[str, Any], key: str) -> list[str]:
    raw = budget.get(key)
    return [str(item) for item in raw if str(item or "").strip()] if isinstance(raw, list) else []


def _annotate_noop(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    annotated = []
    for candidate in candidates:
        item = dict(candidate)
        item.setdefault("enrichment_status", "not_started")
        item.setdefault("enrichment_attempts", 0)
        item.setdefault("enrichment_trace", [])
        annotated.append(item)
    return annotated


def _annotate_enrichment(candidates: list[dict[str, Any]], trace_by_candidate: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id") or "")
        traces = trace_by_candidate.get(candidate_id, [])
        candidate["enrichment_trace"] = traces
        candidate["enrichment_attempts"] = len(traces)
        statuses = {str(item.get("status") or "") for item in traces}
        if not traces:
            candidate["enrichment_status"] = "not_started"
        elif "enriched" in statuses:
            candidate["enrichment_status"] = "enriched"
        elif statuses <= {"skipped", "budget_limited"}:
            candidate["enrichment_status"] = "budget_limited" if "budget_limited" in statuses else "skipped"
        elif "partial" in statuses:
            candidate["enrichment_status"] = "partial"
        else:
            candidate["enrichment_status"] = "failed"
    return candidates


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
