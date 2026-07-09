# Configuration

Run `make configure` to generate `.env` via an interactive wizard, or run `bash scripts/configure.sh` directly.

## Setup wizard

`make configure` handles both first-time setup and ongoing management:

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

> **macOS only.** The configure script auto-downloads [gum](https://github.com/charmbracelet/gum) for its menus. On Linux, install gum manually before running it.

## Environment variables

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

## RAM estimate

`WORKERS × active languages × ~240 MB`

Example: 2 workers, English + French = `2 × 2 × 240 MB ≈ 960 MB`

## Production vs development

First-time setup writes `APP_ENV=production` and prompts for `DOMAIN`. `make start` puts nginx in front as a reverse proxy; the app container has no published port.

For local dev, set `APP_ENV=development` in `.env` (`DOMAIN` becomes optional) and use `make dev-docker` — exposes `:8000` directly with no nginx.

nginx rate-limits `/v1/synthesize` (2 req/s, burst 4) and caps connections per IP. A `503` from behind nginx is a plain nginx error page, not the app's Problem Details JSON.
