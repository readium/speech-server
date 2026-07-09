# Readium Speech Server

> [!IMPORTANT]
> Readium Speech Server is a proof of concept exploring how TTS (Text to Speech) models can be either hosted or proxied through a single Web service.
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

Server: `http://localhost:8000` · Interactive docs: `http://localhost:8000/docs` · Demo: `http://localhost:8000/demo`

**Quick test:**
```bash
curl -s -X POST http://localhost:8000/v1/synthesize \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hello world","voice":"urn:readium:tts:pocket:en-alba"}' \
  -o /tmp/speech.mp3 && open /tmp/speech.mp3
```

> **First start** downloads the selected language models (~240 MB each) into a persistent Docker volume. Every restart after that is instant — models are already cached.

---

## Documentation

- [API Reference](docs/API.md)
- [Voices](docs/voices.md)
- [Configuration](docs/configuration.md)
- [Development](docs/development.md)

---

## Related projects

- [readium/speech](https://github.com/readium/speech) — TypeScript read-aloud library this server is designed to pair with
- [HadrienGardeur/web-speech-recommended-voices](https://github.com/HadrienGardeur/web-speech-recommended-voices) — voice catalog schema reference (CC0)
- [pocket-tts](https://github.com/pocket-tts/pocket-tts) — the underlying CPU TTS engine
