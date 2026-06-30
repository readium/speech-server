#!/usr/bin/env bash
set -euo pipefail

# Only fail on genuinely required vars (api key when auth is enabled)
if [[ "${API_KEY_ENABLED:-false}" == "true" && -z "${API_KEY:-}" ]]; then
  echo "ERROR: API_KEY must be set when API_KEY_ENABLED=true" >&2
  exit 1
fi

if [[ "${RELOAD:-false}" == "true" ]]; then
  exec uvicorn app.main:app \
    --host "${HOST:-0.0.0.0}" \
    --port "${PORT:-8000}" \
    --reload \
    --timeout-graceful-shutdown 3
else
  exec uvicorn app.main:app \
    --host "${HOST:-0.0.0.0}" \
    --port "${PORT:-8000}" \
    --workers "${WORKERS:-1}" \
    --timeout-graceful-shutdown 5
fi
