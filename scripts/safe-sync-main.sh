#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${JPS_ONE_REPO:-/Users/skylerfei/codex/jps-one}"
LOG_PREFIX="[jps-one-sync]"

cd "$REPO_DIR"

if [[ "$(git branch --show-current)" != "main" ]]; then
  echo "$LOG_PREFIX skipped: current branch is not main"
  exit 0
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "$LOG_PREFIX skipped: local changes are present"
  exit 0
fi

git fetch --prune origin main

LOCAL_SHA="$(git rev-parse main)"
REMOTE_SHA="$(git rev-parse origin/main)"
BASE_SHA="$(git merge-base main origin/main)"

if [[ "$LOCAL_SHA" == "$REMOTE_SHA" ]]; then
  echo "$LOG_PREFIX already current"
elif [[ "$LOCAL_SHA" == "$BASE_SHA" ]]; then
  git merge --ff-only origin/main
  echo "$LOG_PREFIX updated to $REMOTE_SHA"
else
  echo "$LOG_PREFIX skipped: main has diverged from origin/main"
  exit 2
fi
