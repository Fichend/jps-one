"""MCP tool contract registry for JPS One.

The contracts are used by docs, diagnostics, and future MCP server entrypoints.
No external side effects happen here.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MCPToolContract(BaseModel):
    name: str
    purpose: str
    safety: str
    status: str = "planned"
    input_fields: list[str] = Field(default_factory=list)
    output_fields: list[str] = Field(default_factory=list)


MCP_TOOL_CONTRACTS: list[MCPToolContract] = [
    MCPToolContract(
        name="product_catalog.search",
        purpose="Search JPS products, selling points, target customers, and citations.",
        safety="Read-only. Must not expose price-sensitive fields unless the caller is authorized.",
        status="foundation",
        input_fields=["query", "category", "customer_type", "country", "limit"],
        output_fields=["products", "matched_chunks", "citations"],
    ),
    MCPToolContract(
        name="lead_store.search",
        purpose="Search lead pool by company, country, status, owner, or product interest.",
        safety="Read-only in phase one. Return only business-safe lead fields.",
        status="foundation",
        input_fields=["company_name", "country", "status", "product_interest", "owner", "limit"],
        output_fields=["leads", "contacts", "last_followups"],
    ),
    MCPToolContract(
        name="knowledge.search",
        purpose="Search RAG chunks across product docs, pricing rules, templates, market rules, and cases.",
        safety="Read-only. Return citations and source metadata.",
        status="foundation",
        input_fields=["query", "knowledge_types", "country", "customer_type", "limit"],
        output_fields=["chunks", "citations"],
    ),
    MCPToolContract(
        name="integration_status.check",
        purpose="Check Meta, WhatsApp, email, Tavily, Apify, MCP search, Jina, and model readiness.",
        safety="Read-only. Never return tokens, secrets, passwords, or full API keys.",
        status="foundation",
        input_fields=["provider"],
        output_fields=["status", "capabilities", "missing_permissions", "last_sync", "next_action"],
    ),
    MCPToolContract(
        name="search.multi_source",
        purpose="Run compliant public web discovery through the configured Tavily/Apify MCP provider order.",
        safety="Read-only. Public web and authorized-source search only; do not bypass login walls, CAPTCHA, or platform restrictions.",
        status="foundation",
        input_fields=["query", "country", "language", "limit", "provider_order"],
        output_fields=["results", "source_tool", "evidence", "dedupe_key"],
    ),
    MCPToolContract(
        name="web.extract_public_page",
        purpose="Read and summarize a public webpage or public profile URL for lead evidence.",
        safety="Read-only. Stop with blocked_or_unauthorized for private pages, login walls, CAPTCHA, or missing permission.",
        status="planned",
        input_fields=["url", "extract_fields", "source_hint"],
        output_fields=["url", "title", "summary", "contacts", "social_links", "compliance_status"],
    ),
    MCPToolContract(
        name="social.discover_public_profiles",
        purpose="Discover public LinkedIn, Facebook, Instagram, and website profile URLs from company/person search context.",
        safety="Public and authorized assets only. Never automate private social account access or scrape non-public data.",
        status="planned",
        input_fields=["company_name", "website", "country", "platforms", "limit"],
        output_fields=["profiles", "evidence_urls", "confidence", "compliance_flags"],
    ),
    MCPToolContract(
        name="match_engine.recommend_products",
        purpose="Recommend JPS products for a lead with evidence-based reasons.",
        safety="May use RAG and lead evidence. Must return reasons and citations.",
        status="planned",
        input_fields=["lead_id", "company_profile", "website_evidence", "target_product_category"],
        output_fields=["recommended_products", "score", "reasons", "citations", "risk_notes"],
    ),
    MCPToolContract(
        name="quote_engine.create_draft",
        purpose="Create a quote draft from selected products and customer context.",
        safety="Write operation. Requires audit log and approval policy before production use.",
        status="planned",
        input_fields=["lead_id", "product_items", "currency", "customer_level", "country", "trade_terms"],
        output_fields=["quote_id", "items", "total", "approval_required", "notes"],
    ),
]


def list_tool_contracts() -> list[dict[str, object]]:
    return [
        contract.model_dump() if hasattr(contract, "model_dump") else contract.dict()
        for contract in MCP_TOOL_CONTRACTS
    ]
