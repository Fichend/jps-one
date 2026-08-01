"""Focused Tavily helpers for one-candidate deep enrichment."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlparse

from config.settings import Settings
from mcp_tools.search_adapters import TavilyMCPSearchAdapter
from tools.web_search import WebSearchTool

logger = logging.getLogger(__name__)


async def tavily_search(settings: Settings, query: str, *, num: int = 8) -> list[dict[str, Any]]:
    try:
        return await TavilyMCPSearchAdapter(settings).search(query, num=num)
    except Exception as exc:
        logger.info("[DeepEnrich] Tavily MCP search failed, falling back to SDK: %s", exc)
        tool = WebSearchTool(settings, allow_mcp=False)
        try:
            return await tool.search(query, num=num)
        finally:
            await tool.close()


async def tavily_extract(settings: Settings, urls: list[str]) -> list[dict[str, Any]]:
    clean_urls = [url for url in _dedupe(urls) if url]
    if not clean_urls:
        return []
    try:
        from tavily import TavilyClient

        def _sync() -> dict[str, Any]:
            return TavilyClient(settings.tavily_api_key).extract(urls=clean_urls, format="markdown", timeout=60)

        payload = await asyncio.to_thread(_sync)
        return _normalize_page_payload(payload, "tavily_extract")
    except Exception as exc:
        logger.info("[DeepEnrich] direct Tavily extract failed, falling back to MCP: %s", exc)
        try:
            return await TavilyMCPSearchAdapter(settings).extract(clean_urls)
        except Exception as mcp_exc:
            logger.info("[DeepEnrich] MCP extract failed: %s", mcp_exc)
            return []


async def tavily_crawl(settings: Settings, url: str, *, max_depth: int = 2, max_pages: int = 30) -> list[dict[str, Any]]:
    clean_url = str(url or "").strip()
    if not clean_url:
        return []
    try:
        from tavily import TavilyClient

        def _sync() -> dict[str, Any]:
            return TavilyClient(settings.tavily_api_key).crawl(
                url=clean_url,
                max_depth=max(1, min(int(max_depth), 3)),
                limit=max(1, min(int(max_pages), 60)),
                format="markdown",
                timeout=120,
            )

        payload = await asyncio.to_thread(_sync)
        return _normalize_page_payload(payload, "tavily_crawl")
    except Exception as exc:
        logger.info("[DeepEnrich] direct Tavily crawl failed, falling back to MCP: %s", exc)
        try:
            return await TavilyMCPSearchAdapter(settings).crawl(clean_url, max_depth=max_depth, max_pages=max_pages)
        except Exception as mcp_exc:
            logger.info("[DeepEnrich] MCP crawl failed: %s", mcp_exc)
            return []


async def tavily_map(settings: Settings, url: str, *, max_pages: int = 50) -> list[str]:
    clean_url = str(url or "").strip()
    if not clean_url:
        return []
    try:
        from tavily import TavilyClient

        def _sync() -> Any:
            client = TavilyClient(settings.tavily_api_key)
            map_fn = getattr(client, "map")
            return map_fn(url=clean_url, max_pages=max(1, min(int(max_pages), 100)))

        payload = await asyncio.to_thread(_sync)
        return _normalize_url_payload(payload)
    except Exception as exc:
        logger.info("[DeepEnrich] direct Tavily map failed, falling back to MCP: %s", exc)
        try:
            rows = await TavilyMCPSearchAdapter(settings).map(clean_url, max_pages=max_pages)
            return _dedupe([str(row.get("link") or "") for row in rows])
        except Exception as mcp_exc:
            logger.info("[DeepEnrich] MCP map failed: %s", mcp_exc)
            return []


async def tavily_research(settings: Settings, query: str, *, model: str = "mini") -> list[dict[str, Any]]:
    clean_query = str(query or "").strip()
    if not clean_query:
        return []
    try:
        from tavily import TavilyClient

        def _sync() -> dict[str, Any]:
            return TavilyClient(settings.tavily_api_key).research(input=clean_query, model=model, timeout=120)

        payload = await asyncio.to_thread(_sync)
        return _normalize_research_payload(payload, clean_query)
    except Exception as exc:
        logger.info("[DeepEnrich] Tavily research failed: %s", exc)
        return []


def _normalize_page_payload(payload: Any, source: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    raw_items = payload.get("results") or payload.get("items") or payload.get("data") or []
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(raw_items if isinstance(raw_items, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        page_url = str(item.get("url") or item.get("source_url") or item.get("link") or "").strip()
        text = item.get("raw_content") or item.get("content") or item.get("text") or item.get("markdown") or ""
        rows.append({
            "title": item.get("title") or page_url,
            "link": page_url,
            "snippet": str(text or "")[:4000],
            "position": index,
            "source": source,
            "evidence": {"source_tool": source, "raw": item},
        })
    return rows


def _normalize_url_payload(payload: Any) -> list[str]:
    if isinstance(payload, list):
        return _dedupe([str(item.get("url") if isinstance(item, dict) else item or "").strip() for item in payload])
    if not isinstance(payload, dict):
        return []
    raw_items = payload.get("urls") or payload.get("results") or payload.get("items") or payload.get("data") or []
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    urls = []
    for item in raw_items if isinstance(raw_items, list) else []:
        urls.append(str(item.get("url") if isinstance(item, dict) else item or "").strip())
    return _dedupe(urls)


def _normalize_research_payload(payload: Any, query: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows: list[dict[str, Any]] = []
    answer = str(payload.get("answer") or payload.get("final_answer") or payload.get("output") or "").strip()
    if answer:
        rows.append({
            "title": "Tavily Research Summary",
            "link": "",
            "snippet": answer[:4000],
            "position": 1,
            "source": "tavily_research",
            "evidence": {"source_tool": "tavily_research", "query": query, "raw": payload},
        })
    raw_results = payload.get("results") or payload.get("sources") or payload.get("citations") or []
    if isinstance(raw_results, dict):
        raw_results = [raw_results]
    for index, item in enumerate(raw_results if isinstance(raw_results, list) else [], start=2):
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or item.get("link") or item.get("source_url") or "").strip()
        rows.append({
            "title": item.get("title") or url or "Tavily Research Source",
            "link": url,
            "snippet": str(item.get("content") or item.get("snippet") or item.get("text") or "")[:4000],
            "position": index,
            "source": "tavily_research",
            "evidence": {"source_tool": "tavily_research", "query": query, "raw": item},
        })
    return rows


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if not clean:
            continue
        key = _url_key(clean)
        if key in seen:
            continue
        seen.add(key)
        result.append(clean)
    return result


def _url_key(url: str) -> str:
    raw = url.strip()
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    parsed = urlparse(raw)
    return (parsed.netloc.lower().removeprefix("www."), parsed.path.rstrip("/").lower()).__repr__()
