"""WebSearchTool — unified web search with MCP, Tavily, and no-key fallback.

Google Search and Google Maps are configured separately through `SERPER_API_KEY`.
When `TAVILY_API_KEY` is configured, this tool uses Tavily with multi-key
round-robin. Without Tavily, it falls back to DuckDuckGo's HTML endpoint.

Multi-key support:
    TAVILY_API_KEY=key1,key2

Keys are rotated in round-robin per-process using a thread-safe atomic counter,
so concurrent searches spread load evenly across all configured keys.
"""

from __future__ import annotations

import itertools
import logging
import threading
from urllib.parse import parse_qs, unquote, urlparse

from config.settings import Settings, get_settings

logger = logging.getLogger(__name__)


# ── Key pool helpers ──────────────────────────────────────────────────────────

def _parse_keys(raw: str) -> list[str]:
    """Split a comma-separated key string into a list of non-empty keys."""
    return [k.strip() for k in raw.split(",") if k.strip()]


class _RoundRobinPool:
    """Thread-safe round-robin key pool."""

    def __init__(self, keys: list[str]) -> None:
        self._keys = keys
        self._cycle = itertools.cycle(keys)
        self._lock = threading.Lock()

    def next_key(self) -> str:
        with self._lock:
            return next(self._cycle)

    def __len__(self) -> int:
        return len(self._keys)

    def __bool__(self) -> bool:
        return bool(self._keys)


# ── Per-backend search implementations ───────────────────────────────────────

def _is_invalid_country_error(exc: Exception) -> bool:
    """Return True when the Tavily error is specifically about an unsupported country code."""
    return "invalid country" in str(exc).lower()


def _parse_tavily_response(response: dict) -> list[dict]:
    results = []
    for i, item in enumerate(response.get("results", []), start=1):
        content = item.get("content", "")
        snippet = content[:400] + "..." if len(content) > 400 else content
        results.append({
            "title": item.get("title", ""),
            "link": item.get("url", ""),
            "snippet": snippet,
            "position": i,
        })
    return results


async def _tavily_search(
    api_key: str,
    query: str,
    num: int,
    gl: str,
) -> list[dict]:
    import asyncio

    try:
        from tavily import TavilyClient
    except ImportError:
        raise ImportError("tavily-python is required. Install: pip install tavily-python")

    client = TavilyClient(api_key)
    max_results = min(num, 20)

    def _sync_with_country():
        return client.search(
            query=query,
            search_depth="basic",
            max_results=max_results,
            country=gl,
        )

    def _sync_no_country():
        return client.search(
            query=query,
            search_depth="basic",
            max_results=max_results,
        )

    use_country = bool(gl and len(gl) == 2)

    if use_country:
        try:
            response = await asyncio.to_thread(_sync_with_country)
            return _parse_tavily_response(response)
        except Exception as e:
            if _is_invalid_country_error(e):
                # Tavily doesn't support this country code — retry without it
                logger.warning(
                    "[WebSearch] Tavily: unsupported country=%r, retrying without country param", gl
                )
                response = await asyncio.to_thread(_sync_no_country)
                return _parse_tavily_response(response)
            raise
    else:
        response = await asyncio.to_thread(_sync_no_country)
        return _parse_tavily_response(response)


