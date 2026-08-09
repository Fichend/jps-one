"""SearchAgent — Google Maps-only discovery with concurrency and dedup."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from config.settings import get_settings
from candidate_pool import build_candidate_pool
from candidate_pool.intelligence import apply_candidate_intelligence
from graph.state import HuntState
from tools.google_maps_search import GoogleMapsSearchTool
from tools.platform_registry import PlatformRegistryTool  # backward-compatible patch target
from tools.web_search import WebSearchTool  # backward-compatible patch target
from tool_executor import ToolExecutor
from hunt_copilot.schemas import ToolPlan
from search_tools.locale_keyword_expander import LocaleKeywordExpander

logger = logging.getLogger(__name__)

# ── Region → Serper geo params mapping ───────────────────────────────────
# Kept here because KeywordGenAgent imports _REGION_GEO for language hints.
_REGION_GEO: dict[str, dict[str, str]] = {
    # English — Countries
    "germany": {"gl": "de", "hl": "de"},
    "france": {"gl": "fr", "hl": "fr"},
    "uk": {"gl": "uk", "hl": "en"},
    "united kingdom": {"gl": "uk", "hl": "en"},
    "italy": {"gl": "it", "hl": "it"},
    "spain": {"gl": "es", "hl": "es"},
    "netherlands": {"gl": "nl", "hl": "nl"},
    "poland": {"gl": "pl", "hl": "pl"},
    "czech republic": {"gl": "cz", "hl": "cs"},
    "czechia": {"gl": "cz", "hl": "cs"},
    "romania": {"gl": "ro", "hl": "ro"},
    "hungary": {"gl": "hu", "hl": "hu"},
    "turkey": {"gl": "tr", "hl": "tr"},
    "russia": {"gl": "ru", "hl": "ru"},
    "ukraine": {"gl": "ua", "hl": "uk"},
    "sweden": {"gl": "se", "hl": "sv"},
    "norway": {"gl": "no", "hl": "no"},
    "denmark": {"gl": "dk", "hl": "da"},
    "finland": {"gl": "fi", "hl": "fi"},
    "portugal": {"gl": "pt", "hl": "pt"},
    "austria": {"gl": "at", "hl": "de"},
    "switzerland": {"gl": "ch", "hl": "de"},
    "belgium": {"gl": "be", "hl": "nl"},
    "greece": {"gl": "gr", "hl": "el"},
    "usa": {"gl": "us", "hl": "en"},
    "united states": {"gl": "us", "hl": "en"},
    "canada": {"gl": "ca", "hl": "en"},
    "australia": {"gl": "au", "hl": "en"},
    "new zealand": {"gl": "nz", "hl": "en"},
    "japan": {"gl": "jp", "hl": "ja"},
    "south korea": {"gl": "kr", "hl": "ko"},
    "india": {"gl": "in", "hl": "en"},
    "brazil": {"gl": "br", "hl": "pt"},
    "mexico": {"gl": "mx", "hl": "es"},
    "china": {"gl": "cn", "hl": "zh-cn"},
    "singapore": {"gl": "sg", "hl": "en"},
    "thailand": {"gl": "th", "hl": "th"},
    "vietnam": {"gl": "vn", "hl": "vi"},
    "indonesia": {"gl": "id", "hl": "id"},
    "malaysia": {"gl": "my", "hl": "en"},
    "philippines": {"gl": "ph", "hl": "en"},
    "south africa": {"gl": "za", "hl": "en"},
    "uae": {"gl": "ae", "hl": "en"},
    "saudi arabia": {"gl": "sa", "hl": "ar"},
    # English — Composite regions
    "europe": {"gl": "de", "hl": "en"},
    "western europe": {"gl": "de", "hl": "en"},
    "eastern europe": {"gl": "pl", "hl": "en"},
    "central europe": {"gl": "de", "hl": "en"},
    "northern europe": {"gl": "se", "hl": "en"},
    "southern europe": {"gl": "it", "hl": "en"},
    "nordic": {"gl": "se", "hl": "en"},
    "scandinavia": {"gl": "se", "hl": "en"},
    "north america": {"gl": "us", "hl": "en"},
    "south america": {"gl": "br", "hl": "pt"},
    "latin america": {"gl": "br", "hl": "es"},
    "southeast asia": {"gl": "sg", "hl": "en"},
    "east asia": {"gl": "jp", "hl": "en"},
    "south asia": {"gl": "in", "hl": "en"},
    "middle east": {"gl": "ae", "hl": "en"},
    "africa": {"gl": "za", "hl": "en"},
    "oceania": {"gl": "au", "hl": "en"},
    # Chinese — Countries
    "德国": {"gl": "de", "hl": "de"},
    "法国": {"gl": "fr", "hl": "fr"},
    "英国": {"gl": "uk", "hl": "en"},
    "意大利": {"gl": "it", "hl": "it"},
    "西班牙": {"gl": "es", "hl": "es"},
    "荷兰": {"gl": "nl", "hl": "nl"},
    "波兰": {"gl": "pl", "hl": "pl"},
    "捷克": {"gl": "cz", "hl": "cs"},
    "罗马尼亚": {"gl": "ro", "hl": "ro"},
    "匈牙利": {"gl": "hu", "hl": "hu"},
    "土耳其": {"gl": "tr", "hl": "tr"},
    "俄罗斯": {"gl": "ru", "hl": "ru"},
    "乌克兰": {"gl": "ua", "hl": "uk"},
    "瑞典": {"gl": "se", "hl": "sv"},
    "挪威": {"gl": "no", "hl": "no"},
    "丹麦": {"gl": "dk", "hl": "da"},
    "芬兰": {"gl": "fi", "hl": "fi"},
    "葡萄牙": {"gl": "pt", "hl": "pt"},
    "奥地利": {"gl": "at", "hl": "de"},
    "瑞士": {"gl": "ch", "hl": "de"},
    "比利时": {"gl": "be", "hl": "nl"},
    "希腊": {"gl": "gr", "hl": "el"},
    "美国": {"gl": "us", "hl": "en"},
    "加拿大": {"gl": "ca", "hl": "en"},
    "澳大利亚": {"gl": "au", "hl": "en"},
    "新西兰": {"gl": "nz", "hl": "en"},
    "日本": {"gl": "jp", "hl": "ja"},
    "韩国": {"gl": "kr", "hl": "ko"},
    "印度": {"gl": "in", "hl": "en"},
    "巴西": {"gl": "br", "hl": "pt"},
    "墨西哥": {"gl": "mx", "hl": "es"},
    "中国": {"gl": "cn", "hl": "zh-cn"},
    "新加坡": {"gl": "sg", "hl": "en"},
    "泰国": {"gl": "th", "hl": "th"},
    "越南": {"gl": "vn", "hl": "vi"},
    "印尼": {"gl": "id", "hl": "id"},
    "印度尼西亚": {"gl": "id", "hl": "id"},
    "马来西亚": {"gl": "my", "hl": "en"},
    "菲律宾": {"gl": "ph", "hl": "en"},
    "南非": {"gl": "za", "hl": "en"},
    "阿联酋": {"gl": "ae", "hl": "en"},
    "沙特": {"gl": "sa", "hl": "ar"},
    "沙特阿拉伯": {"gl": "sa", "hl": "ar"},
    # Chinese — Composite regions
    "欧洲": {"gl": "de", "hl": "en"},
    "西欧": {"gl": "de", "hl": "en"},
    "东欧": {"gl": "pl", "hl": "en"},
    "中欧": {"gl": "de", "hl": "en"},
    "北欧": {"gl": "se", "hl": "en"},
    "南欧": {"gl": "it", "hl": "en"},
    "北美": {"gl": "us", "hl": "en"},
    "南美": {"gl": "br", "hl": "pt"},
    "拉丁美洲": {"gl": "br", "hl": "es"},
    "东南亚": {"gl": "sg", "hl": "en"},
    "东亚": {"gl": "jp", "hl": "en"},
    "南亚": {"gl": "in", "hl": "en"},
    "中东": {"gl": "ae", "hl": "en"},
    "非洲": {"gl": "za", "hl": "en"},
    "大洋洲": {"gl": "au", "hl": "en"},
}


def _resolve_geo_params(target_regions: list[str]) -> dict[str, str]:
    """Convert target_regions list to Serper gl/hl params using first match."""
    for region in target_regions:
        key = region.strip().lower()
        if key in _REGION_GEO:
            return _REGION_GEO[key]
    return {}


_CHINA_KEYWORDS = {"china", "中国", "cn", "大陆", "mainland china"}


def _is_china_region(target_regions: list[str]) -> bool:
    """Backward-compatible helper kept for tests and external imports."""
    for region in target_regions:
        if region.strip().lower() in _CHINA_KEYWORDS:
            return True
    return False


def _build_maps_snippet(place: dict) -> str:
    """Build a compact snippet from Maps place data."""
    parts = []
    if place.get("type"):
        parts.append(place["type"])
    if place.get("address"):
        parts.append(place["address"])
    if place.get("phone_number"):
        parts.append(place["phone_number"])
    if place.get("rating"):
        parts.append(f"Rating: {place['rating']}/5 ({place.get('rating_count', 0)} reviews)")
    return " | ".join(parts)


def _result_identity_key(item: dict) -> str:
    """Stable dedupe key for a search result, including Maps-only rows without website."""
    link = (item.get("link") or "").strip().lower()
    if link:
        return f"url:{link}"

    maps_data = item.get("maps_data") or {}
    place_id = (maps_data.get("place_id") or maps_data.get("cid") or "").strip().lower()
    if place_id:
        return f"place:{place_id}"

    title = (item.get("title") or "").strip().lower()
    address = (maps_data.get("address") or "").strip().lower()
    if title or address:
        return f"maps:{title}|{address}"

    return ""


_SOCIAL_SOURCES = {"apify_instagram", "apify_facebook", "social.search.instagram.apify", "social.search.facebook.apify"}
_RELEVANCE_STOPWORDS = {
    "vietnam", "thailand", "indonesia", "malaysia", "philippines", "india", "uae", "saudi", "arabia",
    "越南", "泰国", "印尼", "印度尼西亚", "马来西亚", "菲律宾", "印度", "阿联酋", "沙特",
    "school", "college", "university", "distributor", "supplier", "dealer", "company", "customer", "customers",
    "email", "phone", "instagram", "facebook", "linkedin", "contact", "official", "public",
}
_DENTAL_MARKERS = ("dental", "dentist", "dentistry", "orthodont", "odont", "nha khoa", "răng", "ทันต", "gigi", "pergigi")


def _requested_max_candidates(state: HuntState, settings) -> int:
    budget = state.get("search_budget") if isinstance(state.get("search_budget"), dict) else {}
    try:
        explicit = int(budget.get("max_candidates") or 0)
    except (TypeError, ValueError):
        explicit = 0
    if explicit > 0:
        return explicit
    try:
        target = int(state.get("target_lead_count") or 10)
    except (TypeError, ValueError):
        target = 10
    return max(target, target * int(getattr(settings, "candidate_pool_multiplier", 4) or 4))


def _is_social_row(item: dict[str, Any]) -> bool:
    source = str(item.get("source") or item.get("source_tool") or "").strip().lower()
    link = str(item.get("link") or "").lower()
    return source in _SOCIAL_SOURCES or "instagram.com" in link or "facebook.com" in link


def _row_text(item: dict[str, Any]) -> str:
    # Do not include source_keyword here. A social result returned from a query
    # like "Thailand dental school" is not automatically a dental-school entity;
    # only the row's own profile text, URL and evidence should prove relevance.
    values = [item.get("title"), item.get("snippet"), item.get("link")]
    evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
    for key in ("username", "fullName", "biography", "businessCategory", "externalUrl", "website", "category"):
        values.append(evidence.get(key))
    return " ".join(str(value or "") for value in values).lower()


def _product_relevance_tokens(state: HuntState) -> set[str]:
    raw_parts = [*(state.get("product_keywords") or []), *(_clean_list_for_tokens(state.get("keywords") or []))]
    text = " ".join(str(part or "") for part in raw_parts).lower()
    tokens = {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9-]{3,}|[\u4e00-\u9fff]{2,}", text)
        if token not in _RELEVANCE_STOPWORDS
    }
    if any(marker in text for marker in ("dental", "dent", "nha", "răng", "ทันต", "gigi", "odont", "牙科", "牙医")):
        tokens.update(_DENTAL_MARKERS)
    return tokens


def _clean_list_for_tokens(values: Any) -> list[str]:
    return [str(value or "") for value in values if str(value or "").strip()]


def _is_relevant_social_row(item: dict[str, Any], state: HuntState) -> bool:
    tokens = _product_relevance_tokens(state)
    if not tokens:
        return True
    text = _row_text(item)
    return any(token in text for token in tokens)


def _backfill_keywords(state: HuntState, *, max_queries: int) -> list[str]:
    budget = state.get("search_budget") if isinstance(state.get("search_budget"), dict) else {}
    seed = [*(_clean_list_for_tokens(state.get("keywords") or [])), *(_clean_list_for_tokens(state.get("used_keywords") or []))]
    expanded = LocaleKeywordExpander().expand(
        base_keywords=seed,
        target_regions=state.get("target_regions", []) or [],
        customer_profile=state.get("target_customer_profile", ""),
        product_keywords=state.get("product_keywords", []) or [],
        hard_filters={},
        max_keywords=max_queries,
    )
    exclusions = " ".join(str(item or "") for item in budget.get("exclusions", []) if str(item or "").strip())
    cleaned = []
    for query in expanded:
        value = re.sub(r"\b(email|phone|instagram|facebook|linkedin|contact)\b", " ", query, flags=re.I)
        value = re.sub(r"\s+", " ", value).strip()
        if exclusions and exclusions.lower() in value.lower():
            continue
        if value and value not in cleaned:
            cleaned.append(value)
    return cleaned[:max_queries]


async def _maps_search_keyword(
    keyword: str,
    maps_tool: GoogleMapsSearchTool,
    semaphore: asyncio.Semaphore,
    *,
    gl: str = "",
    hl: str = "",
) -> dict:
    """Search Google Maps for a keyword and return normalized rows."""
    async with semaphore:
        try:
            logger.info("[GoogleMaps] query=%r gl=%s hl=%s", keyword, gl or "(none)", hl or "(none)")
            places = await maps_tool.search(keyword, gl=gl, hl=hl)
            results = []
            for place in places:
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
                results.append({
                    "title": place.get("title", ""),
                    "link": place.get("website", ""),
                    "snippet": _build_maps_snippet(place),
                    "position": 0,
                    "source": "google_maps",
                    "maps_data": maps_data,
                })

            logger.info("[GoogleMaps] query=%r → %d places", keyword, len(results))
            return {
                "keyword": keyword,
                "results": results,
                "result_count": len(results),
                "source": "google_maps",
                "error": None,
            }
        except Exception as e:
            logger.warning("[GoogleMaps] FAILED query=%r: %s", keyword, e)
            return {
                "keyword": keyword,
                "results": [],
                "result_count": 0,
                "source": "google_maps",
                "error": str(e),
            }


async def _web_search_keyword(
    keyword: str,
    web_tool: WebSearchTool,
    semaphore: asyncio.Semaphore,
    *,
    gl: str = "",
    hl: str = "",
) -> dict:
    """Search the public web for a keyword and return normalized rows."""
    async with semaphore:
        try:
            logger.info("[WebSearch] query=%r gl=%s hl=%s", keyword, gl or "(none)", hl or "(none)")
            results = await web_tool.search(keyword, num=10, gl=gl, hl=hl)
            for item in results:
                item["source"] = getattr(web_tool, "backend", "web_search")
            logger.info("[WebSearch] query=%r -> %d results", keyword, len(results))
            return {
                "keyword": keyword,
                "results": results,
                "result_count": len(results),
                "source": getattr(web_tool, "backend", "web_search"),
                "error": None,
            }
        except Exception as e:
            logger.warning("[WebSearch] FAILED query=%r: %s", keyword, e)
            return {
                "keyword": keyword,
                "results": [],
                "result_count": 0,
                "source": "web_search",
                "error": str(e),
            }


async def _social_search_keyword(
    keyword: str,
    social_tool,
    platform: str,
    semaphore: asyncio.Semaphore,
    *,
    gl: str = "",
    hl: str = "",
) -> dict:
    """Search a public social platform through its dedicated adapter."""
    async with semaphore:
        try:
            logger.info("[%s Search] query=%r gl=%s hl=%s", platform, keyword, gl or "(none)", hl or "(none)")
            if platform == "instagram":
                results = await social_tool.instagram_search(keyword, num=10, gl=gl, hl=hl)
            elif platform == "facebook":
                results = await social_tool.facebook_search(keyword, num=10, gl=gl, hl=hl)
            else:
                results = []
            logger.info("[%s Search] query=%r -> %d results", platform, keyword, len(results))
            return {
                "keyword": keyword,
                "results": results,
                "result_count": len(results),
                "source": f"apify_{platform}",
                "error": None,
            }
        except Exception as e:
            logger.warning("[%s Search] FAILED query=%r: %s", platform, keyword, e)
            return {
                "keyword": keyword,
                "results": [],
                "result_count": 0,
                "source": f"apify_{platform}",
                "error": str(e),
            }


async def _execute_tool_plan_search(
    state: HuntState,
    settings,
    *,
    gl: str = "",
    hl: str = "",
) -> list[dict[str, Any]]:
    raw_plan = state.get("tool_plan")
    if not isinstance(raw_plan, dict):
        return []
    try:
        plan = ToolPlan.model_validate(raw_plan)
    except Exception as exc:
        logger.warning("[SearchAgent] Ignoring invalid tool_plan: %s", exc)
        return []

    executor = ToolExecutor(settings)
    budget = state.get("search_budget") if isinstance(state.get("search_budget"), dict) else {}
    raw_results: list[dict[str, Any]] = []
    search_phase_tools = {"web.search.tavily", "local.search.google_maps"}
    skipped_enrichment = 0
    for step in plan.steps:
        if step.execution_mode != "search_phase" or step.phase != "discovery":
            skipped_enrichment += 1
            logger.info(
                "[SearchAgent] Skipping non-discovery tool_plan step tool=%s phase=%s mode=%s",
                step.tool,
                step.phase,
                step.execution_mode,
            )
            continue
        if step.tool not in search_phase_tools:
            logger.info("[SearchAgent] Skipping tool_plan step outside search phase allowlist tool=%s", step.tool)
            continue
        preview = executor.preview_step(step)
        if preview.status != "ready":
            raw_results.append(
                {
                    "keyword": step.query,
                    "results": [],
                    "result_count": 0,
                    "source": step.tool,
                    "error": preview.message,
                }
            )
            continue
        try:
            result = await executor.execute_step(step, budget=budget, gl=gl, hl=hl)
            items = result.get("items") if isinstance(result.get("items"), list) else []
            raw_results.append(
                {
                    "keyword": step.query,
                    "results": items,
                    "result_count": len(items),
                    "source": step.tool,
                    "error": result.get("blocked_reason") or None,
                }
            )
        except Exception as exc:
            logger.warning("[SearchAgent] Tool plan step failed tool=%s query=%r: %r", step.tool, step.query, exc)
            raw_results.append(
                {
                    "keyword": step.query,
                    "results": [],
                    "result_count": 0,
                    "source": step.tool,
                    "error": str(exc),
                }
            )
    if raw_results:
        logger.info(
            "[SearchAgent] Executed controlled discovery tool_plan steps=%d skipped_enrichment=%d results=%d",
            len(raw_results),
            skipped_enrichment,
            sum(item.get("result_count", 0) for item in raw_results),
        )
    return raw_results


async def _backfill_tool_plan_recall(
    state: HuntState,
    settings,
    *,
    seen_keys: set[str],
    keyword_stats: dict[str, Any],
    gl: str = "",
    hl: str = "",
) -> list[dict[str, Any]]:
    """Add bounded legacy Web/Maps recall when a Tool Plan under-fills.

    Tool Plan is the standard path, but individual MCP servers can return zero
    rows for a valid query. This fallback keeps the business rule intact: first
    fill the candidate pool with real entities, then enrich and rank them.
    """
    max_candidates = _requested_max_candidates(state, settings)
    target_queries = min(10, max(4, max_candidates // 10 + 2))
    keywords = _backfill_keywords(state, max_queries=target_queries)
    if not keywords:
        return []

    semaphore = asyncio.Semaphore(max(1, int(getattr(settings, "search_concurrency", 5) or 5)))
    tasks = []
    web_tool = WebSearchTool(settings, allow_mcp=False)
    maps_tool = GoogleMapsSearchTool(settings)
    try:
        tasks.extend(_web_search_keyword(keyword, web_tool, semaphore, gl=gl, hl=hl) for keyword in keywords)
        if getattr(settings, "serper_api_key", ""):
            tasks.extend(_maps_search_keyword(keyword, maps_tool, semaphore, gl=gl, hl=hl) for keyword in keywords)

        new_results: list[dict[str, Any]] = []
        for future in asyncio.as_completed(tasks):
            try:
                result = await future
            except Exception as exc:
                logger.warning("[SearchAgent] Tool Plan recall backfill task failed: %s", exc)
                continue
            keyword = result.get("keyword", "")
            keyword_stats.setdefault(keyword, {"result_count": 0, "leads_found": 0})
            for item in result.get("results") or []:
                if not isinstance(item, dict):
                    continue
                item["source_keyword"] = keyword
                item_key = _result_identity_key(item)
                if not item_key or item_key in seen_keys:
                    continue
                seen_keys.add(item_key)
                new_results.append(item)
                keyword_stats[keyword]["result_count"] = keyword_stats[keyword].get("result_count", 0) + 1
                if len(new_results) >= max_candidates:
                    return new_results
        return new_results
    finally:
        try:
            await web_tool.close()
            await maps_tool.close()
        except Exception as exc:
            logger.warning("[SearchAgent] Error closing recall backfill tools: %s", exc)


def _resolve_search_sources(state: HuntState, settings) -> set[str]:
    raw = state.get("search_sources") or []
    if not raw:
        raw = [item.strip() for item in settings.search_sources_default.split(",") if item.strip()]
    normalized = {str(item).strip().lower() for item in raw if str(item).strip()}
    aliases = {"maps": "google_maps", "map": "google_maps", "web_search": "web", "ig": "instagram", "fb": "facebook"}
    return {aliases.get(item, item) for item in normalized} or {"web"}


def _social_actor_call_budget(state: HuntState, settings) -> int:
    budget = state.get("search_budget") or {}
    try:
        actor_cap = float(budget.get("apify_actor_max_total_charge_usd", settings.apify_actor_max_total_charge_usd) or 0.2)
    except (TypeError, ValueError):
        actor_cap = 0.2
    try:
        task_cap = float(budget.get("apify_task_max_total_charge_usd", settings.apify_task_max_total_charge_usd) or 1.0)
    except (TypeError, ValueError):
        task_cap = 1.0
    if actor_cap <= 0 or task_cap <= 0:
        return 0
    budget_from_cost = max(1, int(task_cap / actor_cap))
    try:
        query_cap = int(getattr(settings, "apify_max_social_queries_per_task", budget_from_cost) or budget_from_cost)
    except (TypeError, ValueError):
        query_cap = budget_from_cost
    return max(1, min(budget_from_cost, query_cap))


async def search_node(state: HuntState) -> dict:
    """LangGraph node: search for all round keywords."""
    settings = get_settings()
    keywords = state.get("keywords", [])
    target_regions = state.get("target_regions", [])

    logger.info("[SearchAgent] Starting — %d keywords, regions=%s", len(keywords), target_regions)

    if not keywords:
        logger.info("[SearchAgent] No keywords to search, skipping")
        return {"current_stage": "search"}

    budget = state.get("search_budget") if isinstance(state.get("search_budget"), dict) else {}
    if getattr(settings, "locale_keyword_expansion_enabled", True) and not isinstance(state.get("tool_plan"), dict):
        hard_filters = budget.get("hard_filters") if isinstance(budget.get("hard_filters"), dict) else {}
        max_candidates = int(budget.get("max_candidates") or state.get("target_lead_count", 10) * getattr(settings, "candidate_pool_multiplier", 4) or 40)
        keywords = LocaleKeywordExpander().expand(
            base_keywords=keywords,
            target_regions=target_regions,
            customer_profile=state.get("target_customer_profile", ""),
            product_keywords=state.get("product_keywords", []) or [],
            hard_filters=hard_filters,
            max_keywords=max(len(keywords), min(int(getattr(settings, "locale_keyword_max_per_round", 18) or 18), max(8, max_candidates // 5))),
        )

    geo = _resolve_geo_params(target_regions)
    gl = geo.get("gl", "")
    hl = geo.get("hl", "")
    if geo:
        logger.info("[SearchAgent] Resolved regions %s → gl=%s, hl=%s", target_regions, gl, hl)
    else:
        logger.info("[SearchAgent] No geo params resolved from regions=%s, searching globally", target_regions)

    search_sources = _resolve_search_sources(state, settings)
    has_tool_plan = isinstance(state.get("tool_plan"), dict)
    semaphore = asyncio.Semaphore(settings.search_concurrency)
    maps_tool = GoogleMapsSearchTool(settings)
    web_tool = WebSearchTool(settings)
    social_tool = None
    if not has_tool_plan and {"instagram", "facebook"} & search_sources and settings.apify_token:
        try:
            from mcp_tools.search_adapters import ApifySocialSearchAdapter

            social_tool = ApifySocialSearchAdapter(settings, budget=state.get("search_budget") or {})
        except Exception as exc:
            logger.warning("[SearchAgent] Social Apify adapter unavailable: %s", exc)
    social_call_budget = _social_actor_call_budget(state, settings)
    social_calls_scheduled = 0

    search_tasks = []
    social_tasks = []
    route = []
    if has_tool_plan:
        route.append("tool_plan(executor)")
    elif "web" in search_sources:
        search_tasks.extend(_web_search_keyword(kw, web_tool, semaphore, gl=gl, hl=hl) for kw in keywords)
        route.append(f"web_search({web_tool.backend})")
    if not has_tool_plan and "google_maps" in search_sources and settings.serper_api_key:
        search_tasks.extend(_maps_search_keyword(kw, maps_tool, semaphore, gl=gl, hl=hl) for kw in keywords)
        route.append("google_maps(serper)")
    elif not has_tool_plan and "google_maps" in search_sources:
        logger.warning("[SearchAgent] google_maps requested but SERPER_API_KEY is not configured")
    requested_social_sources = [source for source in ("instagram", "facebook") if source in search_sources]
    per_social_source_budget = max(1, social_call_budget // max(1, len(requested_social_sources)))
    if not has_tool_plan and "instagram" in search_sources and social_tool is not None and social_calls_scheduled < social_call_budget:
        allowed = min(per_social_source_budget, max(0, social_call_budget - social_calls_scheduled))
        scheduled_keywords = keywords[:allowed]
        social_tasks.extend(_social_search_keyword(kw, social_tool, "instagram", semaphore, gl=gl, hl=hl) for kw in scheduled_keywords)
        social_calls_scheduled += len(scheduled_keywords)
        route.append("instagram(apify)")
    if not has_tool_plan and "facebook" in search_sources and social_tool is not None and social_calls_scheduled < social_call_budget:
        allowed = min(per_social_source_budget, max(0, social_call_budget - social_calls_scheduled))
        scheduled_keywords = keywords[:allowed]
        social_tasks.extend(_social_search_keyword(kw, social_tool, "facebook", semaphore, gl=gl, hl=hl) for kw in scheduled_keywords)
        social_calls_scheduled += len(scheduled_keywords)
        route.append("facebook(apify)")
    if not has_tool_plan and {"instagram", "facebook"} & search_sources and social_tool is not None:
        logger.info(
            "[SearchAgent] Apify social budget scheduled %d/%d Actor calls",
            social_calls_scheduled,
            social_call_budget,
        )
    if not has_tool_plan and not search_tasks:
        search_tasks = [_web_search_keyword(kw, web_tool, semaphore, gl=gl, hl=hl) for kw in keywords]
        route = [f"web_search({web_tool.backend})"]

    logger.info("[SearchAgent] Tool routing: regions=%s → %s", target_regions, route)
    logger.info(
        "[SearchAgent] Launching %d web/maps tasks (concurrency=%d) and %d sequential social tasks",
        len(search_tasks),
        settings.search_concurrency,
        len(social_tasks),
    )

    raw_results = []
    if has_tool_plan:
        raw_results.extend(await _execute_tool_plan_search(state, settings, gl=gl, hl=hl))
    else:
        for future in asyncio.as_completed(search_tasks):
            try:
                raw_results.append(await future)
            except Exception as e:
                logger.error("[SearchAgent] Task failed: %s", e)
        for task in social_tasks:
            try:
                raw_results.append(await task)
            except Exception as e:
                logger.error("[SearchAgent] Social task failed: %s", e)

    if not has_tool_plan and "google_maps" in search_sources and "web" not in search_sources and sum(r.get("result_count", 0) for r in raw_results) == 0:
        logger.info("[SearchAgent] Maps returned zero results; falling back to WebSearch")
        fallback_tasks = [
            _web_search_keyword(kw, web_tool, semaphore, gl=gl, hl=hl)
            for kw in keywords
        ]
        for future in asyncio.as_completed(fallback_tasks):
            try:
                raw_results.append(await future)
            except Exception as e:
                logger.error("[SearchAgent] Fallback task failed: %s", e)

    all_results = state.get("search_results", [])
    existing_candidate_pool = state.get("candidate_pool", []) or []
    keyword_stats: dict[str, Any] = dict(state.get("keyword_search_stats", {}))

    # seen_urls now stores generic dedupe identities (URL or Maps place key).
    state_seen = state.get("seen_urls") or []
    seen_keys: set[str] = set(state_seen)
    if not seen_keys:
        for r in all_results:
            key = _result_identity_key(r)
            if key:
                seen_keys.add(key)

    initial_new_results = []
    for r in raw_results:
        base_kw = r["keyword"]
        if base_kw not in keyword_stats:
            keyword_stats[base_kw] = {"result_count": 0, "leads_found": 0}

        for item in r["results"]:
            item["source_keyword"] = base_kw
            if _is_social_row(item) and not _is_relevant_social_row(item, state):
                keyword_stats[base_kw]["result_count"] = keyword_stats[base_kw].get("result_count", 0)
                keyword_stats[base_kw]["irrelevant_social_skipped"] = keyword_stats[base_kw].get("irrelevant_social_skipped", 0) + 1
                continue
            item_key = _result_identity_key(item)
            if not item_key or item_key in seen_keys:
                continue
            seen_keys.add(item_key)
            initial_new_results.append(item)
            keyword_stats[base_kw]["result_count"] = keyword_stats[base_kw].get("result_count", 0) + 1

    hunt_id = state.get("hunt_id", "")
    if hunt_id:
        try:
            from observability.cost_tracker import get_tracker

            tracker = get_tracker(hunt_id)
            for r in raw_results:
                tracker.record_search_call(provider=r.get("source", "google_maps"), result_count=r.get("result_count", 0))
        except Exception:
            pass

    try:
        await maps_tool.close()
        await web_tool.close()
    except Exception as e:
        logger.warning("[SearchAgent] Error closing tools: %s", e)

    budget = state.get("search_budget") if isinstance(state.get("search_budget"), dict) else {}
    hard_filters = budget.get("hard_filters") if isinstance(budget.get("hard_filters"), dict) else {}
    target_final = int(budget.get("final_leads") or state.get("target_lead_count") or 10)
    exclusions = budget.get("exclusions") if isinstance(budget.get("exclusions"), list) else []
    customer_types = budget.get("customer_types") if isinstance(budget.get("customer_types"), list) else []
    product_keywords = budget.get("product_keywords") if isinstance(budget.get("product_keywords"), list) else state.get("product_keywords", []) or []
    goal_regions = budget.get("target_regions") if isinstance(budget.get("target_regions"), list) else target_regions
    max_candidates = _requested_max_candidates(state, settings)

    if has_tool_plan and budget.get("candidate_pool_enabled", True):
        preview_pool = build_candidate_pool(
            all_results + initial_new_results,
            hunt_id=hunt_id,
            target_final_leads=target_final,
            hard_filters=hard_filters,
            exclusions=exclusions,
            customer_types=customer_types,
            product_keywords=product_keywords,
            target_regions=goal_regions,
            max_candidates=max_candidates,
        )
        if len(preview_pool) < max(1, int(max_candidates * 0.8)):
            logger.info(
                "[SearchAgent] Tool Plan under-filled candidate pool (%d/%d); running bounded Web/Maps recall backfill",
                len(preview_pool),
                max_candidates,
            )
            backfill_results = await _backfill_tool_plan_recall(
                state,
                settings,
                seen_keys=seen_keys,
                keyword_stats=keyword_stats,
                gl=gl,
                hl=hl,
            )
            initial_new_results.extend(backfill_results)

    candidate_pool = build_candidate_pool(
        all_results + initial_new_results,
        hunt_id=hunt_id,
        target_final_leads=target_final,
        hard_filters=hard_filters,
        exclusions=exclusions,
        customer_types=customer_types,
        product_keywords=product_keywords,
        target_regions=goal_regions,
        max_candidates=max_candidates,
    )
    if existing_candidate_pool and not candidate_pool:
        candidate_pool = list(existing_candidate_pool)
    if candidate_pool and budget.get("candidate_pool_enabled", True):
        try:
            from enrichment import enrich_candidate_pool

            candidate_pool = await enrich_candidate_pool(
                candidate_pool,
                settings=settings,
                budget=budget,
                hunt_id=hunt_id,
                target_final_leads=target_final,
                hard_filters=hard_filters,
                exclusions=exclusions,
                customer_types=customer_types,
                product_keywords=product_keywords,
                target_regions=goal_regions,
            )
        except Exception as exc:
            logger.warning("[SearchAgent] Candidate enrichment skipped after error: %s", exc)

    if candidate_pool and budget.get("candidate_pool_enabled", True):
        try:
            insight = state.get("insight") if isinstance(state.get("insight"), dict) else {}
            candidate_pool = await apply_candidate_intelligence(
                candidate_pool,
                settings=settings,
                hunt_id=hunt_id,
                hunt_round=int(state.get("hunt_round", 0) or 0),
                search_budget=budget,
                insight=insight,
            )
        except Exception as exc:
            logger.warning("[SearchAgent] Candidate intelligence skipped after error: %s", exc)

    logger.info(
        "[SearchAgent] Completed — %d new results (total: %d)",
        len(initial_new_results),
        len(all_results) + len(initial_new_results),
    )

    return {
        "search_results": all_results + initial_new_results,
        "candidate_pool": candidate_pool,
        "seen_urls": list(seen_keys),
        "matched_platforms": [],
        "keyword_search_stats": keyword_stats,
        "current_stage": "search",
    }
