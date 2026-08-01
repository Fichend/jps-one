"""MCP-backed search adapters for JPS One lead discovery.

The adapters keep third-party MCP server details behind one normalized contract
so the hunt graph can consume Tavily/Apify results the same way it consumes the
existing Tavily SDK or DuckDuckGo fallback rows.
"""

from __future__ import annotations

import json
import logging
import time
import asyncio
import re
from typing import Any

import httpx

from config.settings import Settings
from mcp_tools.client import (
    MCPClientError,
    MCPServerConfig,
    MCPToolClient,
    extract_text_content,
    parse_jsonish,
    split_args,
)

logger = logging.getLogger(__name__)


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _json_dict(raw: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not raw:
        return default or {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return default or {}
    return value if isinstance(value, dict) else default or {}


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _trim(text: Any, limit: int = 400) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."


def _result(title: Any, link: Any, snippet: Any, position: int, source: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": str(title or "").strip(),
        "link": str(link or "").strip(),
        "snippet": _trim(snippet),
        "position": position,
        "source": source,
        "source_tool": evidence.get("source_tool", source),
        "evidence": evidence,
    }


def _iter_candidate_items(value: Any) -> list[dict[str, Any]]:
    """Find likely search result rows inside loosely structured MCP payloads."""
    candidates: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if any(k in node for k in ("url", "link", "href", "website", "externalUrl", "profileUrl", "username", "pageUrl")) and any(
                k in node for k in ("title", "name", "fullName", "pageName", "content", "snippet", "description", "text", "biography")
            ):
                candidates.append(node)
            for key in ("results", "organic", "items", "data", "datasetItems", "searchResults"):
                child = node.get(key)
                if isinstance(child, list):
                    for item in child:
                        walk(item)
            if not candidates:
                for child in node.values():
                    if isinstance(child, (dict, list)):
                        walk(child)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(value)
    return candidates


def _structured_payload(result: dict[str, Any]) -> Any:
    structured = result.get("structuredContent")
    if structured:
        return structured
    parsed = parse_jsonish(extract_text_content(result))
    return parsed if parsed is not None else result


def _extract_result_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if not isinstance(value, dict):
        return []
    for key in ("results", "items", "data", "pages", "extracts"):
        child = value.get(key)
        if isinstance(child, list):
            return [item for item in child if isinstance(item, dict)]
    return [value]


def _parse_tavily_text_results(text: str) -> list[dict[str, Any]]:
    """Parse Tavily MCP's human-readable stdio response into result rows.

    The current Tavily MCP server can return a single text block in the form
    ``Title: ... / URL: ... / Content: ...`` instead of structured JSON. Keep a
    deterministic parser here so MCP results remain first-class search rows.
    """
    clean = str(text or "").strip()
    if not clean:
        return []
    rows: list[dict[str, Any]] = []
    pattern = re.compile(
        r"(?:^|\n)Title:\s*(?P<title>.*?)\nURL:\s*(?P<url>\S+)\nContent:\s*(?P<content>.*?)(?=\n\nTitle:\s|\Z)",
        re.S,
    )
    for match in pattern.finditer(clean):
        rows.append(
            {
                "title": match.group("title").strip(),
                "url": match.group("url").strip(),
                "content": match.group("content").strip(),
            }
        )
    return rows


def _first_value(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, "", []):
            return value
    return ""


def _normalize_instagram_item(item: dict[str, Any], position: int, source: str, actor: str) -> dict[str, Any]:
    username = str(_first_value(item, ("username", "userName", "handle")) or "").strip().lstrip("@")
    url = str(_first_value(item, ("url", "profileUrl", "inputUrl")) or "").strip()
    if not url and username:
        url = f"https://www.instagram.com/{username}/"
    full_name = _first_value(item, ("fullName", "full_name", "name"))
    biography = _first_value(item, ("biography", "bio", "description"))
    external_url = _first_value(item, ("externalUrl", "external_url", "website"))
    title = full_name or (f"@{username}" if username else "Instagram profile")
    snippet_parts = [biography]
    if item.get("businessCategoryName") or item.get("businessCategory"):
        snippet_parts.append(f"Category: {item.get('businessCategoryName') or item.get('businessCategory')}")
    if item.get("followersCount") is not None:
        snippet_parts.append(f"Followers: {item.get('followersCount')}")
    if external_url:
        snippet_parts.append(f"External: {external_url}")
    return _result(
        title,
        url,
        " | ".join(str(part) for part in snippet_parts if part),
        position,
        source,
        {
            "source_tool": "call-actor",
            "actor": actor,
            "username": username,
            "fullName": full_name,
            "biography": biography,
            "followersCount": item.get("followersCount"),
            "businessCategory": item.get("businessCategoryName") or item.get("businessCategory"),
            "externalUrl": external_url,
            "raw": item,
        },
    )


def _normalize_facebook_item(item: dict[str, Any], position: int, source: str, actor: str) -> dict[str, Any]:
    url = str(_first_value(item, ("url", "pageUrl", "facebookUrl", "link")) or "").strip()
    title = _first_value(item, ("title", "pageName", "name", "profileName")) or "Facebook public page"
    snippet = _first_value(item, ("description", "about", "text", "intro"))
    website = _first_value(item, ("website", "externalUrl", "external_url"))
    if website:
        snippet = f"{snippet} | Website: {website}" if snippet else f"Website: {website}"
    return _result(
        title,
        url,
        snippet,
        position,
        source,
        {
            "source_tool": "call-actor",
            "actor": actor,
            "website": website,
            "phone": item.get("phone") or item.get("phoneNumber"),
            "category": item.get("category") or item.get("categories"),
            "raw": item,
        },
    )


class TavilyMCPSearchAdapter:
    provider = "tavily_mcp"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        env = {}
        if settings.tavily_api_key:
            env["TAVILY_API_KEY"] = settings.tavily_api_key
        if settings.tavily_mcp_default_parameters:
            env["DEFAULT_PARAMETERS"] = settings.tavily_mcp_default_parameters
        self.client = MCPToolClient(
            MCPServerConfig(
                name="tavily",
                transport=settings.tavily_mcp_transport,  # type: ignore[arg-type]
                command=settings.tavily_mcp_command,
                args=split_args(settings.tavily_mcp_args),
                url=settings.tavily_mcp_url,
                env=env,
                timeout_seconds=settings.tavily_mcp_timeout_seconds,
                stdio_message_format="json_lines",
            )
        )
        self.default_params = _json_dict(settings.tavily_mcp_default_parameters)

    async def search(self, query: str, *, num: int = 10, gl: str = "", hl: str = "") -> list[dict[str, Any]]:
        args = {**self.default_params, "query": query, "max_results": max(1, min(num, 20))}
        if gl and "country" not in args:
            args["country"] = gl
        normalized = await self._search_once(args, num=num)
        if not normalized and args.get("country"):
            retry_args = {key: value for key, value in args.items() if key != "country"}
            normalized = await self._search_once(retry_args, num=num)
        return normalized

    async def _search_once(self, args: dict[str, Any], *, num: int) -> list[dict[str, Any]]:
        try:
            result = await self.client.call_tool("tavily_search", args)
        except MCPClientError as exc:
            if args.get("country") and "country" in str(exc).lower():
                args = {key: value for key, value in args.items() if key != "country"}
                result = await self.client.call_tool("tavily_search", args)
            else:
                raise
        payload = _structured_payload(result)
        rows = _iter_candidate_items(payload)
        if not rows:
            rows = _parse_tavily_text_results(extract_text_content(result))
        normalized: list[dict[str, Any]] = []
        for i, item in enumerate(rows[:num], start=1):
            normalized.append(
                _result(
                    item.get("title") or item.get("name"),
                    item.get("url") or item.get("link") or item.get("href"),
                    item.get("content") or item.get("snippet") or item.get("description") or item.get("text"),
                    i,
                    self.provider,
                    {"source_tool": "tavily_search", "raw_score": item.get("score")},
                )
            )
        return [row for row in normalized if row["link"] or row["title"]]

    async def extract(self, urls: list[str], *, include_images: bool = False) -> list[dict[str, Any]]:
        clean_urls = [str(url or "").strip() for url in urls if str(url or "").strip()]
        if not clean_urls:
            return []
        args = {"urls": clean_urls, "include_images": include_images}
        result = await self.client.call_tool("tavily_extract", args)
        payload = _structured_payload(result)
        rows = _iter_candidate_items(payload)
        normalized: list[dict[str, Any]] = []
        for i, item in enumerate(rows or _extract_result_items(payload), start=1):
            url = item.get("url") or item.get("link") or item.get("href") or item.get("source_url")
            normalized.append(
                _result(
                    item.get("title") or item.get("name") or url,
                    url,
                    item.get("raw_content") or item.get("content") or item.get("text") or item.get("snippet") or item.get("description"),
                    i,
                    "tavily_extract",
                    {"source_tool": "tavily_extract", "raw": item},
                )
            )
        return [row for row in normalized if row["link"] or row["snippet"]]

    async def crawl(self, url: str, *, max_depth: int = 1, max_pages: int = 5) -> list[dict[str, Any]]:
        clean_url = str(url or "").strip()
        if not clean_url:
            return []
        args = {"url": clean_url, "max_depth": max(1, min(int(max_depth), 3)), "max_pages": max(1, min(int(max_pages), 20))}
        result = await self.client.call_tool("tavily_crawl", args)
        payload = _structured_payload(result)
        rows = _iter_candidate_items(payload)
        normalized: list[dict[str, Any]] = []
        for i, item in enumerate(rows or _extract_result_items(payload), start=1):
            page_url = item.get("url") or item.get("link") or item.get("href") or item.get("source_url")
            normalized.append(
                _result(
                    item.get("title") or item.get("name") or page_url,
                    page_url,
                    item.get("raw_content") or item.get("content") or item.get("text") or item.get("snippet") or item.get("description"),
                    i,
                    "tavily_crawl",
                    {"source_tool": "tavily_crawl", "root_url": clean_url, "raw": item},
                )
            )
        return [row for row in normalized if row["link"] or row["snippet"]]

    async def map(self, url: str, *, max_pages: int = 50) -> list[dict[str, Any]]:
        clean_url = str(url or "").strip()
        if not clean_url:
            return []
        args = {"url": clean_url, "max_pages": max(1, min(int(max_pages), 100))}
        result = await self.client.call_tool("tavily_map", args)
        payload = _structured_payload(result)
        rows = _iter_candidate_items(payload)
        if not rows:
            raw_urls = payload.get("urls") or payload.get("results") or payload.get("items") if isinstance(payload, dict) else []
            if isinstance(raw_urls, list):
                rows = [{"url": item} if isinstance(item, str) else item for item in raw_urls]
        normalized: list[dict[str, Any]] = []
        for i, item in enumerate(rows[: max(1, min(int(max_pages), 100))], start=1):
            if not isinstance(item, dict):
                continue
            page_url = item.get("url") or item.get("link") or item.get("href") or item.get("source_url")
            normalized.append(
                _result(
                    item.get("title") or item.get("name") or page_url,
                    page_url,
                    item.get("content") or item.get("snippet") or item.get("description") or "",
                    i,
                    "tavily_map",
                    {"source_tool": "tavily_map", "root_url": clean_url, "raw": item},
                )
            )
        return [row for row in normalized if row["link"]]


class ApifyMCPSearchAdapter:
    provider = "apify_mcp"

    def __init__(self, settings: Settings, budget: dict[str, Any] | None = None) -> None:
        env = {}
        if settings.apify_token:
            env["APIFY_TOKEN"] = settings.apify_token
        if settings.apify_mcp_tools:
            env["TOOLS"] = settings.apify_mcp_tools
            env["APIFY_MCP_TOOLS"] = settings.apify_mcp_tools
        self.settings = settings
        self.budget = budget or {}
        self.client = MCPToolClient(
            MCPServerConfig(
                name="apify",
                transport=settings.apify_mcp_transport,  # type: ignore[arg-type]
                command=settings.apify_mcp_command,
                args=split_args(settings.apify_mcp_args),
                url=settings.apify_mcp_url,
                env=env,
                timeout_seconds=settings.apify_mcp_timeout_seconds,
            )
        )

    async def search(self, query: str, *, num: int = 10, gl: str = "", hl: str = "") -> list[dict[str, Any]]:
        actor = self.settings.apify_default_actor or "apify/rag-web-browser"
        actor_input = {"query": query, "maxResults": max(1, min(num, 20))}
        if gl:
            actor_input["countryCode"] = gl.upper()
        if hl:
            actor_input["languageCode"] = hl

        result = await self.client.call_tool("call-actor", {"actor": actor, "input": actor_input})
        payload = _structured_payload(result)
        payload = await self._maybe_fetch_dataset_items(payload)
        rows = _iter_candidate_items(payload)
        normalized: list[dict[str, Any]] = []
        for i, item in enumerate(rows[:num], start=1):
            normalized.append(
                _result(
                    item.get("title") or item.get("name"),
                    item.get("url") or item.get("link") or item.get("href") or item.get("website"),
                    item.get("description") or item.get("snippet") or item.get("text") or item.get("content"),
                    i,
                    self.provider,
                    {"source_tool": "call-actor", "actor": actor, "dataset_id": _find_dataset_id(payload)},
                )
            )
        return [row for row in normalized if row["link"] or row["title"]]

    async def _maybe_fetch_dataset_items(self, payload: Any) -> Any:
        dataset_id = _find_dataset_id(payload)
        if not dataset_id:
            return payload
        try:
            items = await self.client.call_tool("get-dataset-items", {"datasetId": dataset_id, "limit": 50})
            parsed = _structured_payload(items)
            return parsed if parsed else payload
        except MCPClientError as exc:
            logger.info("[Apify MCP] dataset fetch skipped: %s", exc)
            return payload


class ApifySocialSearchAdapter(ApifyMCPSearchAdapter):
    """Dedicated public social profile search through explicit Apify Actors."""

    provider = "apify_social_mcp"

    def _budget_int(self, key: str, default: int, *, floor: int = 1, ceiling: int = 100) -> int:
        value = self.budget.get(key, getattr(self.settings, key, default))
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(floor, min(parsed, ceiling))

    def _budget_float(self, key: str, default: float, *, floor: float = 0.01, ceiling: float = 25.0) -> float:
        value = self.budget.get(key, getattr(self.settings, key, default))
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = default
        return max(floor, min(parsed, ceiling))

    async def instagram_search(self, query: str, *, num: int = 10, gl: str = "", hl: str = "") -> list[dict[str, Any]]:
        actor = self.settings.apify_instagram_actor or "apify/instagram-scraper"
        actor_input = {
            "search": query,
            "searchType": "user",
            "searchLimit": max(1, min(num, 50)),
            "resultsType": "details",
        }
        return await self._call_social_actor(
            actor=actor,
            actor_input=actor_input,
            source="apify_instagram",
            normalizer=_normalize_instagram_item,
            num=num,
        )

    async def facebook_search(self, query: str, *, num: int = 10, gl: str = "", hl: str = "") -> list[dict[str, Any]]:
        actor = self.settings.apify_facebook_pages_actor or "apify/facebook-pages-scraper"
        actor_input = {
            "search": query,
            "maxItems": max(1, min(num, 50)),
        }
        return await self._call_social_actor(
            actor=actor,
            actor_input=actor_input,
            source="apify_facebook",
            normalizer=_normalize_facebook_item,
            num=num,
        )

    async def _call_social_actor(
        self,
        *,
        actor: str,
        actor_input: dict[str, Any],
        source: str,
        normalizer,
        num: int,
    ) -> list[dict[str, Any]]:
        prefer_mcp = _as_bool(getattr(self.settings, "apify_social_prefer_mcp", False)) or str(
            getattr(self.settings, "apify_social_transport", "http")
        ).strip().lower() == "mcp"
        if not prefer_mcp:
            payload = await self._call_actor_api(actor=actor, actor_input=actor_input, num=num)
            return self._normalize_social_payload(payload, source=source, actor=actor, normalizer=normalizer, num=num)

        arguments: dict[str, Any] = {
            "actor": actor,
            "input": actor_input,
            "waitSecs": min(45, max(1, int(self.settings.apify_mcp_timeout_seconds or 45))),
            "callOptions": {
                "maxItems": self._budget_int("apify_actor_max_items", num),
                "maxTotalChargeUsd": self._budget_float("apify_actor_max_total_charge_usd", 0.2),
            },
        }
        try:
            result = await self.client.call_tool("call-actor", arguments)
            payload = _structured_payload(result)
            payload = await self._maybe_fetch_dataset_items(payload)
        except Exception as exc:
            logger.warning("[Apify Social] MCP call failed for actor=%s, falling back to Apify API: %s", actor, exc)
            payload = await self._call_actor_api(actor=actor, actor_input=actor_input, num=num)
        return self._normalize_social_payload(payload, source=source, actor=actor, normalizer=normalizer, num=num)

    def _normalize_social_payload(self, payload: Any, *, source: str, actor: str, normalizer, num: int) -> list[dict[str, Any]]:
        rows = _iter_candidate_items(payload)
        normalized: list[dict[str, Any]] = []
        for i, item in enumerate(rows[:num], start=1):
            row = normalizer(item, i, source, actor)
            if row.get("link") or row.get("title"):
                normalized.append(row)
        return normalized

    async def _call_actor_api(self, *, actor: str, actor_input: dict[str, Any], num: int) -> Any:
        if not self.settings.apify_token:
            raise MCPClientError("APIFY_TOKEN is not configured")
        actor_id = actor.replace("/", "~")
        actor_timeout = self._budget_int("apify_actor_timeout_seconds", 120, floor=30, ceiling=300)
        poll_interval = self._budget_int("apify_poll_interval_seconds", 3, floor=1, ceiling=15)
        dataset_limit = self._budget_int("apify_dataset_item_limit", num, floor=1, ceiling=100)
        params = {
            "token": self.settings.apify_token,
            "maxItems": self._budget_int("apify_actor_max_items", num),
            "maxTotalChargeUsd": self._budget_float("apify_actor_max_total_charge_usd", 0.2),
        }
        timeout = httpx.Timeout(min(actor_timeout + 20.0, 320.0), connect=15.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            run_response = await client.post(
                f"https://api.apify.com/v2/acts/{actor_id}/runs",
                params=params,
                json=actor_input,
            )
            run_response.raise_for_status()
            run_data = run_response.json().get("data") or {}
            run_id = str(run_data.get("id") or "")
            started_at = time.monotonic()
            while run_id and str(run_data.get("status") or "").upper() not in {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}:
                if time.monotonic() - started_at >= actor_timeout:
                    raise MCPClientError(f"Apify actor {actor} timed out after {actor_timeout}s (run_id={run_id})")
                await asyncio.sleep(poll_interval)
                status_response = await client.get(
                    f"https://api.apify.com/v2/actor-runs/{run_id}",
                    params={"token": self.settings.apify_token},
                )
                status_response.raise_for_status()
                run_data = status_response.json().get("data") or {}
            status = str(run_data.get("status") or "").upper()
            if status and status != "SUCCEEDED":
                raise MCPClientError(f"Apify actor {actor} ended with status={status} run_id={run_id}")
            dataset_id = run_data.get("defaultDatasetId") or run_data.get("defaultDatasetID")
            if not dataset_id:
                raise MCPClientError(f"Apify actor {actor} finished without a default dataset")
            item_response = await client.get(
                f"https://api.apify.com/v2/datasets/{dataset_id}/items",
                params={"token": self.settings.apify_token, "limit": max(1, min(dataset_limit, 100)), "clean": "true"},
            )
            item_response.raise_for_status()
            items = item_response.json()
            logger.info(
                "[Apify Social HTTP] actor=%s run_id=%s status=%s dataset=%s items=%d",
                actor,
                run_id or "(unknown)",
                status or "(unknown)",
                dataset_id,
                len(items) if isinstance(items, list) else 0,
            )
            return items


def _find_dataset_id(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("defaultDatasetId", "datasetId", "dataset_id"):
            found = value.get(key)
            if found:
                return str(found)
        for child in value.values():
            found = _find_dataset_id(child)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_dataset_id(item)
            if found:
                return found
    return ""


class MCPMultiSourceSearchTool:
    """Search Tavily and Apify through MCP with dedupe and fallback semantics."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.adapters: dict[str, Any] = {}
        if settings.tavily_mcp_enabled and settings.tavily_api_key:
            self.adapters["tavily"] = TavilyMCPSearchAdapter(settings)
        if settings.apify_mcp_enabled and settings.apify_token and getattr(settings, "apify_web_rag_enabled", False):
            self.adapters["apify"] = ApifyMCPSearchAdapter(settings)
        configured_order = [p.strip().lower() for p in settings.mcp_search_provider_order.split(",") if p.strip()]
        self.provider_order = [p for p in configured_order if p in self.adapters]
        for provider in self.adapters:
            if provider not in self.provider_order:
                self.provider_order.append(provider)
        self._backend = "mcp(" + "+".join(self.provider_order) + ")"

    @property
    def backend(self) -> str:
        return self._backend if self.adapters else "mcp(unconfigured)"

    @property
    def configured(self) -> bool:
        return bool(self.adapters)

    async def search(self, query: str, *, num: int = 10, gl: str = "", hl: str = "") -> list[dict[str, Any]]:
        if not self.adapters:
            raise MCPClientError("MCP search is enabled but Tavily/Apify credentials are not configured")
        seen: set[str] = set()
        merged: list[dict[str, Any]] = []
        for provider in self.provider_order:
            adapter = self.adapters.get(provider)
            if adapter is None:
                continue
            try:
                rows = await adapter.search(query, num=num, gl=gl, hl=hl)
            except Exception as exc:
                logger.warning("[MCP Search] provider=%s failed: %s", provider, exc)
                continue
            for row in rows:
                key = (row.get("link") or row.get("title") or "").strip().lower()
                if not key or key in seen:
                    continue
                seen.add(key)
                row["position"] = len(merged) + 1
                merged.append(row)
                if len(merged) >= num:
                    return merged
        return merged

    async def close(self) -> None:
        return None
