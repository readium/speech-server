# Provider: PocketTTS

Model-level information for the `pocket` provider — the things that are true for the whole model,
so they're documented here once instead of repeated on every voice in `/voices`. `quality` is
merged into each voice on `/voices` (a voice may override it in `voices.json`); `controls` is
service-wide only, on `GET /service`, not repeated per voice.

Source: [kyutai/pocket-tts](https://github.com/kyutai-labs/pocket-tts) — a CPU TTS (flow-based LM +
Mimi neural codec).

## Identity

- **Provider id:** `pocket`
- **Voice identifier:** `urn:readium:tts:pocket:<originalName>` (e.g. `urn:readium:tts:pocket:estelle`).
  Requests combine the `identifier` with a `language` — voices are declared **once**, not per
  language. The server picks the right language model behind the scenes.

## Model-level defaults

| Property | Value | Notes |
|---|---|---|
| `quality` | `veryHigh` | Quality of the **voice**, not the audio output. All pocket voices are `veryHigh`. Merged into every voice on `/voices`; a voice may override it in `voices.json`. |
| `controls.pitch` | `false` | Not supported. Service-wide only — see `GET /service`. |
| `controls.speed` | `false` | Not supported (no native speed control). Service-wide only. |
| `controls.ssml` | `false` | SSML not supported; tags are stripped, not rendered. Service-wide only. |
| `controls.boundary` | `false` | No word-level timing marks. Service-wide only. |

## Audio output

PocketTTS renders **24 kHz · mono · 16-bit PCM**, returned as a standard **WAV** file with no
re-encoding (the default, and fastest — no ffmpeg). The server can transcode on request:

- `wav` — native, lossless. **Default.**
- `opus` — compressed, high quality. Strong second choice.
- `mp3` — lossy; noticeably worse, not a good default.

`output.sample_rate` is accepted but not applied — output is always the model's native 24 kHz.

## Languages & voices

- **Native languages:** `en` `fr` `it` `de` `es` `pt` `nl`. English ships many voices; each other
  language ships one native voice.
- **Cross-language:** any voice can also speak the languages it declares in `otherLanguages`,
  *if* that `(voice, language)` pair is installed (`VOICE_LANGUAGES`). A voice needs the target
  language's base model **and** its per-language speaker embedding — see
  [configuration → model sizes](../configuration.md#model-sizes--ram).
- What's **actually installed** on a deployment is what `GET /voices` returns (realtime). The full
  declared list of possibilities lives in `app/data/voices/pocket/voices.json`.

## Constraints

- CPU only; torch ≥ 2.5 CPU build. Throughput scales by worker processes.
- **Models:** one model per language, pinned in `_LANG_MODEL` (`app/providers/pocket_tts.py`),
  all from pocket-tts ≥ 4.0. The older 24-layer (`_24l`) models are not supported.

  | Lang | Model | Layers | Download |
  |---|---|---|---|
  | `en` | `english_18m_2026-10` (Kyutai 18.2M flagship) | 8 (d_model 512) | ~111 MB |
  | `fr` | `french` | 6 | ~219 MB |
  | `it` | `italian` | 6 | ~219 MB |
  | `de` | `german` | 6 | ~219 MB |
  | `es` | `spanish` | 6 | ~219 MB |
  | `pt` | `portuguese` | 6 | ~219 MB |
  | `nl` | `dutch` | 6 | ~219 MB |

- Each model uses ~2 CPU cores via an internal generate→decode pipeline and pins torch to a
  single intra-op thread itself (on import) — so we don't set `torch.set_num_threads()`. Give
  the box more cores by running more workers, not more threads per model.
