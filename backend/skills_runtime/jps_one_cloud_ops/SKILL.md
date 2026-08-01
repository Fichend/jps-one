---
name: jps_one_cloud_ops
description: Operate and deploy JPS One on AWS EC2 without losing secrets or breaking the live domain.
---

# JPS One Cloud Ops

Use this skill for deployment, rollback, Nginx, systemd, domain, HTTPS, and health checks.

Required checks:

1. Backup live code, `.env`, databases, uploaded files, Nginx config, and systemd units.
2. Never overwrite or clear `API_ACCESS_TOKEN`.
3. Confirm `https://jps-one.com` DNS and Basic Auth behavior before and after deploy.
4. Run backend tests in `conda run -n ai-hunter`.
5. Run frontend build before upload.
6. Restart services in a controlled order.
7. Verify `/api/v1/health`, `/api/v1/automation/status`, and `/api/v1/jps-one/framework/status`.

Do not expose SSH keys, API keys, app secrets, or tokens in logs or documentation.

