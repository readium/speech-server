DC     = docker compose -f docker-compose.yml -f docker-compose.dev.yml
DC_RUN = $(DC) run --rm --no-deps app

.DEFAULT_GOAL := help

.PHONY: help build dev-docker dev-docker-build test-docker test-integration-docker \
        lint-docker fmt-docker fmt-check-docker typecheck-docker ci-docker \
        logs start run stop clean configure prune-models prune-models-apply \
        sync test lint fmt typecheck ci

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-24s\033[0m %s\n", $$1, $$2}'

# ── Docker (primary workflow) ─────────────────────────────────────────────────
build: ## Build the docker image
	docker compose build

dev-docker: ## Run the dev stack in the foreground (docker)
	$(DC) up

dev-docker-build: ## Rebuild then run the dev stack (docker)
	$(DC) up --build

test-docker: ## Run unit/route tests (docker)
	$(DC_RUN) pytest -m 'not integration and not slow' -v

test-integration-docker: ## Run integration tests (docker)
	$(DC_RUN) pytest -m integration -v

lint-docker: ## Run ruff check (docker)
	$(DC_RUN) ruff check app/ tests/

fmt-docker: ## Run ruff format (docker)
	$(DC_RUN) ruff format app/ tests/

fmt-check-docker: ## Check ruff formatting without writing (docker)
	$(DC_RUN) ruff format --check app/ tests/

typecheck-docker: ## Run mypy (docker)
	$(DC_RUN) mypy app/

ci-docker: lint-docker fmt-check-docker typecheck-docker test-docker ## Run full CI suite (docker)

logs: ## Tail the app container logs
	docker compose logs -f app

start: ## Start the stack with nginx reverse proxy in front (background)
	docker compose --profile nginx up -d

run: start ## Alias for start

stop: ## Stop the stack
	docker compose --profile nginx down

configure: ## Run the interactive setup script
	bash scripts/configure.sh

prune-models: ## Report weight files that don't match the current env config (dry-run)
	docker compose exec app python scripts/prune_weights.py

prune-models-apply: ## Delete weight files that don't match the current env config (frees disk)
	docker compose exec app python scripts/prune_weights.py --apply

clean: ## Remove __pycache__ and .pyc files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete 2>/dev/null || true

# ── Local fallback (requires uv + dev deps installed locally) ─────────────────
sync: ## Install/sync dev dependencies locally (uv)
	uv sync --dev

test: ## Run unit/route tests locally (uv)
	uv run pytest -m 'not integration and not slow' -v

lint: ## Run ruff check locally (uv)
	uv run ruff check app/ tests/

fmt: ## Run ruff format locally (uv)
	uv run ruff format app/ tests/

typecheck: ## Run mypy locally (uv)
	uv run mypy app/

ci: lint fmt typecheck test ## Run full CI suite locally (uv)
