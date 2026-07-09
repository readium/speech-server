# API Reference

HTTP API for the Readium Speech Server: list voices, synthesize speech. Implements the [Readium Speech](https://github.com/readium/speech) `ReadiumSpeechUtterance` / `ReadiumSpeechVoice` contract plus server-specific extensions, called out below.

Base path: `/`. All bodies are `application/json` unless noted.

---

## Contents

- [Authentication](#authentication)
- [Errors](#errors)
- [Health](#health)
- [`GET /voices`](#get-v1voices)
- [`POST /synthesize`](#post-v1synthesize)
- [Not implemented](#not-implemented)

---

## Authentication

None enforced today. `API_KEY_ENABLED` / `API_KEY` exist in [configuration](configuration.md) but no middleware checks them yet — every route is open regardless of the setting. Don't rely on it.

In production, nginx sits in front (see [configuration](configuration.md#production-vs-development)) and rate-limits `/synthesize` (2 req/s, burst 4) plus per-IP connection caps — unrelated to app auth, but the only request throttling that exists.

---

## Errors

All errors are [RFC 9457 Problem Details](https://www.rfc-editor.org/rfc/rfc9457) (`Content-Type: application/problem+json`):

```json
{
  "type": "https://readium.org/speech-server/error#voice_not_found",
  "title": "Voice Not Found",
  "status": 404,
  "detail": "Voice 'urn:unknown' not found.",
  "instance": "urn:uuid:3f7a2e10-..."
}
```

`instance` is the request's `X-Request-Id` (also returned as a response header on every request, success or failure — use it to correlate with server logs).

Pydantic schema errors (`422`) additionally carry an `errors` array (raw Pydantic error list).

| Status | `type` suffix | Raised when |
|---|---|---|
| 400 | `validation_failed` | `text` is empty or whitespace-only |
| 404 | `voice_not_found` | `voice` URI not in the registry |
| 413 | `payload_too_large` | `text` exceeds `MAX_TEXT_LENGTH` |
| 422 | `validation_failed` | Request body fails schema validation (wrong type, missing required field, invalid enum value) |
| 502 | `provider_error` | Provider or ffmpeg failed (bad voice state, generation error, encode failure) |
| 503 | `service_not_ready` | `/readyz` only — models not loaded, ffmpeg missing, or a provider reports unhealthy |

`unsupported_format` (415), `rate_limited` (429), and `provider_timeout` (504) are declared in `app/api/errors.py` for future providers but no current code path raises them — a `429`/`503` seen in production is nginx's own rate/connection limit, a plain nginx error page, not this JSON shape.

---

## Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/healthz` | Liveness. Always `200 {"status": "ok"}` once the process is up. |
| `GET` | `/readyz` | Readiness. `200` once models are loaded, ffmpeg is on `PATH`, and every registered provider reports healthy; `503` otherwise. |

---

## `GET /v1/voices`

```
GET /voices
GET /voices?language=fr
GET /voices?provider=pocket
GET /voices?offset=0&limit=20
```

| Param | Type | Default | Description |
|---|---|---|---|
| `language` | string | — | Filter by BCP-47 language prefix (`en`, `fr`, ...) |
| `provider` | string | — | Filter by provider id (`pocket`) |
| `offset` | int ≥ 0 | `0` | Voices to skip |
| `limit` | int ≥ 1 | none | Max voices to return |

Response: `200`, `Voice[]`. Null-valued optional fields are omitted (`response_model_exclude_none`).

Headers: `X-Total-Count` (matches before pagination), `X-Offset`, `X-Limit` (omitted when `limit` unset).

### `Voice`

```json
{
  "source": "json",
  "label": "Alba (English)",
  "name": "pocket-en-alba",
  "originalName": "alba",
  "voiceURI": "urn:readium:tts:pocket:en-alba",
  "language": "en",
  "gender": "female",
  "quality": "normal",
  "pitchControl": false,
  "preloaded": true,
  "provider": "pocket",
  "engineVoiceId": "alba",
  "sampleRate": 24000,
  "mimeTypes": ["audio/mpeg", "audio/wav", "audio/ogg"],
  "boundary": false
}
```

**`ReadiumSpeechVoice`-aligned:**

| Field | Type | Notes |
|---|---|---|
| `source` | `"json" \| "browser"` | Always `"json"` — every voice here is server-hosted |
| `label` | string | Display name |
| `name` | string | Unique identifier within the Readium ecosystem |
| `originalName` | string | Raw engine voice id |
| `voiceURI` | string | Send this as `SynthesizeRequest.voice` |
| `language` | string | BCP-47 |
| `localizedName`, `altNames`, `altLanguage`, `otherLanguages`, `multiLingual`, `children`, `nativeID`, `note` | — | Not populated by any current provider — always omitted |
| `gender` | `"male" \| "female" \| "neutral" \| null` | |
| `quality` | `"veryLow"…"veryHigh" \| null` | PocketTTS voices are always `"normal"` |
| `pitchControl` | bool | `true` = provider accepts `output.pitch`. PocketTTS = `false` |
| `pitch`, `rate` | float or null | Recommended defaults, if the engine specifies any — currently always `null` |
| `preloaded` | bool | `true` = model weights already resident, ready without a cold-start delay |

**Server extensions (not in `ReadiumSpeechVoice`):**

| Field | Type | Notes |
|---|---|---|
| `provider` | string | Backend serving this voice — `"pocket"` today |
| `engineVoiceId` | string | Opaque, internal — not for client use |
| `sampleRate` | int | Native PCM rate in Hz (`24000` for PocketTTS) |
| `mimeTypes` | string[] | Always `["audio/mpeg", "audio/wav", "audio/ogg"]` |
| `boundary` | bool | `true` = this voice's provider fills `boundaries` on synthesis. Check before setting `boundary: true` on the request — a `false` voice always gets `boundaries: null` back |

---

## `POST /synthesize`

```json
{
  "id": "urn:uuid:019f178c-cc7c-7bb3-a39b-d185f43d3cc4",
  "text": "Ceci est un test.",
  "ssml": false,
  "language": "fr",
  "voice": "urn:readium:tts:pocket:fr-estelle",
  "prev_utterance": "La nuit était sombre.",
  "next_utterance": "La pièce était froide.",
  "publication_id": "urn:isbn:9780000000000",
  "boundary": true,
  "output": {
    "format": "mp3",
    "bitrate": 64,
    "sample_rate": null,
    "speed": 1.0,
    "pitch": null
  }
}
```

Only `text` and `voice` are required; everything else defaults as shown.

| Field | Type | Default | Notes |
|---|---|---|---|
| `id` | string \| null | `null` | Client-generated UUID v7 URN. Parsed, logged, **not otherwise used** — no caching or idempotency yet ([roadmap](#not-implemented)) |
| `text` | string | — | Max `MAX_TEXT_LENGTH` chars (2000 default). Rejected if empty/whitespace after trim |
| `ssml` | bool | `false` | PocketTTS strips tags before synthesis (regex `<[^>]+>` removal) — no SSML-aware prosody |
| `language` | string \| null | `null` | Hint only; voice resolution is by `voiceURI`, not `language` |
| `voice` | string | — | Must exactly match a `voiceURI` from `/v1/voices`. 404 if not found |
| `prev_utterance` / `next_utterance` | string \| null | `null` | Accepted, passed into `SynthesisParams`; PocketTTS ignores both |
| `publication_id` | string \| null | `null` | Accepted, currently unused (reserved for future cache scoping) |
| `boundary` | bool | `false` | `true` → JSON response with base64 audio + timing marks instead of raw binary |
| `output.format` | `"mp3" \| "wav" \| "opus"` | `"mp3"` | `wav` bypasses ffmpeg (fastest); `mp3`/`opus` are ffmpeg-encoded |
| `output.bitrate` | int \| null | `null` | kbps for `mp3`/`opus`; ffmpeg default (~128 mp3, ~64 opus) if unset; ignored for `wav` |
| `output.sample_rate` | int \| null | `null` | **Accepted but not applied** — output is always the model's native rate (24000 Hz for PocketTTS). No resampling happens today |
| `output.speed` | float | `1.0` | **Accepted but ignored** by PocketTTS (logged at debug level) |
| `output.pitch` | float \| null | `null` | **Accepted but ignored** by PocketTTS |

### Response — audio (`boundary: false`, default)

`200`, binary body, `Content-Type: audio/mpeg | audio/wav | audio/ogg`, `Content-Disposition: inline; filename=speech.<ext>`.

### Response — boundary (`boundary: true`)

`200`, JSON regardless of `output.format`:

```json
{
  "audio": "UklGRiQAAABXQVZFZm10IBAAAA...",
  "format": "mp3",
  "boundaries": [
    { "name": "word", "charIndex": 0, "charLength": 4, "elapsedTime": 0.0 },
    { "name": "word", "charIndex": 5, "charLength": 3, "elapsedTime": 0.31 }
  ]
}
```

| Field | Type | Notes |
|---|---|---|
| `audio` | string | Base64, encoded in `output.format` |
| `format` | string | Echoes the requested/default format |
| `boundaries` | `TimingMark[] \| null` | `null` = voice's provider doesn't support timing (`Voice.boundary == false`) — currently true for **every** voice, since PocketTTS never populates this |

### `TimingMark`

Mirrors the [Web Speech API `boundary` event](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisUtterance/boundary_event) field-for-field, so a client that already handles native `SpeechSynthesis` events needs no translation layer.

| Field | Type | Meaning |
|---|---|---|
| `name` | `"word" \| "sentence"` | Always `"word"` today |
| `charIndex` | int | Offset of the word's first char in the request's `text` |
| `charLength` | int | Word length — `text[charIndex:charIndex+charLength]` |
| `elapsedTime` | float | Seconds from audio start |

No `end` field (next mark's `elapsedTime`, or total duration for the last word, covers it) and no `text` field (client already has the source text).

---

## Not implemented

Things the schema or config surfaces but the server doesn't actually do yet:

- **Auth** — `API_KEY_ENABLED` is validated at startup but never enforced on requests.
- **Word boundaries** — no provider populates `TimingMark`s. Every voice reports `boundary: false`.
- **`output.speed` / `output.pitch` / `output.sample_rate`** — accepted, validated, silently ignored by PocketTTS.
- **`id` / `publication_id`** — parsed, not used for caching, idempotency, or dedup.
- **SSML** — tags are stripped, not interpreted. No prosody control.
- **MathML** — passed through as plain text; equations get spoken as raw markup.
- **Providers beyond PocketTTS** — ElevenLabs is planned but not yet wired into `_build_registry()`.
