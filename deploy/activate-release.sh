#!/usr/bin/env bash
set -euo pipefail

DEPLOY_SHA="${1:?commit SHA is required}"
APP_ROOT="/opt/jps-one"
RELEASE_DIR="$APP_ROOT/releases/$DEPLOY_SHA"
CURRENT_LINK="$APP_ROOT/current"
SHARED_DIR="$APP_ROOT/shared"
SHARED_ENV="$SHARED_DIR/backend.env"
LEGACY_ENV="/opt/ai-hunter/backend/.env"
COMPOSE_PROJECT="ai-hunter"
HEALTH_URL="http://127.0.0.1:8000/api/v1/health"

if [[ ! -f "$RELEASE_DIR/docker-compose.yml" ]]; then
  echo "Release is incomplete: $RELEASE_DIR"
  exit 1
fi

mkdir -p "$SHARED_DIR"
if [[ ! -f "$SHARED_ENV" ]]; then
  if [[ ! -f "$LEGACY_ENV" ]]; then
    echo "Missing production environment file: $SHARED_ENV"
    exit 1
  fi
  install -m 600 "$LEGACY_ENV" "$SHARED_ENV"
fi

ln -sfn "$SHARED_ENV" "$RELEASE_DIR/backend/.env"
PREVIOUS_RELEASE="$(readlink "$CURRENT_LINK" 2>/dev/null || true)"
if [[ -z "$PREVIOUS_RELEASE" && -f /opt/ai-hunter/docker-compose.yml ]]; then
  PREVIOUS_RELEASE=/opt/ai-hunter
fi

activate() {
  local directory="$1"
  docker compose -p "$COMPOSE_PROJECT" -f "$directory/docker-compose.yml" up -d --build
}

healthcheck() {
  for _ in $(seq 1 30); do
    if curl --fail --silent --show-error "$HEALTH_URL" >/dev/null; then
      return 0
    fi
    sleep 2
  done
  return 1
}

if activate "$RELEASE_DIR" && healthcheck; then
  ln -sfn "$RELEASE_DIR" "$CURRENT_LINK"
  echo "Deployment successful: $DEPLOY_SHA"
  exit 0
fi

echo "Deployment failed: $DEPLOY_SHA"
if [[ -n "$PREVIOUS_RELEASE" && -f "$PREVIOUS_RELEASE/docker-compose.yml" ]]; then
  echo "Rolling back to: $PREVIOUS_RELEASE"
  activate "$PREVIOUS_RELEASE"
  healthcheck
fi
exit 1
