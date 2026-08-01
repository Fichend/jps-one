"""Tests for agents/search_agent.py — Google Maps-only routing, dedup, stats."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from agents.search_agent import (
    _build_maps_snippet,
    _execute_tool_plan_search,
    _is_china_region,
    _is_relevant_social_row,
    _maps_search_keyword,
    _result_identity_key,
    search_node,
)


def _base_state(**overrides):
    base = {
        "website_url": "https://solartech.de",
        "product_keywords": ["solar inverter"],
        "target_regions": ["Europe"],
        "uploaded_files": [],
        "target_lead_count": 200,
        "max_rounds": 10,
        "insight": {
            "products": ["solar inverter"],
            "industries": ["Renewable Energy"],
        },
        "keywords": ["solar inverter distributor", "PV panel wholesale"],
        "used_keywords": ["solar inverter distributor", "PV panel wholesale"],
        "search_results": [],
        "search_sources": ["google_maps"],
        "search_budget": {},
        "candidate_pool": [],
        "seen_urls": [],
        "matched_platforms": [],
        "keyword_search_stats": {},
        "leads": [],
        "email_sequences": [],
        "hunt_round": 1,
        "prev_round_lead_count": 0,
        "round_feedback": None,
        "current_stage": "keyword_gen",
        "messages": [],
    }
    base.update(overrides)
    return base


class TestMapsSearchKeyword:
    @pytest.mark.asyncio
    async def test_returns_maps_results_and_fields(self):
        sem = asyncio.Semaphore(5)
        mock_tool = AsyncMock()
        mock_tool.search = AsyncMock(return_value=[
            {
                "title": "Solar Co",
                "website": "https://solar.com",
                "address": "Berlin",
                "phone_number": "+49 123",
                "rating": 4.5,
                "rating_count": 100,
                "type": "Solar company",
                "types": ["Solar company"],
                "description": "Distributor",
                "email": "sales@solar.com",
                "place_id": "abc",
            },
        ])

        result = await _maps_search_keyword("solar", mock_tool, sem)
        assert result["keyword"] == "solar"
        assert result["result_count"] == 1
        assert result["source"] == "google_maps"
        assert result["results"][0]["link"] == "https://solar.com"
        assert result["results"][0]["maps_data"]["phoneNumber"] == "+49 123"
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_keeps_maps_rows_without_website(self):
        sem = asyncio.Semaphore(5)
        mock_tool = AsyncMock()
        mock_tool.search = AsyncMock(return_value=[
            {"title": "No Website Co", "address": "Berlin", "place_id": "pid-1"},
            {"title": "Has Website", "website": "https://has.com", "address": "Munich", "place_id": "pid-2"},
        ])

        result = await _maps_search_keyword("test", mock_tool, sem)
        assert result["result_count"] == 2
        assert result["results"][0]["link"] == ""
        assert result["results"][0]["maps_data"]["place_id"] == "pid-1"

    @pytest.mark.asyncio
    async def test_handles_maps_error(self):
        sem = asyncio.Semaphore(5)
        mock_tool = AsyncMock()
        mock_tool.search = AsyncMock(side_effect=Exception("Maps API error"))

        result = await _maps_search_keyword("test", mock_tool, sem)
        assert result["result_count"] == 0
        assert result["source"] == "google_maps"
        assert result["error"] == "Maps API error"


class TestBuildMapsSnippet:
    def test_full_snippet(self):
        place = {"type": "Solar", "address": "Berlin", "phone_number": "+49", "rating": 4.5, "rating_count": 10}
        assert _build_maps_snippet(place) == "Solar | Berlin | +49 | Rating: 4.5/5 (10 reviews)"

    def test_partial_snippet(self):
        place = {"type": "Solar", "address": "Berlin"}
        assert _build_maps_snippet(place) == "Solar | Berlin"

    def test_empty_snippet(self):
        assert _build_maps_snippet({}) == ""


class TestResultIdentityKey:
    def test_uses_url_when_present(self):
        key = _result_identity_key({"link": "https://example.com/a"})
        assert key == "url:https://example.com/a"

    def test_uses_place_id_without_url(self):
        key = _result_identity_key({"link": "", "maps_data": {"place_id": "PID-1"}})
        assert key == "place:pid-1"

    def test_falls_back_to_title_and_address(self):
        key = _result_identity_key({"title": "ACME", "maps_data": {"address": "Berlin"}})
        assert key == "maps:acme|berlin"


def test_social_relevance_does_not_use_source_keyword_as_proof():
    state = _base_state(
        product_keywords=["dental simulator"],
        keywords=["Thailand dental school"],
    )
    row = {
        "title": "School of Magic",
        "link": "https://www.instagram.com/school_of_magic/",
        "snippet": "Personal creator account and online magic lessons",
        "source": "apify_instagram",
        "source_keyword": "Thailand dental school",
        "evidence": {"username": "school_of_magic", "biography": "Magic lessons and tricks"},
    }

    assert _is_relevant_social_row(row, state) is False


class TestSearchNode:
    @pytest.mark.asyncio
    async def test_maps_only_routing(self):
        state = _base_state(keywords=["solar berlin"])

        maps_places = [
            {
                "title": "Maps Place",
                "website": "https://maps-place.com",
                "address": "Berlin",
                "type": "Solar",
                "types": ["Solar"],
                "place_id": "xyz",
            },
        ]

        with patch("agents.search_agent.GoogleMapsSearchTool") as MockMaps, \
             patch("agents.search_agent.get_settings") as mock_settings:

            mock_settings.return_value.search_concurrency = 5
            maps_inst = AsyncMock()
            maps_inst.search = AsyncMock(return_value=maps_places)
            maps_inst.close = AsyncMock()
            MockMaps.return_value = maps_inst

            result = await search_node(state)

        assert result["current_stage"] == "search"
        assert len(result["search_results"]) == 1
        assert result["search_results"][0]["source"] == "google_maps"
        maps_inst.search.assert_called_once()
        maps_inst.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_deduplicates_by_place_without_website(self):
        state = _base_state(
            keywords=["k1", "k2"],
            search_results=[],
            seen_urls=[],
        )

        maps_places = [{"title": "No Website Co", "address": "Berlin", "place_id": "pid-1"}]

        with patch("agents.search_agent.GoogleMapsSearchTool") as MockMaps, \
             patch("agents.search_agent.get_settings") as mock_settings:

            mock_settings.return_value.search_concurrency = 5
            maps_inst = AsyncMock()
            maps_inst.search = AsyncMock(return_value=maps_places)
            maps_inst.close = AsyncMock()
            MockMaps.return_value = maps_inst

            result = await search_node(state)

        assert len(result["search_results"]) == 1
        assert result["seen_urls"] == ["place:pid-1"]

    @pytest.mark.asyncio
    async def test_accumulates_keyword_stats(self):
        state = _base_state(keywords=["kw1"])

        maps_places = [
            {"title": "R1", "website": "https://r1.com", "place_id": "p1"},
            {"title": "R2", "address": "Berlin", "place_id": "p2"},
        ]

        with patch("agents.search_agent.GoogleMapsSearchTool") as MockMaps, \
             patch("agents.search_agent.get_settings") as mock_settings:

            mock_settings.return_value.search_concurrency = 5
            maps_inst = AsyncMock()
            maps_inst.search = AsyncMock(return_value=maps_places)
            maps_inst.close = AsyncMock()
            MockMaps.return_value = maps_inst

            result = await search_node(state)

        assert "kw1" in result["keyword_search_stats"]
        assert result["keyword_search_stats"]["kw1"]["result_count"] == 2

    @pytest.mark.asyncio
    async def test_empty_keywords_returns_early(self):
        state = _base_state(keywords=[])
        result = await search_node(state)
        assert result["current_stage"] == "search"

    @pytest.mark.asyncio
    async def test_tool_plan_runs_bounded_legacy_recall_when_underfilled(self):
        state = _base_state(
            keywords=["solar berlin"],
            search_sources=["web", "google_maps", "instagram", "facebook"],
            tool_plan={
                "objective": "solar",
                "steps": [{"tool": "web.search.tavily", "query": "solar berlin", "max_results": 5, "purpose": "test"}],
                "estimated_max_results": 5,
                "requires_user_confirmation": True,
                "created_by": "fallback",
            },
        )

        class FakeExecutor:
            def __init__(self, settings):
                self.settings = settings

            def preview_step(self, step):
                return type("Preview", (), {"status": "ready", "message": "ok"})()

            async def execute_step(self, step, **kwargs):
                return {
                    "tool": step.tool,
                    "status": "success",
                    "items": [{"title": "Tool Plan Result", "link": "https://tool-plan.example", "source": "tavily_mcp"}],
                }

        with patch("agents.search_agent.ToolExecutor", FakeExecutor), \
             patch("agents.search_agent.GoogleMapsSearchTool") as MockMaps, \
             patch("agents.search_agent.WebSearchTool") as MockWeb, \
             patch("agents.search_agent.get_settings") as mock_settings:
            mock_settings.return_value.search_concurrency = 5
            mock_settings.return_value.serper_api_key = "serper"
            mock_settings.return_value.apify_token = "apify"
            mock_settings.return_value.apify_actor_max_total_charge_usd = 0.2
            mock_settings.return_value.apify_task_max_total_charge_usd = 1.0
            maps_inst = AsyncMock()
            maps_inst.search = AsyncMock(return_value=[])
            maps_inst.close = AsyncMock()
            MockMaps.return_value = maps_inst
            web_inst = AsyncMock()
            web_inst.search = AsyncMock(return_value=[])
            web_inst.close = AsyncMock()
            web_inst.backend = "web"
            MockWeb.return_value = web_inst

            result = await search_node(state)

        assert len(result["search_results"]) == 1
        assert result["search_results"][0]["link"] == "https://tool-plan.example"
        assert maps_inst.search.call_count > 0
        assert web_inst.search.call_count > 0

    @pytest.mark.asyncio
    async def test_tool_plan_search_skips_candidate_enrichment_social_steps(self):
        state = _base_state(
            tool_plan={
                "objective": "Thailand dental simulator distributor",
                "steps": [
                    {
                        "tool": "web.search.tavily",
                        "query": "Thailand dental simulator distributor",
                        "max_results": 5,
                        "purpose": "discover entities",
                        "phase": "discovery",
                        "execution_mode": "search_phase",
                    },
                    {
                        "tool": "social.search.instagram.apify",
                        "query": "Thailand dental simulator distributor",
                        "max_results": 5,
                        "purpose": "enrich after merge",
                        "phase": "enrichment",
                        "execution_mode": "candidate_enrichment",
                    },
                    {
                        "tool": "social.search.facebook.apify",
                        "query": "Thailand dental simulator distributor",
                        "max_results": 5,
                        "purpose": "enrich after merge",
                        "phase": "enrichment",
                        "execution_mode": "candidate_enrichment",
                    },
                ],
                "estimated_max_results": 5,
                "requires_user_confirmation": True,
                "created_by": "fallback",
            }
        )

        class FakeExecutor:
            executed_tools = []

            def __init__(self, settings):
                self.settings = settings

            def preview_step(self, step):
                return type("Preview", (), {"status": "ready", "message": "ok"})()

            async def execute_step(self, step, **kwargs):
                self.executed_tools.append(step.tool)
                return {
                    "tool": step.tool,
                    "status": "success",
                    "items": [{"title": "Discovery Result", "link": "https://discovery.example", "source": step.tool}],
                }

        with patch("agents.search_agent.ToolExecutor", FakeExecutor):
            rows = await _execute_tool_plan_search(state, settings=object())

        assert FakeExecutor.executed_tools == ["web.search.tavily"]
        assert len(rows) == 1
        assert rows[0]["source"] == "web.search.tavily"

    @pytest.mark.asyncio
    async def test_tool_plan_search_blocks_legacy_social_search_phase_steps(self):
        state = _base_state(
            tool_plan={
                "objective": "Thailand dental simulator distributor",
                "steps": [
                    {
                        "tool": "social.search.instagram.apify",
                        "query": "Thailand dental simulator distributor",
                        "max_results": 5,
                        "purpose": "legacy social discovery",
                    }
                ],
                "estimated_max_results": 5,
                "requires_user_confirmation": True,
                "created_by": "fallback",
            }
        )

        class FakeExecutor:
            executed_tools = []

            def __init__(self, settings):
                self.settings = settings

            def preview_step(self, step):
                return type("Preview", (), {"status": "ready", "message": "ok"})()

            async def execute_step(self, step, **kwargs):
                self.executed_tools.append(step.tool)
                return {"tool": step.tool, "status": "success", "items": [{"title": "bad"}]}

        with patch("agents.search_agent.ToolExecutor", FakeExecutor):
            rows = await _execute_tool_plan_search(state, settings=object())

        assert FakeExecutor.executed_tools == []
        assert rows == []


class TestIsChinaRegion:
    def test_china_english(self):
        assert _is_china_region(["China"]) is True

    def test_china_chinese(self):
        assert _is_china_region(["中国"]) is True

    def test_non_china(self):
        assert _is_china_region(["Germany", "Poland"]) is False
