# MCP Tools

`mcp_tools/` defines how JPS One exposes internal capabilities to Codex or future agents.

MCP is not a replacement for user-facing REST APIs. It is a tool surface for agentic workflows.

First tool contracts:

- `product_catalog.search`
- `lead_store.search`
- `knowledge.search`
- `integration_status.check`
- `match_engine.recommend_products`
- `quote_engine.create_draft`

Security rules:

- Do not return secrets.
- Start with read-only tools.
- Add write tools only with audit logging and authorization.

