# Data Model

Core entities:

- Company
- Contact
- Lead
- Evidence
- Product
- PriceRule
- ProductMatch
- OutreachDraft
- Quote
- QuoteItem
- FollowUp

Principles:

- Company is not the same as Lead.
- Evidence is separate and reusable.
- Product and PriceRule are separate.
- Quotes preserve history.
- Outreach drafts require review by default.

Initial status values:

```text
new
to_review
qualified
contacted
replied
interested
quoted
following
won
lost
invalid
blacklisted
```

