"""Controlled executor for unified MCP-style Hunt tool plans."""

from __future__ import annotations

from typing import Any
import re

from config.settings import Settings
from hunt_copilot.schemas import ToolExecutionPreview, ToolPlan, ToolPlanStep
from tool_executor.registry import get_managed_tool


class ToolExecutor:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def preview_plan(self, plan: ToolPlan) -> list[ToolExecutionPreview]:
        previews: list[ToolExecutionPreview] = []
        seen: set[str] = set()
        for step in plan.steps:
            if step.tool in seen:
                continue
            seen.add(step.tool)
            previews.append(self.preview_step(step))
        return previews

    def preview_step(self, step: ToolPlanStep) -> ToolExecutionPreview:
        base = {"tool": step.tool, "phase": step.phase, "execution_mode": step.execution_mode}
        definition = get_managed_tool(step.tool)
        if definition is None:
            return ToolExecutionPreview(**base, status="disabled", message="工具未注册。")
        if not definition.enabled:
            return ToolExecutionPreview(**base, status="disabled", message="工具已禁用。")
        missing = [key for key in definition.required_config if not self._setting_value(key)]
        if missing:
            return ToolExecutionPreview(**base, status="missing_config", message="缺少配置：" + "、".join(missing))
        if step.tool == "browser.assist.chrome" and getattr(self.settings, "chrome_mcp_manual_only", True):
            return ToolExecutionPreview(**base, status="blocked", message="Chrome 通道是人工辅助通道，不会自动执行。")
        if step.execution_mode == "candidate_enrichment":
            return ToolExecutionPreview(**base, status="ready", message="候选客户合并后按公司实体补全，不在主搜索阶段逐关键词执行。")
        if step.execution_mode == "disabled":
            return ToolExecutionPreview(**base, status="blocked", message="当前只做能力预览，暂不自动执行。")
        return ToolExecutionPreview(**base, status="ready", message="工具配置可用，等待后端状态机确认后执行。")

    async def execute_step(self, step: ToolPlanStep, *, budget: dict[str, Any] | None = None, gl: str = "", hl: str = "") -> dict[str, Any]:
        preview = self.preview_step(step)
        if preview.status != "ready":
            return {"tool": step.tool, "status": "blocked", "items": [], "cost_usd": 0.0, "blocked_reason": preview.message}

        if step.tool == "web.search.tavily":
            from mcp_tools.search_adapters import TavilyMCPSearchAdapter
            from tools.web_search import WebSearchTool

            try:
                rows = await TavilyMCPSearchAdapter(self.settings).search(step.query, num=step.max_results, gl=gl, hl=hl)
            except Exception:
                rows = []
            if not rows:
                fallback = WebSearchTool(self.settings, allow_mcp=False)
                try:
                    rows = await fallback.search(step.query, num=step.max_results, gl=gl, hl=hl)
                    for row in rows:
                        row.setdefault("source", getattr(fallback, "backend", "tavily_fallback"))
                        row.setdefault("source_tool", "tavily_sdk_fallback")
                finally:
                    await fallback.close()
            return _result(step.tool, rows)
        if step.tool == "web.extract.tavily":
            from mcp_tools.search_adapters import TavilyMCPSearchAdapter

            rows = await TavilyMCPSearchAdapter(self.settings).extract([step.query])
            return _result(step.tool, rows)
        if step.tool == "web.crawl.tavily":
            from mcp_tools.search_adapters import TavilyMCPSearchAdapter

            rows = await TavilyMCPSearchAdapter(self.settings).crawl(step.query, max_depth=1, max_pages=step.max_results)
            return _result(step.tool, rows)
        if step.tool == "local.search.google_maps":
            from tools.google_maps_search import GoogleMapsSearchTool

            maps = GoogleMapsSearchTool(self.settings)
            try:
                places = await maps.search(step.query, gl=gl, hl=hl)
                if not places:
                    for retry_query in _maps_retry_queries(step.query):
                        if retry_query == step.query:
                            continue
                        places = await maps.search(retry_query, gl=gl, hl=hl)
                        if places:
                            break
            finally:
                await maps.close()
            return _result(step.tool, [_maps_row(place, index) for index, place in enumerate(places[: step.max_results], start=1)])
        if step.tool == "social.search.instagram.apify":
            from mcp_tools.search_adapters import ApifySocialSearchAdapter

            rows = await ApifySocialSearchAdapter(self.settings, budget=budget or {}).instagram_search(step.query, num=step.max_results, gl=gl, hl=hl)
            return _result(step.tool, rows)
        if step.tool == "social.search.facebook.apify":
            from mcp_tools.search_adapters import ApifySocialSearchAdapter

            rows = await ApifySocialSearchAdapter(self.settings, budget=budget or {}).facebook_search(step.query, num=step.max_results, gl=gl, hl=hl)
            return _result(step.tool, rows)
        if step.tool.startswith("browser."):
            return {"tool": step.tool, "status": "blocked", "items": [], "cost_usd": 0.0, "blocked_reason": "浏览器工具只用于人工授权的公开页面复核。"}
        if step.tool.startswith("evidence."):
            return {"tool": step.tool, "status": "blocked", "items": [], "cost_usd": 0.0, "blocked_reason": "OpenSearch 执行入口等待索引配置完成后启用。"}
        return {"tool": step.tool, "status": "blocked", "items": [], "cost_usd": 0.0, "blocked_reason": "工具尚未绑定执行器。"}

    def _setting_value(self, key: str) -> str:
        mapping = {
            "TAVILY_API_KEY": self.settings.tavily_api_key,
            "APIFY_TOKEN": self.settings.apify_token,
            "SERPER_API_KEY": self.settings.serper_api_key,
            "JINA_API_KEY": self.settings.jina_api_key,
            "META_ACCESS_TOKEN": getattr(self.settings, "meta_access_token", ""),
            "OPENSEARCH_ENDPOINT": getattr(self.settings, "opensearch_endpoint", ""),
        }
        return str(mapping.get(key, "") or "").strip()


