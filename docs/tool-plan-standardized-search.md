# Tool Plan Standardized Search

This document records the production search semantics used by Hunt Copilot.

## Core Rule

Tool Plan first discovers real customer entities, then enriches contact and social evidence, then merges, scores and ranks the candidate pool.

Social/contact fields such as Instagram, Facebook, email and phone are enrichment targets. They increase coverage score when found, but they are not used as query pollution terms and do not directly delete relevant companies.

## Execution Flow

1. Compile a deterministic plan from the confirmed strategy.
2. Generate entity discovery queries from region, customer type, product keywords and local-language expansions.
3. Run only Tavily Web and Google Maps in the discovery/search phase.
4. Merge evidence into `candidate_pool` and rank real customer entities first.
5. Run Tavily Extract/Crawl and Apify Instagram/Facebook as candidate enrichment by company identity, not as broad social discovery.
6. If Tool Plan under-fills the requested candidate pool, run bounded legacy Web/Maps recall backfill.
7. Deep extraction consumes the ranked `candidate_pool` in order and preserves candidate evidence such as social links, email and phone.
8. Rank by JPS score, business relevance, source evidence and preferred-field coverage.
9. Display Top N as sorted selected candidates while retaining the full candidate pool.

## Status Semantics

- `qualified_recommended`: Top N candidate with selected preferred fields covered.
- `ranked_candidate`: Top N candidate with good relevance but fields still worth completing.
- `backup_candidate`: retained backup candidate after Top N.
- `needs_enrichment`: lower-ranked candidate that needs more evidence.
- `low_relevance_social`: social-only row that lacks business/product anchors.
- `excluded_by_rule`: candidate strongly conflicts with business exclusions.

## Determinism

Similar confirmed strategies should produce the same ordered query list and tool order. This keeps repeated tasks comparable and makes result differences easier to audit.
