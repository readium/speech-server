#!/usr/bin/env bash
set -euo pipefail

# Validate required env vars
required_vars=(HOST PORT WORKERS)
for var in "${required_vars[@]}"; do
  if [[ -z "${!var:-}" ]]; then
    echo "ERROR: Required env var $var is not set" >&2
    exit 1
  fi
done

# Phase 2+: fetch weights if not baked
# python /app/scripts/fetch_weights.py

exec uvicorn app.main:app \
  --host "${HOST}" \
  --port "${PORT}" \
  --workers "${WORKERS}"
