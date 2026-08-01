# MCP Design

MCP exposes JPS One capabilities to Codex and future agents.

First contracts:

- `product_catalog.search`
- `lead_store.search`
- `knowledge.search`
- `integration_status.check`
- `match_engine.recommend_products`
- `quote_engine.create_draft`

Phase one should be read-only where possible.

Security:

- Do not return secrets.
- Write operations require authorization and audit logs.
- Tool outputs should be scoped and reviewable.

