# GitHub synchronization and EC2 deployment

## Source of truth

- GitHub repository: `Fichend/jps-one`
- Production branch: `main`
- Long-lived local working copy: `/Users/skylerfei/codex/jps-one`
- EC2 import/staging copy: `/Users/skylerfei/Downloads/jps-one /jps-one-live`
- EC2 releases: `/opt/jps-one/releases/<commit-sha>`
- Production environment file: `/opt/jps-one/shared/backend.env`
- Docker Compose project: `ai-hunter` (keeps the existing named volumes)

Do not edit application source directly on EC2. Create a feature branch locally, open a pull request, and merge it after CI passes.

## Local synchronization

`scripts/safe-sync-main.sh` fetches `origin/main` and fast-forwards only when:

1. the current branch is `main`;
2. the working tree is clean; and
3. local `main` has not diverged from GitHub.

The macOS LaunchAgent template in `deploy/macos/` runs the script every five minutes. Install a copy of the helper at `~/Library/Application Support/JPS-One/safe-sync-main.sh` so macOS LaunchAgent can start it outside the Downloads privacy boundary. It never commits, pushes, stashes, resets, or overwrites local work.

## CI

`.github/workflows/ci.yml` validates backend compilation and stable core tests, builds the frontend, and rejects tracked runtime data or high-confidence credential patterns.

The full historical backend suite is not yet a release gate because the SMTP-provider and API-authentication tests still need migration.

## Production deployment

Production deployment is disabled until the repository variable `EC2_DEPLOY_ENABLED` is set to `true` and these Actions secrets exist:

- `EC2_HOST`
- `EC2_USER`
- `EC2_SSH_KEY`
- `EC2_KNOWN_HOSTS`

After activation, every merge to `main` uploads an immutable release directory, reuses the server-only environment file and existing Docker volumes, builds the containers, checks `/api/v1/health`, and rolls back to the previous release if verification fails.
