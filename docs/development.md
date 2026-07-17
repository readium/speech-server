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
2. Declare `id`, `supported_languages`, `default_quality`, and `default_controls` as class variables
3. If voices come from a JSON file, reuse `app/providers/voice_loading.py` (`VoiceEntry`,
   `resolve_install_languages`, `build_voice`) — the same install-mode bounding and
   quality/controls merge PocketTTS uses, so it doesn't get reimplemented per provider
4. Implement `_all_voices()` and `synthesize()`
5. Register in `app/main.py` `_build_registry()`

No changes to routes, synthesizer, or voice catalog. Language filtering, quality/controls
merging, and circuit-breaking are inherited automatically from the base class and core layer.

## Architecture

```
Client
  └─ POST /synthesize
       └─ Synthesizer
            ├─ validate text length + content
            ├─ resolve voice identifier → (provider, Voice)  (VoiceCatalog)
            ├─ circuit breaker check  ← per-provider, 503 fast if open
            ├─ provider.synthesize()  ← runs in thread pool, bounded by semaphore
            │    └─ TTSModel.generate_audio()  — CPU inference
            └─ encode PCM → mp3/opus  (ffmpeg driver)  or  wrap → wav (default)
```

- Routes are `async`; all CPU-bound inference runs off the event loop via `anyio.to_thread.run_sync`
- A semaphore (`MAX_CONCURRENT_SYNTHESES`) prevents model thrashing under concurrent load
- A per-provider circuit breaker (`CIRCUIT_BREAKER_*`) fails fast instead of repeatedly hitting a broken provider
- Model throughput scales by adding worker processes (`WORKERS`), not threads
- Model weights live in a named Docker volume — downloaded once, instant on every subsequent start
