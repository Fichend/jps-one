"""Company-name second-pass enrichment for public social profiles."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from config.settings import Settings
from enrichment.models import EnrichmentResult, EnrichmentTask
from mcp_tools.search_adapters import ApifySocialSearchAdapter

logger = logging.getLogger(__name__)


class SocialEnricher:
    """Search public Instagram/Facebook profiles for a known candidate entity."""

    def __init__(self, settings: Settings, budget: dict[str, Any] | None = None) -> None:
        self.settings = settings
        self.budget = budget or {}
        self._adapter = ApifySocialSearchAdapter(settings, budget=self.budget)

    async def run(self, task: EnrichmentTask) -> EnrichmentResult:
        if not self.settings.apify_token:
            return EnrichmentResult(task.candidate_id, task.task_type, task.query_or_url, "apify_social", "skipped", "未配置 Apify Token，跳过社媒补全。")
        try:
            if task.task_type == "search_instagram_by_company":
                rows = await self._adapter.instagram_search(task.query_or_url, num=5)
                source = "apify_instagram"
            elif task.task_type == "search_facebook_by_company":
                rows = await self._adapter.facebook_search(task.query_or_url, num=5)
                source = "apify_facebook"
            else:
                return EnrichmentResult(task.candidate_id, task.task_type, task.query_or_url, "apify_social", "skipped", "非社媒补全任务。")
        except Exception as exc:
            logger.warning("[SocialEnricher] social task failed candidate=%s task=%s: %s", task.candidate_id, task.task_type, exc)
            return EnrichmentResult(task.candidate_id, task.task_type, task.query_or_url, "apify_social", "failed", str(exc))

        rows = [_attach_social_identity(row, task) for row in rows if _entity_match(row, task)]
        status = "enriched" if rows else "partial"
        message = f"找到 {len(rows)} 条疑似公开社媒主页。" if rows else "没有找到可归并到该客户的社媒主页。"
        return EnrichmentResult(task.candidate_id, task.task_type, task.query_or_url, source, status, message, rows)


def _attach_social_identity(row: dict[str, Any], task: EnrichmentTask) -> dict[str, Any]:
    item = dict(row)
    item.setdefault("candidate_id", task.candidate_id)
    item.setdefault("company_name", task.company_name)
    item.setdefault("country", task.country)
    evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
    if task.website and not evidence.get("externalUrl") and _same_domain_hint(item, task.website):
        evidence["externalUrl"] = task.website
    if evidence:
        item["evidence"] = evidence
    return item


def _entity_match(row: dict[str, Any], task: EnrichmentTask) -> bool:
    company = _tokens(task.company_name)
    if not company:
        return True
    text = " ".join(str(value or "") for value in (row.get("title"), row.get("snippet"), row.get("link"))).lower()
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    text += " " + " ".join(str(evidence.get(key) or "") for key in ("username", "fullName", "biography", "externalUrl", "website")).lower()
    matched = sum(1 for token in company if token in text)
    return matched >= min(2, len(company)) or _same_domain_hint(row, task.website)


def _same_domain_hint(row: dict[str, Any], website: str) -> bool:
    if not website:
        return False
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    candidates = [evidence.get("externalUrl"), evidence.get("website"), row.get("website")]
    target = _domain(website)
    return bool(target and any(_domain(str(value or "")) == target for value in candidates))


def _domain(url: str) -> str:
    if not url:
        return ""
    host = urlparse(url if "://" in url else f"https://{url}").netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _tokens(value: str) -> list[str]:
    stopwords = {"co", "company", "ltd", "limited", "inc", "llc", "the", "and", "dental", "equipment"}
    return [token for token in value.lower().replace("&", " ").split() if len(token) >= 3 and token not in stopwords][:5]
