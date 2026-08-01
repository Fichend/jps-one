# Connectors

`connectors/` wraps deterministic external systems and protocol-level adapters.

Connectors should:

- Accept explicit input and return typed output.
- Hide provider-specific error handling and rate-limit behavior.
- Never make business decisions.
- Never expose secrets in logs, responses, or README files.

Connector groups:

- `search/` - Tavily, Serper, DuckDuckGo, Google Maps.
- `web_reader/` - Jina Reader, HTML fetching, contact parsing.
- `meta/` - Facebook OAuth, Page sync, Lead Ads reads, diagnostics.
- `whatsapp/` - WhatsApp Business templates, message status, webhooks.
- `email/` - SMTP, IMAP, deliverability readiness.
- `files/` - Excel, PDF, DOCX, CSV parsing.

