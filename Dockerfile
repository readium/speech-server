# syntax=docker/dockerfile:1

# ── Stage 1: install dependencies ─────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY app/ ./app/
COPY tests/ ./tests/

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --system --create-home --uid 1001 appuser \
    && mkdir -p /weights \
    && chown -R appuser:appuser /weights /home/appuser

WORKDIR /app

COPY --from=builder /app/.venv          /app/.venv
COPY --from=builder /app/app            /app/app
COPY --from=builder /app/pyproject.toml /app/pyproject.toml
COPY scripts/entrypoint.sh /app/scripts/entrypoint.sh

RUN chmod +x /app/scripts/entrypoint.sh \
    && chown -R appuser:appuser /app

# HF_HOME=/weights — pocket-tts downloads models here (persisted via named volume)
ENV PATH="/app/.venv/bin:$PATH" \
    HF_HOME=/weights

USER appuser

EXPOSE 8000

# start_period covers first-run model downloads (~240 MB per language)
HEALTHCHECK --interval=30s --timeout=5s --start-period=300s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')"

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
