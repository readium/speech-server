# Readium Speech Server

> [!IMPORTANT]
> Readium Speech Server is a proof of concept exploring how TTTS (Text to Speech) models can be either hosted or proxied through a single Web service.
> 
> This project is not currently production-ready and it's missing key features such as caching or long term storage options.

A remote text-to-speech HTTP service for the [Readium](https://readium.org) ecosystem. Exposes a uniform API for listing voices and synthesizing speech, backed by open-source models and proxied commercial models.

Designed to pair with [Readium Speech](https://github.com/readium/speech), Readium toolkits or any other application.

---

## Overview

| | |
|---|---|
| **API** | `GET /voices` · `POST /synthesize` |
| **Providers** | PocketTTS · ElevenLabs (planned) |
| **Languages** | English · French · Italian · German · Spanish · Portuguese |
| **Formats** | MP3 · WAV · Opus |
| **Word boundaries** | Planned (ElevenLabs) |
| **Deployment** | Docker · CPU-only · Single named volume for model weights |

---

## Quick start

You need **Docker** — nothing else. No Python, no PyTorch, no model files on your machine.

```bash
make configure        # interactive setup → writes .env
make build            # build the image (~2 min)
make dev-docker       # start server — downloads models on first run
```

Server: `http://localhost:8000`  
Interactive API docs: `http://localhost:8000/docs`

**Quick test — synthesize and play:**
```bash
curl -s -X POST http://localhost:8000/v1/synthesize \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hello world","voice":"urn:readium:tts:pocket:en-alba"}' \
  -o /tmp/speech.mp3 && open /tmp/speech.mp3
```

> **First start** downloads the selected language models (~240 MB each) into a persistent Docker volume. Every restart after that is instant — models are already cached.

**Browser demo:** `http://localhost:8000/demo` (or `:8080` behind nginx in production). A single static page, served same-origin by the app itself — no build step, no extra dependency. Lets you pick a voice (with language/provider/gender filters), type an utterance, and hear it synthesized in-browser, with the equivalent `curl` command and raw response shown alongside. A "Developer tools" panel exposes the rest of the request body (format, bitrate, speed, pitch, sample rate, SSML, word-boundary mode) — fields confirmed to actually affect output are called out separately from ones the current provider silently ignores (see [`docs/API.md`](docs/API.md) "Not implemented").

### Production

```bash
make start   # detached — docker compose --profile nginx up -d
make stop    # stop all containers
make logs    # tail app logs (nginx logs: docker compose logs -f nginx)
```

Reachable at `http://<DOMAIN>:8080` — nginx publishes host port `8080`, plain HTTP only, no TLS termination. Put a TLS-terminating load balancer in front for a real deployment.

`restart: unless-stopped` is set on the **app** container only; the nginx sidecar has no restart policy (`docker-compose.yml`), so it won't come back on its own after a crash or host reboot.

nginx also rate-limits `/v1/synthesize` (2 req/s, burst 4) and caps connections per IP — a `503` from behind nginx under load is a plain nginx error page, not the app's Problem Details JSON.

---

## Setup wizard

`make configure` opens an interactive wizard. It handles both first-time setup and ongoing management:

```
Readium Speech Server

  Current: languages=en  workers=1

  1) Show full config
  2) Add a language
  3) Remove a language
  4) Change workers
  5) Update HF token
  6) First-time setup (re-run / overwrite)
  7) Reset
  q) Quit
```

Adding a language updates `.env` in place — only the new model is downloaded on next restart. Removing a language preserves the model files in the Docker volume; disk is reclaimed only if you choose to purge the volume.

> **Production by default.** First-time setup writes `APP_ENV=production` and prompts for `DOMAIN` (required in production — FastAPI uses it for `TrustedHostMiddleware` and the OpenAPI base URL). `make start` puts nginx in front of the app as a reverse proxy; the app container has no published port, so it's only reachable through nginx. For local dev, edit `.env` and set `APP_ENV=development` (`DOMAIN` becomes optional again), and use `make dev-docker` instead — it exposes `:8000` directly with no nginx.

---

## Voices

156 voices across 7 language variants (26 voice identities × 6 languages). Every voice is available in every language — `alba` speaking English, `alba` speaking French, `alba` speaking German, etc. Only languages listed in `LANGUAGES` are loaded at startup (~240 MB RAM per language per worker).

The 26 voice identities, sourced from [kyutai/tts-voices](https://huggingface.co/kyutai/tts-voices):

| Voice | Gender | Origin |
|---|---|---|
| alba | female | Alba MacKenna (CC BY 4.0) |
| anna, vera, fantine, charles, paul, eponine, azelma, george, mary, jane, michael, eve | mixed | VCTK dataset (CC BY 4.0) |
| bill_boerst, peter_yearsley, stuart_bell, caro_davy | mixed | Voice Zero / LibriVox (CC0) |
| marius, javert | male | Voice donations (CC0) |
| cosette | female | Expresso dataset (CC BY-NC 4.0) |
| jean | male | EARS dataset (CC BY-NC 4.0) |
| estelle | female | Unmute production voices |
| giovanni, lola, juergen, rafael | mixed | Kyutai (language reference voices) |

Voice URIs are language-scoped — the same speaker in different languages gets a distinct URI:

```
urn:readium:tts:pocket:en-alba    # Alba speaking English
urn:readium:tts:pocket:fr-alba    # Alba speaking French
urn:readium:tts:pocket:de-alba    # Alba speaking German
```

Supported language codes: `en`, `fr`, `it`, `de`, `es`, `pt` — derived directly from PocketTTS model names.

> **How it works:** PocketTTS pre-computes voice embeddings for every voice × language combination (stored as `.safetensors` files in `kyutai/pocket-tts-without-voice-cloning`). The voice sample is encoded once at model-load time — no per-request cloning overhead.

---

## API reference

### Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/healthz` | Liveness — 200 when the process is running |
| `GET` | `/readyz` | Readiness — 503 until models are loaded and ffmpeg is available |

### Voices

```
GET /v1/voices
GET /v1/voices?language=fr
GET /v1/voices?provider=pocket
GET /v1/voices?offset=0&limit=20
```

Returns an array of voice objects. Null-valued optional fields are omitted. Each voice includes a `boundary` field indicating whether that provider supports word-level timing marks.

**Pagination query params:**

| Param | Type | Description |
|---|---|---|
| `language` | string | Filter by BCP-47 language prefix (e.g. `en`, `fr`) |
| `provider` | string | Filter by provider id (e.g. `pocket`) |
| `offset` | int ≥ 0 | Voices to skip (default: 0) |
| `limit` | int ≥ 1 | Max voices to return (default: all) |

**Response headers:**

| Header | Description |
|---|---|
| `X-Total-Count` | Total matching voices before pagination |
| `X-Offset` | Applied offset |
| `X-Limit` | Applied limit (omitted when no limit set) |

### Synthesize

```
POST /v1/synthesize
Content-Type: application/json
```

**Minimal request — returns binary MP3:**

```json
{
  "text": "Hello, world!",
  "voice": "urn:readium:tts:pocket:en-alba"
}
```

**Full request:**

```json
{
  "id": "urn:uuid:019f178c-cc7c-7bb3-a39b-d185f43d3cc4",
  "text": "Ceci est un test.",
  "language": "fr",
  "voice": "urn:readium:tts:pocket:fr-estelle",
  "ssml": false,
  "prev_utterance": "La nuit était sombre.",
  "next_utterance": "La pièce était froide.",
  "publication_id": "urn:isbn:9780000000000",
  "boundary": false,
  "output": {
    "format": "mp3",
    "bitrate": 64,
    "speed": 1.0,
    "pitch": null
  }
}
```

**Response (default, `boundary: false`):**

Binary audio with `Content-Type: audio/mpeg` (or `audio/wav`, `audio/ogg`).

**Response (`boundary: true`):**

```json
{
  "audio": "<base64-encoded audio>",
  "format": "mp3",
  "boundaries": [
    { "name": "word", "charIndex": 0,  "charLength": 5,  "elapsedTime": 0.0  },
    { "name": "word", "charIndex": 6,  "charLength": 3,  "elapsedTime": 0.38 }
  ]
}
```

`boundaries` is always `null` today — no provider populates timing marks yet. Every voice reports `boundary: false`; check it before setting `boundary: true` to skip a wasted round trip.

Word boundary fields mirror the [Web Speech API `boundary` event](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisUtterance/boundary_event): `charIndex` and `charLength` index into the original `text`; `elapsedTime` is seconds from audio start.

**Output formats:**

| `format` | `Content-Type` | Notes |
|---|---|---|
| `mp3` | `audio/mpeg` | Default |
| `wav` | `audio/wav` | No transcoding — fastest |
| `opus` | `audio/ogg` | Smallest file size |

**Errors:**

All errors are [RFC 9457 Problem Details](https://www.rfc-editor.org/rfc/rfc9457) (`Content-Type: application/problem+json`):

```json
{ "type": "https://readium.org/speech-server/error#voice_not_found", "title": "Voice Not Found", "status": 404, "detail": "Voice 'urn:unknown' not found." }
```

| Status | Type suffix | Cause |
|---|---|---|
| 400 | `validation_failed` | Empty or whitespace text |
| 404 | `voice_not_found` | Voice URI not registered |
| 413 | `payload_too_large` | Text exceeds `MAX_TEXT_LENGTH` (default 2000 chars) |
| 422 | `validation_failed` | Request schema invalid (Pydantic detail) |
| 502 | `provider_error` | Provider or ffmpeg failed |
| 503 | `service_not_ready` | `/readyz` only — models not loaded, ffmpeg missing, or a provider unhealthy |

Behind production nginx, a `503`/`429` can also come from nginx's own rate/connection limits — those are plain nginx error pages, not `application/problem+json`.

Full field-by-field reference, including every request/response field and what's not implemented yet: [`docs/API.md`](docs/API.md).

---

## Configuration

Run `make configure` to generate `.env`, or run `bash scripts/configure.sh` directly.

| Variable | Default | Description |
|---|---|---|
| `LANGUAGES` | `en` | Comma-separated BCP-47 language codes to load. Supported: `en fr it de es pt` |
| `HF_TOKEN` | _(empty)_ | HuggingFace token. Optional — prevents rate-limiting on first-run model downloads |
| `WORKERS` | `1` | Uvicorn worker processes. Each loads a full copy of every active language model |
| `MAX_CONCURRENT_SYNTHESES` | `2` | Max parallel CPU inference jobs per worker |
| `API_KEY_ENABLED` | `false` | Reserved — validated at startup but **not yet enforced** on any route |
| `API_KEY` | _(empty)_ | Reserved, same caveat |
| `LOG_LEVEL` | `INFO` | `DEBUG` · `INFO` · `WARNING` · `ERROR` |
| `PORT` | `8000` | Listen port |
| `MAX_TEXT_LENGTH` | `2000` | Maximum characters per synthesis request |
| `FFMPEG_BIN` | `ffmpeg` | Path to ffmpeg binary (bundled in the Docker image) |
| `POCKET_DEFAULT_VOICE` | `alba` | Default voice when none is specified |
| `ENABLED_PROVIDERS` | `pocket` | Comma-separated provider ids to register at startup. Only `pocket` exists today |
| `DEFAULT_PROVIDER` | `pocket` | Must be one of `ENABLED_PROVIDERS` — validated at startup |
| `DOMAIN` | _(empty)_ | Required when `APP_ENV=production` — used for `TrustedHostMiddleware` and nginx `server_name` |

**RAM estimate:** `WORKERS × active languages × ~240 MB`

Example: 2 workers, English + French = `2 × 2 × 240 MB ≈ 960 MB`

---

## Development

### Commands

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

### Running tests locally

The fast suite requires no models and no ffmpeg — everything is mocked:

```bash
uv sync
uv run pytest tests/ -m 'not integration and not slow' -v
```

### Adding a provider

1. Create `app/providers/<name>.py` implementing `TTSProvider`
2. Declare `id`, `supported_languages`, and `supports_boundaries` as class variables
3. Implement `_all_voices()` and `synthesize()`
4. Register in `app/main.py` `_build_registry()`

No changes to routes, synthesizer, or voice catalog. Language filtering and boundary capability are inherited automatically from the base class.

---

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

---


## Related projects

- [readium/speech](https://github.com/readium/speech) — TypeScript read-aloud library this server is designed to pair with
- [HadrienGardeur/web-speech-recommended-voices](https://github.com/HadrienGardeur/web-speech-recommended-voices) — voice catalog schema reference (CC0)
- [pocket-tts](https://github.com/pocket-tts/pocket-tts) — the underlying CPU TTS engine
