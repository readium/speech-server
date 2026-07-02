#!/usr/bin/env bash
set -euo pipefail

# Only fail on genuinely required vars (api key when auth is enabled)
if [[ "${API_KEY_ENABLED:-false}" == "true" && -z "${API_KEY:-}" ]]; then
  echo "ERROR: API_KEY must be set when API_KEY_ENABLED=true" >&2
  exit 1
fi

# Safe to trust forwarded headers unconditionally: in production the app has
# no published host port (only reachable via the speech-net bridge from the
# nginx sidecar), so nothing outside Docker can spoof X-Forwarded-For/Host.
# In dev (port published directly, no nginx) these headers are simply absent,
# so this is a no-op and uvicorn falls back to the real socket peer.
PROXY_FLAGS=(--proxy-headers --forwarded-allow-ips="*")

if [[ "${RELOAD:-false}" == "true" ]]; then
  exec uvicorn app.main:app \
    --host "${HOST:-0.0.0.0}" \
    --port "${PORT:-8000}" \
    "${PROXY_FLAGS[@]}" \
    --reload \
    --timeout-graceful-shutdown 3
else
  exec uvicorn app.main:app \
    --host "${HOST:-0.0.0.0}" \
    --port "${PORT:-8000}" \
    "${PROXY_FLAGS[@]}" \
    --workers "${WORKERS:-1}" \
    --timeout-graceful-shutdown 5
fi
