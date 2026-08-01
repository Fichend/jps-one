# Knowledge / RAG

`knowledge/` is the JPS One RAG foundation. It stores and retrieves JPS-specific knowledge for product matching, outreach, quoting, and market reasoning.

Knowledge types:

- `product_docs`
- `price_rules`
- `email_templates`
- `market_rules`
- `sales_cases`
- `company_docs`

First version goals:

- Define schemas and metadata.
- Provide ingestion and retrieval placeholders.
- Preserve citations.
- Avoid hidden facts: every generated recommendation should be able to cite source chunks or explicit business rules.

