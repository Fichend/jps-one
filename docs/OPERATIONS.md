# Operations

Daily checks:

- Domain responds through Nginx.
- Backend health endpoint responds.
- Automation worker status is visible.
- Email queue has no unexpected backlog.
- Search source settings are present.
- Meta diagnostics explain missing permissions or assets.
- Logs do not expose secrets.

Troubleshooting order:

1. Browser error.
2. Nginx status.
3. FastAPI service status.
4. Worker status.
5. Queue database.
6. `.env` and settings store.
7. External provider diagnostics.

