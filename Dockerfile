# syntax=docker/dockerfile:1

# ── Stage 1: install dependencies ─────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY app/ ./app/

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --system --create-home --uid 1001 appuser \
    && mkdir -p /weights \
    && chown -R appuser:appuser /weights /home/appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app/.venv          /app/.venv
COPY --from=builder --chown=appuser:appuser /app/app            /app/app
COPY --from=builder --chown=appuser:appuser /app/pyproject.toml /app/pyproject.toml
# entrypoint.sh + prune_weights.py both run inside the container (the latter via
# `make prune-models`); configure.sh/pocket_plan.py are host-only but harmless here.
COPY --chown=appuser:appuser scripts/ /app/scripts/

RUN chmod +x /app/scripts/entrypoint.sh

# HF_HOME=/weights — pocket-tts downloads models here (persisted via named volume)
ENV PATH="/app/.venv/bin:$PATH" \
    HF_HOME=/weights

USER appuser

EXPOSE 8000

# /readyz (not /healthz): healthy only once models are loaded, so `compose up --wait` and the
# deploy fail when the load fails. start_period covers first-run downloads (~110-220 MB/language).
HEALTHCHECK --interval=30s --timeout=5s --start-period=600s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/readyz')"

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
