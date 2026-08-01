"""Website discovery and contact extraction for candidate entities."""

from __future__ import annotations

import logging
import asyncio
from typing import Any
from urllib.parse import urlparse

from config.settings import Settings
from enrichment.models import EnrichmentResult, EnrichmentTask
from mcp_tools.search_adapters import TavilyMCPSearchAdapter
from tools.contact_extractor import discover_contact_pages, extract_phone_numbers, extract_social_media, sanitize_phone_list
from tools.email_finder import extract_emails_from_text
from tools.jina_reader import JinaReaderTool
from tools.web_search import WebSearchTool

logger = logging.getLogger(__name__)


class WebsiteEnricher:
    """Read official websites deeply enough to collect contact and social evidence."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._reader = JinaReaderTool(settings)

    async def close(self) -> None:
        await self._reader.close()

    async def run(self, task: EnrichmentTask) -> EnrichmentResult:
        if task.task_type == "find_website":
            return await self.find_website(task)
        if task.task_type == "extract_website":
            return await self.extract_website(task)
        if task.task_type == "crawl_website":
            return await self.crawl_website(task)
        return EnrichmentResult(
            candidate_id=task.candidate_id,
            task_type=task.task_type,
            query_or_url=task.query_or_url,
            source="website_enricher",
            status="skipped",
            message="非官网补全任务。",
        )

    async def find_website(self, task: EnrichmentTask) -> EnrichmentResult:
        if not self.settings.tavily_api_key:
            return EnrichmentResult(
                task.candidate_id,
                task.task_type,
                task.query_or_url,
                "web_search",
                "skipped",
                "未配置 Tavily，跳过官网发现。",
            )
        try:
            search_tool = WebSearchTool(self.settings, allow_mcp=True)
            rows = await search_tool.search(task.query_or_url, num=5)
            await search_tool.close()
        except Exception as exc:
            logger.warning("[WebsiteEnricher] find website failed candidate=%s: %s", task.candidate_id, exc)
            return EnrichmentResult(task.candidate_id, task.task_type, task.query_or_url, "web_search", "failed", str(exc))
        official_rows = [_attach_candidate_identity(row, task) for row in rows if _looks_like_official(row)]
        status = "enriched" if official_rows else "partial"
        message = f"发现 {len(official_rows)} 个疑似官网结果。" if official_rows else "没有发现可信官网，保留候选继续排序。"
        return EnrichmentResult(task.candidate_id, task.task_type, task.query_or_url, "web_search", status, message, official_rows)

    async def extract_website(self, task: EnrichmentTask) -> EnrichmentResult:
        pages = [task.query_or_url]
        items: list[dict[str, Any]] = []
        messages: list[str] = []
        first_text = ""
        try:
            rows = await _tavily_extract_rows(self.settings, [task.query_or_url]) if self.settings.tavily_api_key else []
            for row in rows:
                text = _row_text(row)
                first_text = first_text or text
                items.append(_contact_row_from_text(task, row.get("link") or task.query_or_url, text, "tavily_extract", row))
        except Exception as exc:
            messages.append(f"Tavily extract 失败：{exc}")
            logger.info("[WebsiteEnricher] Tavily extract failed url=%s: %s", task.query_or_url, exc)

        if not first_text:
            try:
                first_text = await self._reader.read(task.query_or_url)
                items.append(_contact_row_from_text(task, task.query_or_url, first_text, "jina_reader", {}))
            except Exception as exc:
                messages.append(f"Jina reader 失败：{exc}")

        contact_pages = discover_contact_pages(first_text, task.query_or_url)[: max(0, int(getattr(self.settings, "candidate_enrichment_pages_per_site", 5) or 5) - 1)]
        for url in contact_pages:
            try:
                text = await self._reader.read(url)
                items.append(_contact_row_from_text(task, url, text, "jina_contact_page", {}))
            except Exception as exc:
                messages.append(f"联系页读取失败 {url}: {exc}")

        items = [item for item in items if _has_contact_signal(item)]
        status = "enriched" if items else ("failed" if messages else "partial")
        message = f"官网抽取生成 {len(items)} 条联系人/社媒证据。" if items else "; ".join(messages[:2]) or "官网没有抽取到联系人证据。"
        return EnrichmentResult(task.candidate_id, task.task_type, task.query_or_url, "website_enricher", status, message, items)

    async def crawl_website(self, task: EnrichmentTask) -> EnrichmentResult:
        if not self.settings.tavily_api_key:
            return EnrichmentResult(task.candidate_id, task.task_type, task.query_or_url, "tavily_crawl", "skipped", "未配置 Tavily，跳过站内 crawl。")
        try:
            max_pages = int(getattr(self.settings, "candidate_enrichment_pages_per_site", 5) or 5)
            rows = await _tavily_crawl_rows(self.settings, task.query_or_url, max_depth=1, max_pages=max_pages)
        except Exception as exc:
            logger.info("[WebsiteEnricher] Tavily crawl failed url=%s: %s", task.query_or_url, exc)
            return EnrichmentResult(task.candidate_id, task.task_type, task.query_or_url, "tavily_crawl", "failed", str(exc))
        items = [
            _contact_row_from_text(task, row.get("link") or task.query_or_url, _row_text(row), "tavily_crawl", row)
            for row in rows
        ]
        items = [item for item in items if _has_contact_signal(item)]
        status = "enriched" if items else "partial"
        message = f"站内 crawl 抽取 {len(items)} 条联系人/社媒证据。" if items else "站内 crawl 未发现新的联系人证据。"
        return EnrichmentResult(task.candidate_id, task.task_type, task.query_or_url, "tavily_crawl", status, message, items)


def _attach_candidate_identity(row: dict[str, Any], task: EnrichmentTask) -> dict[str, Any]:
    item = dict(row)
    item.setdefault("candidate_id", task.candidate_id)
    item.setdefault("company_name", task.company_name)
    item.setdefault("title", task.company_name or row.get("title", ""))
    item.setdefault("country", task.country)
    item.setdefault("source", row.get("source") or "web_search")
    return item


async def _tavily_extract_rows(settings: Settings, urls: list[str]) -> list[dict[str, Any]]:
    try:
        from tavily import TavilyClient

        def _sync_extract() -> dict[str, Any]:
            return TavilyClient(settings.tavily_api_key).extract(urls=urls, format="markdown", timeout=30)

        payload = await asyncio.to_thread(_sync_extract)
        return _normalize_tavily_page_payload(payload, "tavily_extract")
    except Exception as exc:
        logger.info("[WebsiteEnricher] direct Tavily extract failed, falling back to MCP: %s", exc)
        return await TavilyMCPSearchAdapter(settings).extract(urls)


async def _tavily_crawl_rows(settings: Settings, url: str, *, max_depth: int, max_pages: int) -> list[dict[str, Any]]:
    try:
        from tavily import TavilyClient

        def _sync_crawl() -> dict[str, Any]:
            return TavilyClient(settings.tavily_api_key).crawl(
                url=url,
                max_depth=max_depth,
                limit=max_pages,
                format="markdown",
                timeout=min(60, int(getattr(settings, "candidate_enrichment_timeout_seconds", 90) or 90)),
            )

        payload = await asyncio.to_thread(_sync_crawl)
        return _normalize_tavily_page_payload(payload, "tavily_crawl")
    except Exception as exc:
        logger.info("[WebsiteEnricher] direct Tavily crawl failed, falling back to MCP: %s", exc)
        return await TavilyMCPSearchAdapter(settings).crawl(url, max_depth=max_depth, max_pages=max_pages)


def _normalize_tavily_page_payload(payload: dict[str, Any], source: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    raw_items = payload.get("results") or payload.get("items") or payload.get("data") or []
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    for index, item in enumerate(raw_items if isinstance(raw_items, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        page_url = item.get("url") or item.get("source_url") or item.get("link") or ""
        text = item.get("raw_content") or item.get("content") or item.get("text") or item.get("markdown") or ""
        rows.append(
            {
                "title": item.get("title") or page_url,
                "link": page_url,
                "snippet": str(text or "")[:1200],
                "position": index,
                "source": source,
                "evidence": {"source_tool": source, "raw": item},
            }
        )
    return rows


def _looks_like_official(row: dict[str, Any]) -> bool:
    link = str(row.get("link") or row.get("website") or "").strip()
    if not link:
        return False
    host = urlparse(link if "://" in link else f"https://{link}").netloc.lower()
    return not any(blocked in host for blocked in ("facebook.com", "instagram.com", "linkedin.com", "youtube.com", "google.", "yelp.", "tripadvisor."))


def _row_text(row: dict[str, Any]) -> str:
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    raw = evidence.get("raw") if isinstance(evidence.get("raw"), dict) else {}
    return "\n".join(str(value or "") for value in (row.get("title"), row.get("snippet"), raw.get("raw_content"), raw.get("content"), raw.get("text")))


def _contact_row_from_text(task: EnrichmentTask, url: str, text: str, source: str, raw: dict[str, Any]) -> dict[str, Any]:
    emails = extract_emails_from_text(text or "")[:10]
    phones = sanitize_phone_list(extract_phone_numbers(text or ""))[:10]
    social = extract_social_media(text or "")
    evidence = {
        "source_tool": source,
        "website": task.website or task.query_or_url,
        "email": emails[0] if emails else "",
        "phone": phones[0] if phones else "",
        "raw": raw,
    }
    return {
        "candidate_id": task.candidate_id,
        "title": task.company_name,
        "company_name": task.company_name,
        "link": url,
        "website": task.website or task.query_or_url,
        "country": task.country,
        "snippet": (text or "")[:500],
        "source": source,
        "emails": emails,
        "phone_numbers": phones,
        "social_media": social,
        "instagram_url": social.get("instagram", ""),
        "facebook_url": social.get("facebook", ""),
        "linkedin_url": social.get("linkedin", ""),
        "evidence": evidence,
    }


def _has_contact_signal(row: dict[str, Any]) -> bool:
    return bool(row.get("emails") or row.get("phone_numbers") or row.get("instagram_url") or row.get("facebook_url") or row.get("linkedin_url"))
