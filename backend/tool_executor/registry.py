"""Unified MCP-style tool registry for controlled Hunt execution."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ManagedToolDefinition:
    tool_id: str
    display_name: str
    provider: str
    required_config: list[str] = field(default_factory=list)
    budget_sensitive: bool = False
    safety_policy: str = "public_or_authorized_only"
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)
    enabled: bool = True


TOOLS: tuple[ManagedToolDefinition, ...] = (
    ManagedToolDefinition(
        tool_id="web.search.tavily",
        display_name="Tavily Web Search",
        provider="tavily_mcp",
        required_config=["TAVILY_API_KEY"],
        budget_sensitive=True,
        input_schema={"query": "string", "max_results": "integer"},
        output_schema={"items": "search_result[]"},
    ),
    ManagedToolDefinition(
        tool_id="web.extract.tavily",
        display_name="Tavily Extract",
        provider="tavily_mcp",
        required_config=["TAVILY_API_KEY"],
        budget_sensitive=True,
        input_schema={"urls": "string[]"},
        output_schema={"items": "page_evidence[]"},
    ),
    ManagedToolDefinition(
        tool_id="web.crawl.tavily",
        display_name="Tavily Crawl",
        provider="tavily_mcp",
        required_config=["TAVILY_API_KEY"],
        budget_sensitive=True,
        input_schema={"url": "string", "max_depth": "integer", "max_pages": "integer"},
        output_schema={"items": "site_page_evidence[]"},
    ),
    ManagedToolDefinition(
        tool_id="local.search.google_maps",
        display_name="Google Maps / Serper",
        provider="serper",
        required_config=["SERPER_API_KEY"],
        budget_sensitive=True,
        input_schema={"query": "string", "max_results": "integer"},
        output_schema={"items": "maps_place[]"},
    ),
    ManagedToolDefinition(
        tool_id="social.search.instagram.apify",
        display_name="Apify Instagram Public Profile Search",
        provider="apify_mcp",
        required_config=["APIFY_TOKEN"],
        budget_sensitive=True,
        input_schema={"query": "string", "max_results": "integer"},
        output_schema={"items": "public_instagram_profile[]"},
    ),
    ManagedToolDefinition(
        tool_id="social.search.facebook.apify",
        display_name="Apify Facebook Public Page Search",
        provider="apify_mcp",
        required_config=["APIFY_TOKEN"],
        budget_sensitive=True,
        input_schema={"query": "string", "max_results": "integer"},
        output_schema={"items": "public_facebook_page[]"},
    ),
    ManagedToolDefinition(
        tool_id="browser.read.playwright",
        display_name="Playwright Public Page Reader",
        provider="playwright_mcp",
        required_config=[],
        input_schema={"url": "string"},
        output_schema={"items": "page_evidence[]"},
    ),
    ManagedToolDefinition(
        tool_id="browser.assist.chrome",
        display_name="Chrome Manual Assisted Review",
        provider="chrome_mcp",
        required_config=[],
        input_schema={"url": "string"},
        output_schema={"items": "manual_page_evidence[]"},
    ),
    ManagedToolDefinition(
        tool_id="evidence.search.opensearch",
        display_name="OpenSearch Evidence Search",
        provider="opensearch_mcp",
        required_config=["OPENSEARCH_ENDPOINT"],
        input_schema={"query": "string", "max_results": "integer"},
        output_schema={"items": "indexed_evidence[]"},
    ),
    ManagedToolDefinition(
        tool_id="evidence.index.opensearch",
        display_name="OpenSearch Evidence Index",
        provider="opensearch_mcp",
        required_config=["OPENSEARCH_ENDPOINT"],
        input_schema={"items": "candidate_evidence[]"},
        output_schema={"indexed": "integer"},
    ),
)


def list_managed_tools() -> list[ManagedToolDefinition]:
    return list(TOOLS)


def get_managed_tool(tool_id: str) -> ManagedToolDefinition | None:
    for tool in TOOLS:
        if tool.tool_id == tool_id:
            return tool
    return None
