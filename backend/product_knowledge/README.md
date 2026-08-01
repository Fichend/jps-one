# JPS Product Knowledge

This package contains a curated product knowledge layer for Hunt Copilot.

The goal is not to let the AI invent products. The recommender uses a small,
auditable catalogue template derived from `JPS Dental Catalogue 2026.pdf` and
`医疗耗材221104.pdf`, then returns product keywords that fit the user's target
customer type.

## Files

- `data/jps_dental_catalog_2026.pdf` - original catalogue, kept for traceability.
- `data/jps_medical_consumables_221104.pdf` - JPS medical consumables catalogue, kept for traceability.
- `data/jps_product_templates.json` - curated product families, aliases, customer fit, and Chinese-English mappings.
- `jps_catalog_loader.py` - safe JSON loader for the curated template.
- `jps_product_recommender.py` - deterministic product keyword recommender used by Hunt Copilot.

## Safety Rules

- The recommender only returns keywords from the curated JSON template.
- Chinese-English mapping is alias based; unknown words are not guessed as products.
- Dental and medical consumables catalogues share one curated template, but each product family keeps its own customer-fit rules.
- Excluded customer types have priority over target customer types.
- If product intent is still unclear, the Copilot should ask the user to confirm the suggested keywords before execution.

## Update Process

1. Add or revise products in `jps_product_templates.json`.
2. Keep English keywords concise and search-friendly.
3. Add Chinese aliases when sales users naturally describe the product in Chinese.
4. Run product knowledge and Hunt Copilot tests before deployment.
