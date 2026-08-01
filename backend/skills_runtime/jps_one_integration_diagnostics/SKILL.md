---
name: jps_one_integration_diagnostics
description: Diagnose JPS One external integrations and explain usable capability boundaries.
---

# JPS One Integration Diagnostics

Use this skill for Meta, WhatsApp, Tavily, Jina, SMTP/IMAP, and model diagnostics.

Checks:

- Provider configured or not.
- Credentials present without exposing values.
- Required permissions.
- Last successful test.
- Missing setup.
- Practical capability boundary.
- Next action.

Important Meta boundary:

- OAuth success does not mean Facebook customer search is available.
- Page count `0` means authorized Page workflows are not ready.
- Lead Ads retrieval depends on authorized forms and assets.

