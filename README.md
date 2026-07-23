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
| **API** | `GET /service` · `GET /voices` · `POST /synthesize` |
| **Providers** | [PocketTTS](docs/providers/pocket.md) (local) · [ElevenLabs](docs/providers/elevenlabs.md) (hosted) |
| **Languages** | English · French · Italian · German · Spanish · Portuguese |
| **Formats** | WAV (default) · MP3 · Opus |
| **Word boundaries** | ElevenLabs (word-level timing marks) |
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

**Live demo:** [speech-server.readium.org/demo](https://speech-server.readium.org/demo)

**Quick test:**
```bash
curl -s -X POST http://localhost:8000/synthesize \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hello world","voice":"urn:readium:tts:pocket:alba"}' \
  -o /tmp/speech.wav && open /tmp/speech.wav
```

> **First start** downloads the selected language models (~240 MB each) into a persistent Docker volume. Every restart after that is instant — models are already cached.

---

## Documentation

- [API Reference](docs/API.md)
- [Voices](docs/voices.md)
- [Configuration](docs/configuration.md)
- Providers: [PocketTTS](docs/providers/pocket.md) · [ElevenLabs](docs/providers/elevenlabs.md)
- [Development](docs/development.md)
- [Deployment](docs/deployment.md)

---

## Related projects

- [readium/speech](https://github.com/readium/speech) — TypeScript read-aloud library this server is designed to pair with
- [HadrienGardeur/web-speech-recommended-voices](https://github.com/HadrienGardeur/web-speech-recommended-voices) — voice catalog schema reference (CC0)
- [pocket-tts](https://github.com/pocket-tts/pocket-tts) — the underlying CPU TTS engine
