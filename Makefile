.PHONY: dev sync test test-integration lint fmt typecheck build run stop clean

dev:
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

sync:
	uv sync --dev

test:
	uv run pytest -m 'not integration and not slow' -v

test-integration:
	uv run pytest -m 'integration' -v

lint:
	uv run ruff check app/ tests/

fmt:
	uv run ruff format app/ tests/

typecheck:
	uv run mypy app/

build:
	docker build -t speech-server .

run:
	docker compose up

stop:
	docker compose down 2>/dev/null || true
	-pkill -f "uvicorn app.main:app" 2>/dev/null || true

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete 2>/dev/null || true
