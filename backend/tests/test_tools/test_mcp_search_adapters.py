import pytest

from config.settings import Settings
from mcp_tools.client import parse_jsonish, split_args
from mcp_tools.search_adapters import ApifySocialSearchAdapter, MCPMultiSourceSearchTool, TavilyMCPSearchAdapter


class FakeMCPClient:
    async def call_tool(self, tool_name, arguments):
        assert tool_name == "tavily_search"
        assert arguments["query"] == "medical distributor germany"
        return {
            "structuredContent": {
                "results": [
                    {
                        "title": "DentalMed GmbH",
                        "url": "https://dentalmed.example",
                        "content": "Dental and medical distributor in Germany.",
                        "score": 0.92,
                    }
                ]
            }
        }


def _settings(**overrides):
    defaults = {
        "mcp_search_enabled": True,
        "tavily_api_key": "tvly-test",
        "apify_token": "",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_split_args_accepts_commas_and_newlines():
    assert split_args("-y,tavily-mcp@latest\n--debug") == ["-y", "tavily-mcp@latest", "--debug"]


def test_parse_jsonish_extracts_embedded_json():
    assert parse_jsonish("Result:\n[{\"url\": \"https://example.com\"}]") == [{"url": "https://example.com"}]


@pytest.mark.asyncio
async def test_tavily_mcp_adapter_normalizes_results():
    adapter = TavilyMCPSearchAdapter(_settings())
    adapter.client = FakeMCPClient()

    rows = await adapter.search("medical distributor germany", num=5, gl="de")

    assert rows == [
        {
            "title": "DentalMed GmbH",
            "link": "https://dentalmed.example",
            "snippet": "Dental and medical distributor in Germany.",
            "position": 1,
            "source": "tavily_mcp",
            "source_tool": "tavily_search",
            "evidence": {"source_tool": "tavily_search", "raw_score": 0.92},
        }
    ]


def test_multi_source_search_reports_configured_providers():
    tool = MCPMultiSourceSearchTool(_settings(apify_token="apify-test", apify_web_rag_enabled=True))
    assert tool.configured is True
    assert tool.backend == "mcp(tavily+apify)"


def test_multi_source_search_can_be_unconfigured():
    tool = MCPMultiSourceSearchTool(_settings(tavily_api_key="", apify_token=""))
    assert tool.configured is False
    assert tool.backend == "mcp(unconfigured)"


class FakeApifySocialClient:
    def __init__(self):
        self.calls = []

    async def call_tool(self, tool_name, arguments):
        self.calls.append((tool_name, arguments))
        assert tool_name == "call-actor"
        return {
            "structuredContent": {
                "items": [
                    {
                        "username": "dental_demo",
                        "fullName": "Dental Demo",
                        "biography": "Dental training distributor",
                        "followersCount": 1280,
                        "externalUrl": "https://dental-demo.example",
                    }
                ]
            }
        }


@pytest.mark.asyncio
async def test_apify_instagram_adapter_uses_actor_schema_and_budget():
    adapter = ApifySocialSearchAdapter(
        _settings(apify_token="apify-test", apify_social_prefer_mcp=True),
        budget={"apify_actor_max_items": 7, "apify_actor_max_total_charge_usd": 0.13},
    )
    fake = FakeApifySocialClient()
    adapter.client = fake

    rows = await adapter.instagram_search("dental distributor", num=10)

    assert rows[0]["source"] == "apify_instagram"
    assert rows[0]["link"] == "https://www.instagram.com/dental_demo/"
    assert fake.calls[0][1]["actor"] == "apify/instagram-scraper"
    assert fake.calls[0][1]["input"] == {
        "search": "dental distributor",
        "searchType": "user",
        "searchLimit": 10,
        "resultsType": "details",
    }
    assert fake.calls[0][1]["callOptions"] == {"maxItems": 7, "maxTotalChargeUsd": 0.13}


@pytest.mark.asyncio
async def test_apify_social_defaults_to_http_without_mcp_call(monkeypatch):
    adapter = ApifySocialSearchAdapter(_settings(apify_token="apify-test", apify_social_prefer_mcp=False))
    fake = FakeApifySocialClient()
    adapter.client = fake

    async def fake_api(actor, actor_input, num):
        return [
            {
                "username": "direct_http",
                "fullName": "Direct HTTP",
                "biography": "Dental equipment distributor",
            }
        ]

    monkeypatch.setattr(adapter, "_call_actor_api", fake_api)

    rows = await adapter.instagram_search("dental distributor", num=5)

    assert rows[0]["link"] == "https://www.instagram.com/direct_http/"
    assert fake.calls == []


def test_multi_source_search_respects_apify_web_rag_flag():
    tool = MCPMultiSourceSearchTool(_settings(apify_token="apify-test", apify_web_rag_enabled=False))
    assert tool.configured is True
    assert tool.backend == "mcp(tavily)"
