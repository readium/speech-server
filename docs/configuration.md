# Configuration

Run `make configure` to generate config via an interactive wizard, or run `bash scripts/configure.sh` directly.

Config is split by scope, all files written by the wizard:

- **`.env`** — server/auth/concurrency/circuit-breaker. Universal, provider-agnostic.
- **`pocket-tts.env`** — PocketTTS-scoped install config (which languages, which voices in which
  languages).
- **`elevenlabs.env`** — ElevenLabs-scoped config (`ELEVENLABS_API_KEY`, `ELEVENLABS_MODEL_ID`,
  `ELEVENLABS_LANGUAGES`). Languages are **provider-scoped** — ElevenLabs has its own set here,
  independent of pocket's `LANGUAGES`. See [providers/elevenlabs.md](providers/elevenlabs.md).

Each provider gets its own env file this way, since "which languages/voices/keys does this provider
need" is inherently per-provider, not global. `pydantic-settings` reads them all automatically
(`app/config/settings.py`); a provider env file simply being absent is not an error. Existing
installs are migrated automatically the next time the wizard runs (it moves
`LANGUAGES`/`VOICE_INSTALL_MODE`/`POCKET_DEFAULT_VOICE` out of `.env` and into a newly created
`pocket-tts.env`, once, silently).

## Setup wizard

`make configure` handles both first-time setup and ongoing management. The top-level menu only
has universal actions; anything provider-scoped lives behind **Manage provider**, which lists
registered providers (`pocket`, `elevenlabs`) and drops into a provider-specific submenu:

```
Readium Speech Server

  Current: languages=en  workers=1

  1) Show full config
  2) Manage provider
  3) Change workers
  4) Update HF token
  5) First-time setup (re-run / overwrite)
  6) Reset
  q) Quit
```

**Manage provider → pocket:** (the live install plan is shown above the menu each time)

```
1) Languages
2) Voice coverage
3) Back
```

A linear two-step flow: pick languages first, then choose coverage over them.

