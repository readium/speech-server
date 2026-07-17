# API Reference

HTTP API for the Readium Speech Server: list voices, synthesize speech. Implements the [Readium Speech](https://github.com/readium/speech) `ReadiumSpeechUtterance` / `ReadiumSpeechVoice` contract plus server-specific extensions, called out below.

Base path: `/`. All bodies are `application/json` unless noted.

---

## Contents

- [Authentication](#authentication)
- [Errors](#errors)
- [Health](#health)
- [`GET /service`](#get-service)
- [`GET /voices`](#get-voices)
- [`POST /synthesize`](#post-synthesize)
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
| 404 | `voice_not_found` | `voice` identifier not in the registry |
| 404 | `voice_language_unsupported` | The requested `voice` (or `voice` + `language`) isn't served here. Deliberately neutral — it does not reveal *why* (whether a voice/language is installed), only that it's unsupported. Ask `/voices` for what this deployment actually serves |
| 413 | `payload_too_large` | `text` exceeds `MAX_TEXT_LENGTH` |
| 422 | `validation_failed` | Request body fails schema validation (wrong type, missing required field, invalid enum value) |
| 502 | `provider_error` | Provider or ffmpeg failed (bad voice state, generation error, encode failure) |
| 503 | `service_not_ready` | **During startup** the server accepts connections immediately and loads models in the background — `/synthesize` and `/voices` return 503 until warmup finishes (`/healthz` and `/service` stay up throughout; `/readyz` flips to 200 when ready). Also 503 from `/readyz` if ffmpeg is missing or a provider is unhealthy, and from `/synthesize` when a provider's circuit breaker is open — see [configuration](configuration.md) for `CIRCUIT_BREAKER_*` |

`unsupported_format` (415), `rate_limited` (429), and `provider_timeout` (504) are declared in `app/api/errors.py` for future providers but no current code path raises them — a `429`/`503` seen in production is nginx's own rate/connection limit, a plain nginx error page, not this JSON shape.

---

## Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/healthz` | Liveness. Always `200 {"status": "ok"}` once the process is up. |
| `GET` | `/readyz` | Readiness. `200` once models are loaded, ffmpeg is on `PATH`, and every registered provider reports healthy; `503` otherwise. |

---

## `GET /service`

```
GET /service
```

Server-wide, per-provider **capabilities** — kept separate from `/voices` so this isn't repeated on
every voice: supported output formats + default, request limits, and per provider the model-level
`quality`/`controls` and the installed-language summary. The voices themselves are on
[`GET /voices`](#get-voices). Per-provider details (output specs, voice notes) live in each
provider's README under `docs/providers/`.

```json
{
  "output": {"formats": ["wav", "mp3", "opus"], "default": "wav"},
  "limits": {"maxTextLength": 2000, "maxConcurrentSyntheses": 2},
  "providers": [
    {
      "id": "pocket",
      "installedLanguages": ["en"]
    }
  ]
}
```

`providers[].installedLanguages` reflects `LANGUAGES` + `VOICE_LANGUAGES` as actually configured.
Model-level `quality`/`controls` aren't repeated here — they're merged into each voice on
[`GET /voices`](#get-voices) and documented per provider under `docs/providers/`. See
[configuration](configuration.md).

---

## `GET /voices`

```
GET /voices
GET /voices?language=fr
GET /voices?provider=pocket
GET /voices?offset=0&limit=20
```

| Param | Type | Default | Description |
|---|---|---|---|
| `language` | string | — | Filter by BCP-47 language prefix, matched against a voice's primary `language` **or** `otherLanguages` (`en`, `fr`, ...) |
| `provider` | string | — | Filter by provider id (`pocket`) |
| `offset` | int ≥ 0 | `0` | Voices to skip |
| `limit` | int ≥ 1 | none | Max voices to return |

The voices **actually installed** on this deployment (realtime): each voice's `language` (primary)
and `otherLanguages` reflect what's loaded now, bounded by `LANGUAGES` + `VOICE_LANGUAGES`. Model-level
`quality`/`controls` are merged in per voice. A voice not in this list can't be synthesized here.

Response: `200`, `Voice[]`.

Headers: `X-Total-Count` (matches before pagination), `X-Offset`, `X-Limit` (omitted when `limit` unset).

### `Voice`

Model-level info (quality default, control support) is declared once per provider and **merged**
into every voice it serves; a voice only carries a field in `voices.json` when it's voice-specific
or needs to override that default. `otherLanguages` reflects languages **actually installed** for
that voice on this deployment, not every language the voice could theoretically support — see
[configuration](configuration.md).

```json
{
  "name": "Alba",
  "originalName": "alba",
  "provider": "pocket",
  "identifier": "urn:readium:tts:pocket:alba",
  "language": "en-US",
  "otherLanguages": [],
  "gender": "male",
  "quality": "veryHigh",
  "controls": {}
}
```

`controls` lists only the **enabled** controls — a control the voice doesn't support is absent
(pocket supports none, so `{}`). A voice that supported SSML would show `"controls": {"ssml": true}`.

**`ReadiumSpeechVoice`-aligned:**

| Field | Type | Notes |
|---|---|---|
| `name` | string | Display name |
| `originalName` | string | Raw engine voice id |
| `language` | string | BCP-47, primary |
| `otherLanguages` | string[] | Additional languages this voice is actually installed for — empty by default (`VOICE_LANGUAGES` unset) |
| `gender` | `"male" \| "female" \| "neutral" \| null` | |
| `quality` | `"veryLow"…"veryHigh" \| null` | Provider default unless a voice overrides it. PocketTTS voices are always `"veryHigh"` |

**Server extensions (not in `ReadiumSpeechVoice`):**

| Field | Type | Notes |
|---|---|---|
| `provider` | string | Backend serving this voice — `"pocket"` today |
| `identifier` | string | Send this as `SynthesizeRequest.voice` |
| `controls` | object | `{pitch, speed, ssml, boundary}` booleans — what this voice accepts, merged from the provider's defaults with any voice-specific override. PocketTTS: all `false` |

---

## `POST /synthesize`

```json
{
  "id": "urn:uuid:019f178c-cc7c-7bb3-a39b-d185f43d3cc4",
  "text": "Ceci est un test.",
  "ssml": false,
  "language": "fr",
  "voice": "urn:readium:tts:pocket:estelle",
  "prev_utterance": "La nuit était sombre.",
  "next_utterance": "La pièce était froide.",
  "publication_id": "urn:isbn:9780000000000",
  "boundary": true,
  "output": {
    "format": "wav",
    "bitrate": 64,
    "sample_rate": null,
    "speed": 1.0,
    "pitch": null
  }
}
```

Only `text` is required; everything else defaults as shown (`voice` falls back to `POCKET_DEFAULT_VOICE`).

| Field | Type | Default | Notes |
|---|---|---|---|
| `id` | string \| null | `null` | Client-generated UUID v7 URN. Parsed, logged, **not otherwise used** — no caching or idempotency yet ([roadmap](#not-implemented)) |
| `text` | string | — | Max `MAX_TEXT_LENGTH` chars (2000 default). Rejected if empty/whitespace after trim |
| `ssml` | bool | `false` | PocketTTS strips tags before synthesis (regex `<[^>]+>` removal) — no SSML-aware prosody |
| `language` | string \| null | `null` | For voices installed across more than one language (`VOICE_LANGUAGES=*:*` or an explicit override), picks which installed language to synthesize in; falls back to the voice's primary language if unset or not installed for that voice |
| `voice` | string \| null | `null` | A voice `identifier` from `/voices`, or a raw `originalName`. 404 if not found. When omitted, falls back to `POCKET_DEFAULT_VOICE`; if that's unset too, `400` |
| `prev_utterance` / `next_utterance` | string \| null | `null` | Accepted, passed into `SynthesisParams`; PocketTTS ignores both |
| `publication_id` | string \| null | `null` | Accepted, currently unused (reserved for future cache scoping) |
| `boundary` | bool | `false` | `true` → JSON response with base64 audio + timing marks instead of raw binary |
| `output.format` | `"wav" \| "mp3" \| "opus"` | `"wav"` | `wav` bypasses ffmpeg and is highest quality (fastest, no lossy encoding); `mp3`/`opus` are ffmpeg-encoded on request — see [`GET /service`](#get-service) for what's available |
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
| `boundaries` | `TimingMark[] \| null` | `null` = this voice doesn't support timing (`Voice.controls.boundary == false`) — currently true for **every** voice, since PocketTTS never populates this |

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
- **Word boundaries** — no provider populates `TimingMark`s. Every voice reports `controls.boundary: false`.
- **`output.speed` / `output.pitch` / `output.sample_rate`** — accepted, validated, silently ignored by PocketTTS.
- **`id` / `publication_id`** — parsed, not used for caching, idempotency, or dedup.
- **SSML** — tags are stripped, not interpreted. No prosody control.
- **MathML** — passed through as plain text; equations get spoken as raw markup.
- **Curated cross-language voice quality** — `otherLanguages` in `voices.json` documents what a voice is *capable* of, not whether it's a *good fit* (e.g. an English voice speaking French). No ranking/curation of this is implemented yet — deliberately conservative, pending a listening review.
- **Providers beyond PocketTTS** — ElevenLabs is planned but not yet wired into `_build_registry()`.
