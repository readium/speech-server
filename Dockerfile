# syntax=docker/dockerfile:1

# ── Stage 1: install dependencies ─────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app/ ./app/

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
# Same base as builder so .venv Python symlinks resolve correctly.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --system --create-home --uid 1001 appuser

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/app  /app/app
COPY scripts/ /app/scripts/

RUN chmod +x /app/scripts/entrypoint.sh \
    && mkdir -p /app/assets/weights /app/assets/voices \
    && chown -R appuser:appuser /app

ENV PATH="/app/.venv/bin:$PATH"

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')"

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