def _result(tool: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"tool": tool, "status": "success", "items": rows, "cost_usd": 0.0, "blocked_reason": ""}


_MAPS_NOISE_RE = re.compile(r"\b(email|e-mail|phone|telephone|tel|contact|instagram|facebook|linkedin|whatsapp|site:\S+)\b", re.I)


def _maps_retry_queries(query: str) -> list[str]:
    clean = re.sub(r"\s+", " ", _MAPS_NOISE_RE.sub(" ", str(query or ""))).strip()
    variants = [str(query or "").strip(), clean]
    words = clean.split()
    if len(words) >= 5:
        # Maps performs better with business/category + country/city than with a
        # long product sentence. Keep deterministic reduced forms as bounded
        # retries instead of firing more broad queries.
        variants.append(" ".join(words[-4:]))
        variants.append(" ".join([*words[:2], *words[-2:]]))
    deduped: list[str] = []
    seen: set[str] = set()
    for value in variants:
        key = value.lower()
        if value and key not in seen:
            seen.add(key)
            deduped.append(value)
    return deduped[:3]


def _maps_row(place: dict[str, Any], position: int) -> dict[str, Any]:
    maps_data = {
        "title": place.get("title", ""),
        "address": place.get("address", ""),
        "type": place.get("type", ""),
        "types": place.get("types", []),
        "website": place.get("website", ""),
        "phone_number": place.get("phone_number", ""),
        "phoneNumber": place.get("phone_number", ""),
        "description": place.get("description", ""),
        "email": place.get("email", ""),
        "rating": place.get("rating", 0),
        "rating_count": place.get("rating_count", 0),
        "latitude": place.get("latitude", 0),
        "longitude": place.get("longitude", 0),
        "cid": place.get("cid", ""),
        "place_id": place.get("place_id", ""),
    }
    snippet_parts = [maps_data.get("type"), maps_data.get("address"), maps_data.get("phone_number")]
    return {
        "title": place.get("title", ""),
        "link": place.get("website", ""),
        "snippet": " | ".join(str(part) for part in snippet_parts if part),
        "position": position,
        "source": "google_maps",
        "maps_data": maps_data,
    }
