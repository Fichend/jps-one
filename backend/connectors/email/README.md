# Email Connector

Email connectors wrap SMTP, IMAP, readiness checks, and delivery status.

Rules:

- Keep SMTP/IMAP protocol work in connectors.
- Keep campaign strategy and approval policy in business/workflow layers.
- Never log full passwords, app passwords, or API tokens.
- First version defaults to draft + human review before sending.

