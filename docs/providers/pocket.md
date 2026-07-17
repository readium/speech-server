# Provider: PocketTTS

Model-level information for the `pocket` provider — the things that are true for the whole model,
so they're documented here once instead of repeated on every voice in `/voices`. The API still
merges the model-level defaults below into each voice (a voice may override them).

Source: [kyutai/pocket-tts](https://github.com/kyutai-labs/pocket-tts) — a CPU TTS (flow-based LM +
Mimi neural codec).

## Identity

- **Provider id:** `pocket`
- **Voice identifier:** `urn:readium:tts:pocket:<originalName>` (e.g. `urn:readium:tts:pocket:estelle`).
  Requests combine the `identifier` with a `language` — voices are declared **once**, not per
  language. The server picks the right language model behind the scenes.

## Model-level defaults (merged into every voice)

| Property | Value | Notes |
|---|---|---|
| `quality` | `veryHigh` | Quality of the **voice**, not the audio output. All pocket voices are `veryHigh`. |
| `controls.pitch` | `false` | Not supported. |
| `controls.speed` | `false` | Not supported (no native speed control). |
| `controls.ssml` | `false` | SSML not supported; tags are stripped, not rendered. |
| `controls.boundary` | `false` | No word-level timing marks. |

A future voice that overrides one of these (e.g. `controls.ssml: true`) would carry that field in
`voices.json`; otherwise the value above applies.

## Audio output

PocketTTS renders **24 kHz · mono · 16-bit PCM**, returned as a standard **WAV** file with no
re-encoding (the default, and fastest — no ffmpeg). The server can transcode on request:

- `wav` — native, lossless. **Default.**
- `opus` — compressed, high quality. Strong second choice.
- `mp3` — lossy; noticeably worse, not a good default.

`output.sample_rate` is accepted but not applied — output is always the model's native 24 kHz.

## Languages & voices

- **Native languages:** `en` `fr` `it` `de` `es` `pt`. English ships many voices; each other
  language ships one native voice.
- **Cross-language:** any voice can also speak the languages it declares in `otherLanguages`,
  *if* that `(voice, language)` pair is installed (`VOICE_LANGUAGES`). A voice needs the target
  language's base model **and** its per-language speaker embedding — see
  [configuration → model sizes](../configuration.md#model-sizes--ram).
- What's **actually installed** on a deployment is what `GET /voices` returns (realtime). The full
  declared list of possibilities lives in `app/data/voices/pocket/voices.json`.

## Constraints

- CPU only; torch ≥ 2.5 CPU build. `en`/`it`/`pt` are 6-layer models; `fr`/`de`/`es` are larger
  24-layer models (slower, higher quality). Throughput scales by worker processes.
