# Business Domain

`business/` contains JPS-specific rules and service objects. This is the core difference between JPS One and a generic lead finder.

Business modules should:

- Be independent of FastAPI request objects.
- Avoid direct provider API calls.
- Prefer deterministic rules where possible.
- Return evidence-aware, reviewable decisions.

Domains:

- `leads/` - customer pool, deduplication, status, ownership.
- `products/` - JPS product catalog and product metadata.
- `matching/` - customer-to-product scoring and explanation.
- `quotes/` - price rules, quote drafts, approval requirements.
- `crm/` - follow-up records, assignment, pipeline stages.

