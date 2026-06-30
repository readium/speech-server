DC     = docker compose -f docker-compose.yml -f docker-compose.dev.yml
DC_RUN = $(DC) run --rm --no-deps app

.PHONY: build dev-docker dev-docker-build test-docker lint-docker fmt-docker typecheck-docker ci-docker \
        logs start run stop clean configure \
        sync test lint fmt typecheck ci

# ── Docker (primary workflow) ─────────────────────────────────────────────────
build:
	docker compose build

dev-docker:
	$(DC) up

dev-docker-build:
	$(DC) up --build

test-docker:
	$(DC_RUN) pytest -m 'not integration and not slow' -v

test-integration-docker:
	$(DC_RUN) pytest -m integration -v

lint-docker:
	$(DC_RUN) ruff check app/ tests/

fmt-docker:
	$(DC_RUN) ruff format app/ tests/

fmt-check-docker:
	$(DC_RUN) ruff format --check app/ tests/

typecheck-docker:
	$(DC_RUN) mypy app/

ci-docker: lint-docker fmt-check-docker typecheck-docker test-docker

logs:
	docker compose logs -f app

start:
	docker compose up -d

run: start

stop:
	docker compose down

configure:
	bash scripts/configure.sh

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete 2>/dev/null || true

# ── Local fallback (requires uv + dev deps installed locally) ─────────────────
sync:
	uv sync --dev

test:
	uv run pytest -m 'not integration and not slow' -v

lint:
	uv run ruff check app/ tests/

fmt:
	uv run ruff format app/ tests/

typecheck:
	uv run mypy app/

ci: lint fmt typecheck test
