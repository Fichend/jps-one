# Deployment

## Pre-flight

1. Backup live code.
2. Backup `.env`.
3. Backup databases and uploads.
4. Backup Nginx and systemd configs.
5. Run backend tests in conda `ai-hunter`.
6. Run frontend build.

## Local Checks

```bash
cd backend
conda run -n ai-hunter python -m pytest
conda run -n ai-hunter python -m compileall .

cd ../frontend
npm run build
```

## Post-deploy Checks

```text
https://jps-one.com
/api/v1/health
/api/v1/automation/status
/api/v1/jps-one/framework/status
```

Never overwrite `API_ACCESS_TOKEN` during upload.

