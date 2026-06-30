# Readium Speech Server — API Reference & Design Notes

Everything implemented in the `feature/pocket-tts` branch. Covers the full
request/response contract, field-by-field meaning, and the reasoning behind
each design decision.

---

## Table of Contents

1. [POST /v1/synthesize — Request](#post-v1synthesize--request)
2. [POST /v1/synthesize — Response (audio)](#post-v1synthesize--response-audio)
3. [POST /v1/synthesize — Response (boundary)](#post-v1synthesize--response-boundary)
4. [GET /v1/voices — Response](#get-v1voices--response)
5. [The `id` field and UUID v7](#the-id-field-and-uuid-v7)
6. [Word Boundaries — deep dive](#word-boundaries--deep-dive)
7. [Language Filtering](#language-filtering)
8. [Provider Capabilities](#provider-capabilities)
9. [Future: MathML](#future-mathml)

---

## POST /v1/synthesize — Request

```json
{
  "id":            "urn:uuid:019f178c-cc7c-7bb3-a39b-d185f43d3cc4",
  "text":          "Ceci est un test.",
  "ssml":          false,
  "language":      "fr",
  "voice":         "urn:readium:tts:pocket:fr-estelle",
  "prev_utterance": "La nuit était sombre.",
  "next_utterance": "La pièce était froide.",
  "publication_id": "urn:isbn:9780000000000",
  "boundary":      true,
  "output": {
    "format":      "mp3",
    "bitrate":     64,
    "sample_rate": null,
    "speed":       1.0,
    "pitch":       null
  }
}
```

### Top-level fields

| Field | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `id` | `string \| null` | No | `null` | Client-generated utterance identifier. UUID v7 URN. Used for correlation, idempotency, future caching. Currently received but not used by server. |
| `text` | `string` | **Yes** | — | The text to synthesize. Max 2000 chars (configurable via `MAX_TEXT_LENGTH`). Must not be empty/whitespace. |
| `ssml` | `boolean` | No | `false` | If `true`, `text` contains SSML markup. PocketTTS strips tags before synthesis — no SSML-aware prosody today. |
| `language` | `string \| null` | No | `null` | Language hint (`"fr"`, `"en"`). Used for provider routing in future multi-language requests. |
| `voice` | `string` | **Yes** | — | `voiceURI` from the voices list. Must exactly match a registered voice. Returns 404 if not found. |
| `prev_utterance` | `string \| null` | No | `null` | Text of the sentence before this one. Passed to provider for prosody context (natural speech flow). PocketTTS ignores today — reserved for Kokoro/commercial providers. |
| `next_utterance` | `string \| null` | No | `null` | Text of the sentence after this one. Same purpose. |
| `publication_id` | `string \| null` | No | `null` | Server extension. Identifies the ebook/document. Future: scopes the in-memory cache so utterances from different books don't collide. |
| `boundary` | `boolean` | No | `false` | If `true`, response is JSON with base64 audio + word timing marks instead of binary audio. See [boundary section](#post-v1synthesize--response-boundary). |

### `output` object

`output` is **optional** — omit it entirely to get mp3 at defaults.

Why nested? The Readium Speech API spec groups audio parameters under `output`
to distinguish them from utterance properties (`text`, `language`, `voice`).
Flat structure would mix "what to say" with "how to encode it".

| Field | Type | Default | Meaning |
|---|---|---|---|
| `format` | `"mp3" \| "wav" \| "opus"` | `"mp3"` | Output audio format. `wav` = raw PCM in RIFF container (no ffmpeg needed, fastest). `mp3` and `opus` go through ffmpeg. |
| `bitrate` | `integer \| null` | `null` | kbps for mp3/opus encoding. `null` = ffmpeg default (~128 kbps mp3, ~64 kbps opus). Ignored for `wav`. |
| `sample_rate` | `integer \| null` | `null` | Output sample rate. `null` = native model rate (24000 Hz for PocketTTS). Resampling via ffmpeg if set differently. |
| `speed` | `float` | `1.0` | Playback speed multiplier. `0.5` = half speed, `2.0` = double. PocketTTS ignores today (logs warning). Passed through for providers that support it. |
| `pitch` | `float \| null` | `null` | Pitch adjustment. PocketTTS ignores today. Passed through for providers that support it. |

---

## POST /v1/synthesize — Response (audio)

When `boundary: false` (default). Returns **binary audio** directly.

```
HTTP 200 OK
Content-Type: audio/mpeg          (mp3)
              audio/wav           (wav)
              audio/ogg           (opus)
Content-Disposition: attachment; filename=speech.mp3
```

Body = raw audio bytes. No JSON wrapper.

### Error responses

All errors return JSON:

```json
{
  "error": {
    "code": "voice_not_found",
    "message": "Voice 'urn:unknown' not found.",
    "detail": null
  }
}
```

| Status | `error.code` | Cause |
|---|---|---|
| 400 | `validation_failed` | Empty or whitespace `text` |
| 404 | `voice_not_found` | `voice` URI not in registry |
| 413 | `payload_too_large` | `text` exceeds `MAX_TEXT_LENGTH` |
| 422 | *(Pydantic detail)* | Schema error (wrong type, missing `voice`, invalid `format`) |

---

## POST /v1/synthesize — Response (boundary)

When `boundary: true`. Returns **JSON** regardless of `output.format`.

```json
{
  "audio": "UklGRiQAAABXQVZFZm10IBAAAA...",
  "format": "mp3",
  "boundaries": [
    { "name": "word", "charIndex": 0,  "charLength": 4, "elapsedTime": 0.0  },
    { "name": "word", "charIndex": 5,  "charLength": 3, "elapsedTime": 0.31 },
    { "name": "word", "charIndex": 9,  "charLength": 2, "elapsedTime": 0.52 },
    { "name": "word", "charIndex": 12, "charLength": 5, "elapsedTime": 0.68 }
  ]
}
```

### Response fields

| Field | Type | Meaning |
|---|---|---|
| `audio` | `string` | Base64-encoded audio in the requested `output.format`. Decode to bytes to play. |
| `format` | `string` | Format of the encoded audio (`"mp3"`, `"wav"`, `"opus"`). |
| `boundaries` | `array \| null` | Word timing marks. **`null`** = provider does not support word boundaries. **`[]`** = supported but no marks produced. **`[{...}]`** = marks present. |

### Why `null` not `[]` for unsupported?

`[]` is ambiguous — could mean "supported but no words" (edge case) or "not supported."
`null` is an unambiguous sentinel: this provider cannot produce timing marks.
Client does one null-check, no invented boolean flags needed.

```
boundaries: null  →  feature not available for this voice/provider
boundaries: []    →  available but nothing produced (shouldn't happen in practice)
boundaries: [...] →  available + marks
```

### `TimingMark` fields

Mirrors the **Web Speech API `SpeechSynthesisEvent`** boundary event fields exactly.
This is intentional — Readium clients already handle Web Speech API events; same field
names = zero translation layer.

| Field | Type | Web Speech API equivalent | Meaning |
|---|---|---|---|
| `name` | `"word" \| "sentence"` | `event.name` | Type of boundary. Currently always `"word"`. |
| `charIndex` | `integer` | `event.charIndex` | Character offset in the original `text` string where this word starts. |
| `charLength` | `integer` | `event.charLength` | Character count of the word. `text.slice(charIndex, charIndex + charLength)` = the word. |
| `elapsedTime` | `float` | `event.elapsedTime` | Seconds from audio start when this word begins. |

**Why no `text` field in the mark?** The original `text` is already in the request.
Client reconstructs the word: `text.substring(charIndex, charIndex + charLength)`.
Embedding the word string would duplicate data and create mismatch risk if text is
preprocessed differently.

**Why no `end` field?** End time = next mark's `elapsedTime` (or total audio duration
for the last word). Web Speech API omits it for the same reason.

### Boundary support by provider

| Provider | `supports_boundaries` | Notes |
|---|---|---|
| PocketTTS | `false` | `generate_audio()` returns PCM only — no timing data |
| ElevenLabs (future) | `true` | Returns character-level `alignment` arrays — aggregate to words |
| Azure Speech (future) | `true` | `WordBoundary` SDK events with tick offsets — convert to seconds |
| Web Speech API | `true` (browser-native) | Native `boundary` events |

For ElevenLabs: their response has `characters[]`, `character_start_times_seconds[]`,
`character_end_times_seconds[]`. Walk the arrays, emit a new `TimingMark` each time
a space or punctuation boundary is crossed.

---

## GET /v1/voices — Response

```json
[
  {
    "source":        "json",
    "label":         "Alba (English)",
    "name":          "pocket-en-alba",
    "originalName":  "alba",
    "voiceURI":      "urn:readium:tts:pocket:en-alba",
    "language":      "en",
    "gender":        "female",
    "quality":       "normal",
    "pitchControl":  false,
    "preloaded":     true,
    "provider":      "pocket",
    "engineVoiceId": "alba",
    "sampleRate":    24000,
    "mimeTypes":     ["audio/mpeg", "audio/wav", "audio/ogg"],
    "boundary":      false
  }
]
```

Null-valued optional fields (`localizedName`, `altNames`, `altLanguage`, `otherLanguages`, `multiLingual`, `children`, `pitch`, `rate`, `nativeID`, `note`) are omitted from the response.

### Field groups

**Readium `ReadiumSpeechVoice`-aligned fields** (standard — client expects these):

| Field | Meaning |
|---|---|
| `source` | Always `"json"` for server-hosted voices. `"browser"` = Web Speech API voice (client-side only). |
| `label` | Human-readable display name. Used in UI pickers. |
| `name` | Unique identifier for this voice within Readium ecosystem. |
| `originalName` | Raw engine voice ID as provided by the TTS engine. |
| `voiceURI` | **The key field** — send this in `SynthesizeRequest.voice`. Globally unique URI. |
| `language` | Language code (`"en"`, `"fr"`). Matches PocketTTS model names. Used for filtering and matching to book language. |
| `gender` | `"male"`, `"female"`, `"neutral"`, or `null`. |
| `quality` | `"veryLow"`, `"low"`, `"normal"`, `"high"`, `"veryHigh"`. PocketTTS voices = `"normal"`. |
| `preloaded` | `true` = model weights are in the image / downloaded to the weights volume, ready immediately. |
| `pitchControl` | `true` = provider accepts `output.pitch`. PocketTTS = `false`. |
| `pitch` / `rate` | Recommended defaults for this voice, if the engine specifies any. Usually `null`. |

**Server extension fields** (not in Readium spec — added by this server):

| Field | Meaning |
|---|---|
| `provider` | Which TTS backend serves this voice. `"pocket"` today. `"kokoro"`, `"elevenlabs"`, `"azure"` later. |
| `engineVoiceId` | Raw voice ID passed to the engine internally. Not for client use — opaque. |
| `sampleRate` | Native PCM sample rate of the model output in Hz. PocketTTS = `24000`. |
| `mimeTypes` | Audio formats this voice can produce. All voices support `["audio/mpeg", "audio/wav", "audio/ogg"]`. |
| `boundary` | **`true`** = this voice's provider supports word timing marks. Send `boundary: true` in synthesis requests. **`false`** = marks unavailable, response will have `boundaries: null`. |

### Why `boundary` on the voice?

Client checks `voice.boundary` **before** sending the synthesis request.
If `false`, client doesn't set `boundary: true` — saves a round trip and avoids
getting `null` back. If a client ignores the flag and sends `boundary: true` anyway,
the response carries `boundaries: null` to explain why marks are absent.

---

## The `id` field and UUID v7

### Anatomy of the `id`

```
"id": "urn:uuid:019f178c-cc7c-7bb3-a39b-d185f43d3cc4"
       ───┬───  ───┬───  ───────────────────────────────
          │        │     UUID itself (128 bits, 32 hex chars + 4 dashes)
          │        └──── URN namespace: UUID (IANA-registered)
          └───────────── URN scheme: a name, not a network address
```

**`urn:`** — Uniform Resource Name (RFC 8141). Persistent global identifier that
doesn't resolve to a URL. Unlike `https://`, it just *names* something uniquely and
permanently. Good for IDs that need to survive across systems without implying a
network location.

**`uuid:`** — The IANA-registered URN namespace for UUIDs (RFC 4122).

### UUID v7

The example ID uses **UUID version 7** (RFC 9562, 2024).

```
019f178c-cc7c-7bb3-a39b-d185f43d3cc4
─────────────────────────────────────
First 48 bits = Unix timestamp in milliseconds
019f178c cc7c → 0x019f178ccc7c → 1750697878652 ms → 2025-06-23 ~17:57 UTC

Version nibble = 7 (the "7" in "7bb3")

Remaining bits = random
```

UUID version comparison:

| Version | Year | Sortable? | Notes |
|---|---|---|---|
| v1 | 1997 | Yes | Encodes MAC address — privacy risk |
| v4 | 2003 | No | Pure random — most common today |
| v7 | 2024 | **Yes** | Time-ordered + random — preferred for new systems |

v7 is preferred because database indexes on UUIDs don't fragment (sorted insert order),
and you can decode the creation timestamp from the ID itself.

### What the server does with `id` today

**Nothing.** Field is received, parsed into `Utterance.id`, never used.

### What it's intended for

1. **Correlation** — synthesis requests can return out of order. Client matches
   audio response to book position using `id`.

2. **Cache key** — `(publication_id, id, voice, format)` → cached audio bytes.
   Same sentence + same voice = return cached bytes, skip synthesis. Defined in
   Phase 3 / `design.md §17` as in-memory LRU cache.

3. **Idempotency** — client retries failed request with same `id` → server detects
   duplicate, returns cached result, doesn't synthesize twice.

4. **Distributed tracing** — log `id` alongside errors, duration, provider name.
   "Why did this utterance fail?" traceable across log lines.

---

## Word Boundaries — deep dive

### Why boundaries matter

Readium reads ebooks aloud. As audio plays, the UI highlights the word currently
being spoken. To highlight correctly it needs to know: "at 0.31 seconds into this
audio clip, the third word starts." That's a timing mark.

Without boundaries: audio plays but nothing highlights. Reader loses their place.

### The Web Speech API model

The browser's built-in TTS (`SpeechSynthesis`) fires a `boundary` event for each
word. Event fields:

```
charIndex    integer   Character offset in the utterance string
charLength   integer   Length of the word
elapsedTime  float     Seconds since speech started
name         string    "word" or "sentence"
```

MDN reference: https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisUtterance/boundary_event

Our `TimingMark` is a direct mapping. When a Readium client already handles Web Speech
API boundary events, it handles our server response with zero changes.

### The ElevenLabs model

ElevenLabs stream-with-timestamps returns character-level arrays:

```json
{
  "alignment": {
    "characters":                  ["H","e","l","l","o"," ","w","o","r","l","d"],
    "character_start_times_seconds": [0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, ...],
    "character_end_times_seconds":   [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, ...]
  }
}
```

ElevenLabs reference: https://elevenlabs.io/docs/api-reference/text-to-speech/stream-with-timestamps

To convert to `TimingMark` array: walk `characters[]`, track `charIndex` from the
original text, emit a new mark each time a space or punctuation boundary is crossed,
set `elapsedTime` from `character_start_times_seconds[i]`.

### PocketTTS limitation

`pocket_tts.TTSModel.generate_audio(state, text)` returns a single `torch.Tensor`
of PCM samples. The entire sentence is synthesized in one pass. No per-word timing
information comes back from the model.

Options to work around (not implemented):
- **Word-by-word synthesis** — split text on spaces, synthesize each word, measure
  sample count → duration. Very slow (N model calls instead of 1). Approximate
  (prosody changes at word boundaries vs. sentence context).
- **Forced alignment** — run a separate forced-alignment model (e.g. `montreal-forced-aligner`)
  on the audio + transcript after synthesis. Adds latency, heavy dependency.

Current behaviour: `boundary: true` with a PocketTTS voice returns `boundaries: null`.
`Voice.boundary = false` tells client not to ask.

---

## Language Filtering

### How it works

`LANGUAGES` environment variable = comma-separated BCP-47 prefixes:

```
LANGUAGES=en,fr
```

PocketTTS declares:
```python
supported_languages = frozenset({"en", "fr", "it", "de", "es", "pt"})
```

`active_languages()` returns the **intersection**:
```
{"en", "fr", "it", "de", "es", "pt"} ∩ {"en", "fr"} = {"en", "fr"}
```

`list_voices()` filters to voices whose `language` BCP-47 prefix is in the active set:
- `"en"` → included
- `"fr"` → included
- `"it"` → excluded

### RAM impact

Each language model is ~240 MB. Loading 6 languages = ~1.4 GB RSS.
Default `LANGUAGES=en` = ~240 MB. Select only what you need.

### FakeProvider and language filtering

`FakeProvider.supported_languages = frozenset()` (empty = language-agnostic).
`active_languages()` returns empty frozenset when `supported_languages` is empty.
`list_voices()` returns all fake voices unfiltered.

This means tests are never affected by `LANGUAGES` config — fake voices always appear.

---

## Provider Capabilities

Every provider declares its capabilities as class variables. Adding a new provider
never touches routes, synthesizer, or voice catalog — only the provider class itself
and the registry.

```python
class TTSProvider(ABC):
    id: ClassVar[str]
    supported_languages: ClassVar[frozenset[str]] = frozenset()  # empty = all
    supports_boundaries: ClassVar[bool] = False
```

| Capability | Class var | Effect |
|---|---|---|
| Language scope | `supported_languages` | `list_voices()` filters automatically |
| Word boundaries | `supports_boundaries` | `Voice.boundary` set at load time; response `boundaries` is `null` vs array |

When a future provider supports boundaries:

```python
class ElevenLabsProvider(TTSProvider):
    id = "elevenlabs"
    supported_languages = frozenset({"en", "fr", "de", ...})
    supports_boundaries = True   # ← flip this

    async def synthesize(self, params) -> AudioResult:
        ...
        return AudioResult(pcm=pcm, sample_rate=44100, boundaries=marks)  # ← populate this
```

Voices for that provider automatically get `boundary: true` in the voice list.
Synthesis response carries real marks. No other code changes.

---

## Future: MathML

MathML markup in `text` is currently passed through as-is (treated as plain text,
tags will be spoken literally). This is a known gap.

When **MathCAT** is integrated:
- Detect MathML in `text` (similar to `ssml: true` detection — look for `<math>` root tag)
- MathCAT converts MathML → spoken natural language string
- Pass the resulting string to the TTS engine as plain text

No API shape change needed. `text` stays `string`. MathML support is a
pre-processing concern inside the provider or synthesizer, not a schema concern.
