# Development

## Commands

| Command | Description |
|---|---|
| `make configure` | Run setup wizard |
| `make build` | Build Docker image |
| `make dev-docker` | Start dev server with hot-reload |
| `make dev-docker-build` | Build then start |
| `make start` | Start production stack (detached) |
| `make stop` | Stop containers |
| `make logs` | Tail app logs |
| `make test-docker` | Fast test suite — no models needed |
| `make test-integration-docker` | Integration tests — requires models in volume |
| `make ci-docker` | Lint + format check + typecheck + tests |
| `make lint-docker` | `ruff check` |
| `make fmt-docker` | `ruff format` |
| `make typecheck-docker` | `mypy` |
| `make test` | Fast tests via `uv` (no Docker) |
| `make ci` | Full local CI |
| `make clean` | Remove `__pycache__` and `.pyc` files |

## Running tests locally

The fast suite requires no models and no ffmpeg — everything is mocked:

```bash
uv sync
uv run pytest tests/ -m 'not integration and not slow' -v
```

## Adding a provider

1. Create `app/providers/<name>.py` implementing `TTSProvider`
2. Declare `id`, `supported_languages`, and `supports_boundaries` as class variables
3. Implement `_all_voices()` and `synthesize()`
4. Register in `app/main.py` `_build_registry()`

No changes to routes, synthesizer, or voice catalog. Language filtering and boundary capability are inherited automatically from the base class.

## Architecture

```
Client
  └─ POST /v1/synthesize
       └─ Synthesizer
            ├─ validate text length + content
            ├─ resolve voiceURI → (provider, voiceURI)  (VoiceCatalog)
            ├─ provider.synthesize()  ← runs in thread pool, bounded by semaphore
            │    └─ TTSModel.generate_audio()  — CPU inference
            └─ encode PCM → mp3/opus  (ffmpeg driver)  or  wrap → wav
```

- Routes are `async`; all CPU-bound inference runs off the event loop via `anyio.to_thread.run_sync`
- A semaphore (`MAX_CONCURRENT_SYNTHESES`) prevents model thrashing under concurrent load
- Model throughput scales by adding worker processes (`WORKERS`), not threads
- Model weights live in a named Docker volume — downloaded once, instant on every subsequent start
