---
name: jps_one_lead_hunt
description: Run a JPS One customer discovery workflow with public sources and evidence.
---

# JPS One Lead Hunt

Use this skill for product/country/customer-type lead discovery.

Inputs:

- JPS product category or product keywords.
- Target country or region.
- Target customer profile.
- Optional source files.
- Target lead count and round limits.

Workflow:

1. Generate multilingual search strategy.
2. Search public web, maps, directories, B2B pages, and user uploads.
3. Read company websites.
4. Extract company, contact, product-line, and source evidence.
5. Deduplicate by website, company name, and email.
6. Save evidence and score lead quality.
7. Hand qualified leads to product matching.

Boundaries:

- Do not bypass login, CAPTCHA, paywalls, or non-public data.
- Facebook is not a general search source.
- Default output must be reviewable and exportable.

