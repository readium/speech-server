# Deployment

Automated: CI passes on `main` → `deploy.yml` builds + pushes the image to GHCR and
SSHes into the GCP VM to pull + restart. **Config (`.env`, `pocket-tts.env`) is
provisioned by the pipeline from GitHub Secrets — you never edit it on the VM by
hand, and you never run the wizard in production.** `configure.sh` is a *local /
first-time* convenience only.

## How config flows

```
local .env / pocket-tts.env / elevenlabs.env  ──base64──▶  GitHub Secrets  ──deploy.yml writes──▶  VM files  ──▶  containers
```

`.env`, `pocket-tts.env` and `elevenlabs.env` are gitignored (they hold secrets). The
GitHub secrets `DOTENV_B64` / `POCKET_TTS_ENV_B64` / `ELEVENLABS_ENV_B64` are the single
source of truth; the deploy job decodes them onto the VM before `docker compose up`.
`ELEVENLABS_ENV_B64` is optional — set it only when the ElevenLabs provider is enabled.

## One-time setup

### 1. Local — produce the env files
Generate them however you like (the wizard is easiest):
```bash
./scripts/configure.sh     # or hand-edit .env and pocket-tts.env
```
Then base64-encode each (copy the output):
```bash
base64 -i .env | pbcopy            # macOS; or:  base64 -w0 .env   (Linux)
base64 -i pocket-tts.env | pbcopy
base64 -i elevenlabs.env | pbcopy  # only if you use the ElevenLabs provider
```

### 2. GitHub — create the secrets
Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value |
|---|---|
| `DOTENV_B64` | base64 of your `.env` |
| `POCKET_TTS_ENV_B64` | base64 of your `pocket-tts.env` |
| `ELEVENLABS_ENV_B64` | base64 of your `elevenlabs.env` — **optional**, only when ElevenLabs is enabled. Leave unset to skip it (the file stays absent, which is fine). |
| `GCP_VM_HOST` / `GCP_VM_USER` / `GCP_SSH_PRIVATE_KEY` | VM SSH access (already set) |

### 3. VM — prepare once (no config edits)
```bash
git clone https://github.com/readium/speech-server ~/speech-server
# install docker + docker compose plugin
# if the GHCR image is private, authenticate so `docker compose pull` works:
echo "$GHCR_PAT" | docker login ghcr.io -u <user> --password-stdin
```
The `weights_cache` Docker volume persists across deploys, so models download only
once. Nginx serves TLS (see `nginx/` + `DOMAIN`).

## Changing config (any env var, add or edit) — the whole point

**No SSH, no wizard on the VM.** Update the source and redeploy:

1. Edit `.env` / `pocket-tts.env` / `elevenlabs.env` locally (or re-run the wizard).
2. Re-base64 and update the corresponding GitHub secret (`DOTENV_B64` /
   `POCKET_TTS_ENV_B64` / `ELEVENLABS_ENV_B64`).
3. Push to `main` (or re-run the **Build & Deploy** workflow). The deploy job
   rewrites the VM's env files and restarts.

Adding a *new* var is the same flow — it's just part of the file. `entrypoint.sh`
validates required vars at container start and fails fast if one is missing, so a
bad/incomplete secret is caught immediately: the new container exits and the deploy job
fails. (`docker compose up` has already replaced the old container by then, so the site is
down until the secret is fixed and redeployed.)

## Notes

- **Model/voice config** (`LANGUAGES`, `VOICE_LANGUAGES`) lives in `pocket-tts.env`.
  Changing it and redeploying triggers new downloads on next start (cached after);
  reclaim disk for removed ones with `make prune-models` (dry run), then
  `make prune-models-apply`, run on the VM. The same applies after a release that changes
  models (e.g. the move to the Kyutai 4.x models): the new weights download on first start and
  the old ones stay in the volume until pruned. The prune removes model folders that are no
  longer used; an older-revision copy of a folder that is still in use stays (wasted disk only).
- **Deploys wait for readiness:** the container healthcheck calls `/readyz` (models loaded),
  and the deploy runs `docker compose up -d --wait --wait-timeout 720`. If models fail to
  load (e.g. a Hugging Face download error) the deploy job fails instead of going green.
  The first start after a model change downloads weights, so `/readyz` is 503 for a few minutes.
- **CORS:** `CORS_ORIGINS` (in `.env`, so in the `DOTENV_B64` secret) lists the browser origins
  allowed to call the API. It defaults to `https://readium.org` (the Readium Speech demos).
  nginx lets `OPTIONS` through for the CORS preflight.
- **ElevenLabs spend cap:** set `ELEVENLABS_DAILY_CHAR_LIMIT` in `elevenlabs.env`. `0` means
  unlimited, and a production server logs a warning at startup if ElevenLabs is on with `0`.
  The counter is kept on the weights volume, so redeploys don't reset it.
- **Secrets vs non-secrets:** bundling both files as base64 secrets is the pragmatic
  choice for a single VM. To review config in PRs instead, graduate to a
  SOPS/age-encrypted env committed to the repo and decrypted at deploy.
- **Rollback:** images are tagged by commit SHA (`ghcr.io/readium/speech-server:<sha>`);
  pin that tag in compose and redeploy to roll back the app. Config rolls back by
  restoring the previous secret value.