def _clean_duckduckgo_url(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if "uddg" in query and query["uddg"]:
        return unquote(query["uddg"][0])
    return url


def _parse_duckduckgo_html(content: str) -> list[dict]:
    from lxml import html

    tree = html.fromstring(content)
    results: list[dict] = []

    for item in tree.xpath('//*[contains(concat(" ", normalize-space(@class), " "), " result ")]'):
        title_nodes = item.xpath('.//*[contains(concat(" ", normalize-space(@class), " "), " result__a ")]')
        if not title_nodes:
            continue
        title_node = title_nodes[0]
        link = _clean_duckduckgo_url(title_node.get("href") or "")
        if not link:
            continue

        snippet_nodes = item.xpath('.//*[contains(concat(" ", normalize-space(@class), " "), " result__snippet ")]')
        snippet = snippet_nodes[0].text_content().strip() if snippet_nodes else ""
        results.append(
            {
                "title": title_node.text_content().strip(),
                "link": link,
                "snippet": snippet,
                "position": len(results) + 1,
            }
        )

    if results:
        return results

    for title_node in tree.xpath('//a[contains(@href, "uddg=")]'):
        link = _clean_duckduckgo_url(title_node.get("href") or "")
        title = title_node.text_content().strip()
        if not link or not title:
            continue
        results.append(
            {
                "title": title,
                "link": link,
                "snippet": "",
                "position": len(results) + 1,
            }
        )

    return results


async def _duckduckgo_search(
    query: str,
    num: int,
    gl: str,
    hl: str,
) -> list[dict]:
    import httpx

    params = {"q": query}
    if hl:
        params["kl"] = hl
    elif gl:
        params["kl"] = f"{gl.lower()}-en"

    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
        for endpoint in (
            "https://lite.duckduckgo.com/lite/",
            "https://html.duckduckgo.com/html/",
        ):
            try:
                response = await client.get(
                    endpoint,
                    params=params,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "text/html,application/xhtml+xml",
                    },
                )
                response.raise_for_status()
                results = _parse_duckduckgo_html(response.text)[: max(0, min(num, 20))]
                if results:
                    return results
            except Exception as exc:
                last_error = exc
                logger.warning("[WebSearch] DuckDuckGo fallback endpoint failed: %s", endpoint)

    if last_error is not None:
        raise RuntimeError(
            "DuckDuckGo fallback search failed. Configure TAVILY_API_KEY or another supported search key for reliable web search."
        ) from last_error
    return []


class WebSearchTool:
    """Unified web search tool.

    Usage:
        tool = WebSearchTool()
        results = await tool.search("solar panel distributor Germany", gl="de", hl="de")
        await tool.close()
    """

    def __init__(self, settings: Settings | None = None, *, allow_mcp: bool = True) -> None:
        self._settings = settings or get_settings()
        self._mcp_tool = None

        # Build key pools
        self._tavily_pool = _RoundRobinPool(_parse_keys(self._settings.tavily_api_key))

        if allow_mcp and self._settings.mcp_search_enabled:
            try:
                from mcp_tools.search_adapters import MCPMultiSourceSearchTool

                self._mcp_tool = MCPMultiSourceSearchTool(self._settings)
                if not self._mcp_tool.configured:
                    self._mcp_tool = None
                    raise RuntimeError("Tavily/Apify MCP credentials are not configured")
                self._backend = self._mcp_tool.backend
                logger.info("[WebSearch] Backend: %s", self._backend)
            except Exception as exc:
                self._mcp_tool = None
                logger.warning("[WebSearch] MCP backend unavailable, falling back: %s", exc)

        if self._mcp_tool is not None:
            return
        if self._tavily_pool:
            self._backend = "tavily"
            logger.info("[WebSearch] Backend: Tavily (%d key(s))", len(self._tavily_pool))
        else:
            self._backend = "duckduckgo"
            logger.warning("[WebSearch] No TAVILY_API_KEY configured; using DuckDuckGo HTML fallback")

    @property
    def backend(self) -> str:
        """Active backend name."""
        return self._backend

    async def search(
        self,
        query: str,
        *,
        num: int = 10,
        gl: str = "",
        hl: str = "",
    ) -> list[dict]:
        """Execute a general web search.

        Automatically picks the next key from the round-robin pool.

        Args:
            query: Search query string.
            num: Number of results (max 20).
            gl: Country code (e.g. "de", "us").
            hl: Language code (e.g. "de", "en").

        Returns:
            List of dicts with keys: title, link, snippet, position.
        """
        if self._mcp_tool is not None:
            results = await self._mcp_tool.search(query, num=num, gl=gl, hl=hl)
            if results:
                return results
            logger.warning("[WebSearch] MCP search returned no rows; using legacy fallback")
        if self._backend == "tavily" or self._tavily_pool:
            key = self._tavily_pool.next_key()
            return await _tavily_search(key, query, num, gl)
        return await _duckduckgo_search(query, num, gl, hl)

    async def close(self) -> None:
        if self._mcp_tool is not None:
            await self._mcp_tool.close()
        return None