**Languages** re-runs the same multi-select as first-time setup — whatever you check becomes
`LANGUAGES` (the ceiling: the base models that load). Newly-added languages download once on next
restart (~219 MB for en/it/pt, ~672 MB for fr/de/es); removed languages keep their model files in
the Docker volume — see [Disk space](#disk-space) to reclaim selectively.

**Voice coverage** chooses what installs on top of the native defaults (see
[Per-voice language overrides](#per-voice-language-overrides)). The native voices of your selected
languages are **always** installed — they're the best-matched model for each voice, so coverage
only ever *adds* cross-language support:

- **default** — native voices only, each in its own language (`VOICE_LANGUAGES=`).
- **all** — every voice also speaks every selected language, including non-native ones
  (`VOICE_LANGUAGES=*:*`).
- **custom** — defaults **plus** cross-language pairs you hand-pick. Pick any voice, then choose any
  of the languages it can speak; each pick adds an `originalName:lang` pair and, if needed, pulls
  that language into `LANGUAGES`. `VOICE_LANGUAGES` lists only the *extra* pairs — the defaults stay
  implied by `LANGUAGES`.

> **macOS only.** The configure script auto-downloads [gum](https://github.com/charmbracelet/gum) for its menus. On Linux, install gum manually before running it.

## Environment variables — `.env`

| Variable | Default | Description |
|---|---|---|
| `HF_TOKEN` | _(empty)_ | HuggingFace token. Optional — prevents rate-limiting on first-run model downloads. Shared across any provider that pulls models from HF |
| `WORKERS` | `1` | Uvicorn worker processes. Each loads a full copy of every active language model |
| `MAX_CONCURRENT_SYNTHESES` | `1` | Max parallel CPU inference jobs per worker. Each job uses ~2 cores; `configure.sh` derives this from `nproc`/RAM so cores ≈ workers × concurrency × 2 (no oversubscription) |
| `CIRCUIT_BREAKER_ENABLED` | `true` | Trip a provider's circuit breaker after repeated `synthesize()` failures, returning `503` immediately instead of hammering a broken provider |
| `CIRCUIT_BREAKER_FAILURE_THRESHOLD` | `5` | Consecutive failures before a provider's breaker opens |
| `CIRCUIT_BREAKER_RECOVERY_SECONDS` | `30` | How long an open breaker waits before allowing one trial call |
| `API_KEY_ENABLED` | `false` | Reserved — validated at startup but **not yet enforced** on any route |
| `API_KEY` | _(empty)_ | Reserved, same caveat |
| `LOG_LEVEL` | `INFO` | `DEBUG` · `INFO` · `WARNING` · `ERROR` |
| `PORT` | `8000` | Listen port |
| `MAX_TEXT_LENGTH` | `2000` | Maximum characters per synthesis request |
| `FFMPEG_BIN` | `ffmpeg` | Path to ffmpeg binary (bundled in the Docker image) |
| `ENABLED_PROVIDERS` | `pocket` | Comma-separated provider ids to register at startup: `pocket`, `elevenlabs` |
| `DEFAULT_PROVIDER` | `pocket` | Must be one of `ENABLED_PROVIDERS` — validated at startup |
| `DOMAIN` | _(empty)_ | Required when `APP_ENV=production` — used for `TrustedHostMiddleware` and nginx `server_name` |

## Environment variables — `pocket-tts.env`

| Variable | Default | Description |
|---|---|---|
| `LANGUAGES` | _(empty)_ | Comma-separated BCP-47 language codes to **load as base models**. No hardcoded fallback — env-driven; unset means no base models load (no voices served). Size per language is *not* uniform: the 6-layer `en`/`it`/`de`/`es`/`pt` models are ~219 MB download / ~438 MB RAM; the 24-layer `fr` model is ~672 MB download / ~1344 MB RAM (loaded size ~2x the download, measured at startup). Supported: `en fr it de es pt`. This is the ceiling — nothing below can exceed it |
| `VOICE_LANGUAGES` | _(empty)_ | Which voices get warmed against which of those loaded models, beyond each voice's own primary — see [Per-voice language overrides](#per-voice-language-overrides) |
| `POCKET_DEFAULT_VOICE` | _(empty)_ | Default voice when none is specified. No hardcoded fallback — env-driven; empty means the setting is unset |

## Environment variables — `elevenlabs.env`

Only loaded/required when `elevenlabs` is in `ENABLED_PROVIDERS`. Managed by the wizard
(**Manage provider → elevenlabs**). Full details: [providers/elevenlabs.md](providers/elevenlabs.md).

| Variable | Default | Description |
|---|---|---|
| `ELEVENLABS_API_KEY` | _(empty)_ | **Required** when the provider is enabled — startup fails without it. From elevenlabs.io → profile → API key |
| `ELEVENLABS_MODEL_ID` | `eleven_multilingual_v2` | Model + cost multiplier. `flash_v2_5`/`turbo_v2_5` are 0.5 credits/char (cheapest); `multilingual_v2`/`v3` are 1.0. [Compare](https://elevenlabs.io/docs/models) · [pricing](https://elevenlabs.io/pricing) |
| `ELEVENLABS_LANGUAGES` | _(empty)_ | ElevenLabs' **own** languages (comma BCP-47, e.g. `en,fr,ja`), separate from pocket's `LANGUAGES` — languages are provider-scoped. Empty = no ElevenLabs voices. Supported: the 29 languages common to all ElevenLabs models (`ar bg cs da de el en es fi fil fr hi hr id it ja ko ms nl pl pt ro ru sk sv ta tr uk zh`) |
| `ELEVENLABS_DAILY_CHAR_LIMIT` | `0` | Max characters sent to ElevenLabs **per day** so users can't spam it. `0` = unlimited. Resets at 00:00 UTC; over the cap `/synthesize` returns `429 rate_limited`. Pick per your model's rate ([pricing](https://elevenlabs.io/pricing/api) — flash/turbo bill half, so the same cost buys ~2× the characters). Host-wide (shared across workers via a JSON file). Set via wizard: Manage provider → elevenlabs → Set daily limit |
| `ELEVENLABS_USAGE_FILE` | `/tmp/elevenlabs_usage.json` | Where the daily counter is stored. Point at a volume path to persist the count across container restarts |
| `ELEVENLABS_BASE_URL` | `https://api.elevenlabs.io` | API base URL — override for testing |

`LANGUAGES` and `VOICE_LANGUAGES` operate at different levels and both matter: `LANGUAGES`
decides which base language models physically load into RAM at all — any voice whose *primary*
language isn't in this set is skipped entirely, no matter what `VOICE_LANGUAGES` says.
`VOICE_LANGUAGES` only fine-tunes which *already-loaded* models a voice also gets warmed
against.

## Per-voice language overrides

`VOICE_LANGUAGES` is one setting that does two things:

- A bare `*:*` token = install every voice's declared `otherLanguages` that are in `LANGUAGES`
  (old `VOICE_INSTALL_MODE=all`). Its absence = primary-only (old `VOICE_INSTALL_MODE=primary`,
  still the default).
- Explicit `originalName:lang` pairs cherry-pick or prune on top of that base — e.g. install
  French for Alba specifically without turning on `*:*` for every voice, or turn on `*:*` but
  exclude one voice's Portuguese support. Use the wizard's "Voice coverage → custom", or set
  directly:

```dotenv
VOICE_LANGUAGES=alba:fr,alba:de,-javert:es
```

Comma-separated `originalName:lang` pairs (voice's `originalName` from `voices.json`, not its
`identifier`). A pair adds by default; a leading `-` removes instead. `*:*` can appear in the
same list as explicit pairs (`VOICE_LANGUAGES=*:*,-javert:es` = "everything except javert's
Spanish"). Rules, applied on top of the `*:*` base:

1. An **add** pair can only promote a language the voice already declares in its own
   `otherLanguages` in `voices.json` — it can't invent support voices.json doesn't claim.
2. Both directions are bounded by `LANGUAGES` — neither ever triggers downloading a new base
   language model by itself; the language must already be enabled.
3. If the same pair appears both with and without `-`, **remove wins** — it's always the final
   word for the exact pair it names.
4. A voice installs for whichever enabled languages apply — its primary if that's in
   `LANGUAGES`, plus any added/`*:*` cross-languages. A voice can even run in a **non-primary**
   language *without* its primary base model (e.g. `VOICE_LANGUAGES=estelle:en` with
   `LANGUAGES=en` installs estelle in English only, no French model): pocket_tts loads a voice's
   embedding from the target language's model, not the primary's. When a request omits `language`,
   the voice's default is its primary if installed, else its first installed language. `/voices`
   still reports the voice's true primary `language` (from `voices.json`); `/service` reports which
   languages are actually installed.

## Model sizes & RAM

The wizard deliberately keeps sizes out of its prompts — they live here. All figures are for the
`kyutai/pocket-tts-without-voice-cloning` models (what the server loads without gated access) and
are approximate.

**Base language model** — one per selected language, loaded once per worker. Two size classes:

| Languages | Layers | Download (disk, once) | RAM (per worker) |
|---|---|---|---|
| `en` `it` `de` `es` `pt` | 6 | ~219 MB | ~438 MB |
| `fr` | 24 (`_24l`) | ~672 MB | ~1344 MB |

RAM ≈ 2× the download (measured at startup). This is the dominant cost.

**Voice embedding** — one per installed `(voice, language)`, small: ~6 MB into a 6-layer language,
~25–33 MB into a 24-layer language. Native voices carry one; each cross-language pair adds one more.

**RAM formula:** `WORKERS × (sum of each active language's RAM size)`.
Example: 1 worker, English + French = `438 + 1344 ≈ 1782 MB` RAM (download ~891 MB base + a few
hundred MB of embeddings). Add a language, and its whole base model is added per worker.

To see the exact **voice/pair count** for your config (not sizes), the wizard's config view uses
`scripts/pocket_plan.py`.

## Disk space

Changing `LANGUAGES` or `VOICE_LANGUAGES` doesn't free disk on its own — weights stay cached in the
`weights_cache` volume in case you re-add them later (and re-download automatically from the HF
cache on next start if you do). To reclaim space for what you no longer use, without purging
everything:

```bash
make prune-models          # dry-run report
make prune-models-apply    # actually delete
```

It prunes to the **exact install plan** of your current `LANGUAGES` + `VOICE_LANGUAGES` (reusing
the same `plan_install` the server loads with, so it can't drift): it drops base models for
languages no longer enabled **and**, within kept languages, individual voice embeddings no longer
used (e.g. a removed cross-language pair). Empty `VOICE_LANGUAGES` (default coverage) correctly
keeps just the native voices. It only deletes a file's underlying blob once nothing else references
it — safe to re-run anytime. Under the hood it's `docker compose exec app python
scripts/prune_weights.py [--apply]`; pass `--keep en,fr` for a language-level-only override that
preserves every embedding.

To reclaim everything at once instead, use the wizard's "Reset" → "purge all downloaded models"
option, which removes the whole `weights_cache` volume.

## Production vs development

First-time setup writes `APP_ENV=production` and prompts for `DOMAIN`. `make start` puts nginx in front as a reverse proxy; the app container has no published port.

For local dev, set `APP_ENV=development` in `.env` (`DOMAIN` becomes optional) and use `make dev-docker` — exposes `:8000` directly with no nginx.

nginx rate-limits `/synthesize` (2 req/s, burst 4) and caps connections per IP. A `503` from behind nginx is a plain nginx error page, not the app's Problem Details JSON.
