# Workflows

`workflows/` owns long-running business processes. A workflow coordinates API input, agents, connectors, business rules, persistence, and background jobs.

Rules:

- Keep orchestration here, not in FastAPI route handlers.
- Do not place provider-specific code here; call `connectors/`.
- Do not place JPS pricing or matching rules here; call `business/`.
- Return structured state that can be persisted, resumed, inspected, and tested.

Planned workflows:

- `hunt_workflow.py` - customer discovery from product/market inputs.
- `lead_enrichment_workflow.py` - website reading, contact extraction, evidence capture.
- `product_match_workflow.py` - customer-to-JPS product matching with RAG citations.
- `email_generation_workflow.py` - outreach drafts with policy and human review.
- `quote_generation_workflow.py` - quote draft creation from product and price rules.
- `integration_sync_workflow.py` - Meta, email, WhatsApp, and search source diagnostics/sync.

