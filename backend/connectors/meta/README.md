# Meta / Facebook Connector

Meta is an authorized asset connector, not a full-platform customer search connector.

Supported first-version responsibilities:

- OAuth configuration diagnostics.
- Facebook Page list sync for authorized business assets.
- Lead Ads lead retrieval when authorized objects exist.
- Permission and missing-capability reporting.

Current known boundary:

- OAuth can succeed while Page count is `0`; in that case the connector is configured but not yet operational for Page-based workflows.
- `leads_retrieval` reads Lead Ads form leads; it does not search all Facebook customers.
- Public Page content access requires separate Meta feature review and should not be assumed.

