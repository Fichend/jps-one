# RAG Design

JPS One RAG exists to support business decisions, not only chat Q&A.

Knowledge types:

- `product_docs`
- `price_rules`
- `email_templates`
- `market_rules`
- `sales_cases`
- `company_docs`

Pipeline:

```text
upload
-> parse
-> classify
-> chunk
-> metadata
-> embed
-> store
-> retrieve
-> cite
-> agent output
```

First version can use local metadata and vector storage. A later version can migrate to Postgres + pgvector.

