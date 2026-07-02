#!/usr/bin/env bash
# configure.sh — Readium Speech Server setup & management wizard
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"

# ── Colours ───────────────────────────────────────────────────────────────────
B=$'\033[1m' R=$'\033[0m' G=$'\033[32m' Y=$'\033[33m' C=$'\033[36m' RED=$'\033[31m'

ok()   { printf '%s✓%s %s\n' "$G" "$R" "$*"; }
warn() { printf '%s!%s %s\n' "$Y" "$R" "$*"; }
err()  { printf '%s✗%s %s\n' "$RED" "$R" "$*" >&2; }
hdr()  { echo; gum style --bold --foreground 212 "── $* ──"; echo; }
banner() { gum style --border rounded --border-foreground 212 --bold --padding "0 2" --margin "1 0" "Readium Speech Server"; }

# ── Portable .env read/write ──────────────────────────────────────────────────
get_env() {
    grep -E "^${1}=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true
}

set_env() {
    local key="$1" val="$2" tmp
    if [[ ! -f "$ENV_FILE" ]]; then
        printf '%s=%s\n' "$key" "$val" >> "$ENV_FILE"
        return
    fi
    if grep -qE "^${key}=" "$ENV_FILE"; then
        tmp=$(mktemp)
        while IFS= read -r line; do
            if [[ "$line" == "${key}="* ]]; then
                printf '%s=%s\n' "$key" "$val"
            else
                printf '%s\n' "$line"
            fi
        done < "$ENV_FILE" > "$tmp"
        mv "$tmp" "$ENV_FILE"
    else
        printf '%s=%s\n' "$key" "$val" >> "$ENV_FILE"
    fi
}

# ── Language helpers ──────────────────────────────────────────────────────────
ALL_LANGS=(en fr it de es pt)

lang_name() {
    case "$1" in
        en) echo "English" ;;    fr) echo "French" ;;
        it) echo "Italian" ;;    de) echo "German" ;;
        es) echo "Spanish" ;;    pt) echo "Portuguese" ;;
        *)  echo "$1" ;;
    esac
}

current_langs() {
    local raw
    raw=$(get_env LANGUAGES)
    echo "${raw:-en}"
}

lang_list_to_set() {
    local out="" p
    IFS=',' read -ra parts <<< "$1"
    for p in "${parts[@]}"; do
        p="${p// /}"
        if [[ -n "$p" ]] && ! echo ",${out}," | grep -qF ",${p},"; then
            out="${out:+${out},}${p}"
        fi
    done
    echo "$out"
}

# ── Docker check ──────────────────────────────────────────────────────────────
require_docker() {
    if ! command -v docker &>/dev/null; then
        err "Docker is not installed."
        printf '  Install: https://www.docker.com/products/docker-desktop\n\n'
        exit 1
    fi
}

# ── gum check (interactive UI: menus/prompts/spinners) ─────────────────────────
# No brew/sudo required: falls back to downloading a local static binary
# straight from GitHub releases into $REPO_ROOT/.bin, used only for this
# script's own PATH.
GUM_BIN_DIR="$REPO_ROOT/.bin"
GUM_BIN="$GUM_BIN_DIR/gum"

require_gum() {
    if command -v gum &>/dev/null; then
        return
    fi
    if [[ -x "$GUM_BIN" ]]; then
        export PATH="$GUM_BIN_DIR:$PATH"
        return
    fi
    if [[ "$(uname -s)" != "Darwin" ]]; then
        err "gum is not installed (used for this wizard's menus/prompts)."
        printf '  Install: https://github.com/charmbracelet/gum#installation\n\n'
        exit 1
    fi

    warn "gum not found — downloading a local copy (no brew/sudo needed)..."
    local arch tag url tmp api_json
    arch=$(uname -m)
    [[ "$arch" == "arm64" ]] || arch="x86_64"
    # Fetch into a variable first, then parse — piping curl straight into
    # `grep -m1` under pipefail lets grep close the pipe early, SIGPIPE-ing
    # curl and killing the script via set -e.
    api_json=$(curl -fsSL https://api.github.com/repos/charmbracelet/gum/releases/latest 2>/dev/null) || true
    tag=$(printf '%s' "$api_json" | grep -m1 '"tag_name"' | cut -d'"' -f4) || true
    tag="${tag:-v0.14.5}"
    url="https://github.com/charmbracelet/gum/releases/download/${tag}/gum_${tag#v}_Darwin_${arch}.tar.gz"

    mkdir -p "$GUM_BIN_DIR"
    tmp=$(mktemp -d)
    if curl -fsSL "$url" -o "$tmp/gum.tar.gz" 2>/dev/null && tar -xzf "$tmp/gum.tar.gz" -C "$tmp"; then
        find "$tmp" -type f -name gum -exec mv {} "$GUM_BIN" \;
        chmod +x "$GUM_BIN"
        rm -rf "$tmp"
        export PATH="$GUM_BIN_DIR:$PATH"
        ok "gum installed → $GUM_BIN"
    else
        rm -rf "$tmp"
        err "Auto-download failed."
        printf '  Install manually: brew install gum\n'
        printf '  or see: https://github.com/charmbracelet/gum#installation\n\n'
        exit 1
    fi
}

# ══════════════════════════════════════════════════════════════════════════════
# Actions
# ══════════════════════════════════════════════════════════════════════════════

do_first_setup() {
    require_docker

    if [[ -f "$ENV_FILE" ]]; then
        warn ".env already exists."
        CHOICE=$(gum choose "Overwrite" "Backup (.env → .env.backup) then overwrite" "Cancel") || true
        case "$CHOICE" in
            "Overwrite") ;;
            "Backup"*) cp "$ENV_FILE" "${ENV_FILE}.backup"
               ok "Backed up → .env.backup" ;;
            *) printf 'Cancelled.\n'; return ;;
        esac
    fi

    hdr "Step 1/4 — Languages"
    local lang_opts=()
    for code in "${ALL_LANGS[@]}"; do
        lang_opts+=("$code — $(lang_name "$code")")
    done

    # Enter is easy to hit reflexively (it's the "confirm" key in most menus)
    # before pressing Space to actually check anything — confirm-and-retry
    # loop so a stray Enter doesn't silently lock in the wrong selection.
    while true; do
        local choices=()
        # mapfile is bash4+ only; macOS ships bash 3.2 by default. Portable read loop instead.
        while IFS= read -r line; do
            [[ -n "$line" ]] && choices+=("$line")
        done < <(printf '%s\n' "${lang_opts[@]}" |
            gum choose --no-limit \
                --header "SPACE to check a language, then ENTER when done (default: English if none checked)")

        LANGS=""
        # bash 3.2 (macOS default) treats "${arr[@]}" on an empty array as unbound
        # under set -u — check length first rather than expanding directly.
        if [[ ${#choices[@]} -gt 0 ]]; then
            for choice in "${choices[@]}"; do
                LANGS="${LANGS:+${LANGS},}${choice%% —*}"
            done
        fi
        [[ -z "$LANGS" ]] && LANGS="en"
        LANGS=$(lang_list_to_set "$LANGS")

        printf '\nSelected:\n'
        IFS=',' read -ra _selected_codes <<< "$LANGS"
        for code in "${_selected_codes[@]}"; do
            printf '  %s✓%s %s — %s\n' "$G" "$R" "$code" "$(lang_name "$code")"
        done

        if gum confirm "Use these languages?"; then
            break
        fi
        printf '\n'
    done
    ok "Languages: $LANGS"

    hdr "Step 2/4 — Workers"
    WORKERS=$(gum input --placeholder "1" \
        --header "RAM per worker = ~240 MB × number of languages loaded") || true
    WORKERS="${WORKERS:-1}"
    case "$WORKERS" in
        ''|*[!0-9]*|0) warn "Invalid — using 1"; WORKERS=1 ;;
    esac
    ok "Workers: $WORKERS"

    hdr "Step 3/4 — HuggingFace Token"
    HF_TOKEN=$(gum input --password --placeholder "hf_..." \
        --header "Get a free read-only token at: https://huggingface.co/settings/tokens") || true
    if [[ -z "$HF_TOKEN" ]]; then
        warn "No token entered — model downloads may be rate-limited until HF_TOKEN is set."
    else
        ok "Token recorded"
    fi

    hdr "Step 4/4 — Domain"
    DOMAIN_INPUT=$(gum input --placeholder "tts.example.com" \
        --header "Domain name nginx/FastAPI will serve") || true
    if [[ -z "$DOMAIN_INPUT" ]]; then
        err "DOMAIN is required in production mode."
        exit 1
    fi
    ok "Domain: $DOMAIN_INPUT"

    cat > "$ENV_FILE" << 'EOF'
# Readium Speech Server — environment variables
# Generated by configure.sh — edit manually or re-run configure.sh

# ── Server ──
APP_ENV=production
LOG_LEVEL=INFO
HOST=0.0.0.0
PORT=8000
API_V1_PREFIX=/v1
WORKERS=1
DOMAIN=

# ── Auth (off by default) ──
API_KEY_ENABLED=false
API_KEY=

# ── Concurrency ──
MAX_CONCURRENT_SYNTHESES=2

# ── Languages (comma-separated BCP-47 prefixes; PocketTTS: en,fr,it,de,es,pt) ──
# Each language downloads ~240 MB on first start into the weights Docker volume.
LANGUAGES=en
HF_TOKEN=

# ── Providers ──
ENABLED_PROVIDERS=pocket
DEFAULT_PROVIDER=pocket

# ── PocketTTS ──
POCKET_DEFAULT_VOICE=alba

# ── Audio / ffmpeg ──
FFMPEG_BIN=ffmpeg
MAX_TEXT_LENGTH=2000
EOF
    chmod 600 "$ENV_FILE"
    set_env LANGUAGES "$LANGS"
    set_env WORKERS   "$WORKERS"
    set_env HF_TOKEN  "$HF_TOKEN"
    set_env DOMAIN    "$DOMAIN_INPUT"

    ok "Written → .env"
    _print_next_steps "$LANGS"
}

do_add_language() {
    _require_env
    local current
    current=$(current_langs)

    hdr "Add Language"
    local available=() code choice
    for code in "${ALL_LANGS[@]}"; do
        if ! echo "$current" | grep -qE "(^|,)${code}(,|$)"; then
            available+=("$code — $(lang_name "$code")")
        fi
    done
    if [[ ${#available[@]} -eq 0 ]]; then
        warn "All supported languages are already enabled."
        return
    fi
    choice=$(printf '%s\n' "${available[@]}" | gum choose --header "Language to add") || true
    if [[ -z "$choice" ]]; then
        warn "Cancelled."
        return
    fi
    code="${choice%% —*}"
    local new
    new=$(lang_list_to_set "${current},${code}")
    set_env LANGUAGES "$new"
    ok "LANGUAGES updated → $new"
    printf '\n%sRestart the server to load the new language:%s\n' "$B" "$R"
    printf '  make stop && make start\n\n'
    printf '%sNote:%s first start downloads ~240 MB for %s%s%s. Cached after that.\n\n' \
        "$Y" "$R" "$B" "$code" "$R"
}

do_remove_language() {
    _require_env
    local current
    current=$(current_langs)
    IFS=',' read -ra parts <<< "$current"

    if [[ ${#parts[@]} -eq 1 ]]; then
        err "Only one language configured (${current}). Cannot remove — server needs at least one."
        return
    fi

    hdr "Remove Language"
    local options=() p code choice
    for p in "${parts[@]}"; do
        options+=("$p — $(lang_name "$p")")
    done
    choice=$(printf '%s\n' "${options[@]}" | gum choose --header "Language to remove") || true
    if [[ -z "$choice" ]]; then
        warn "Cancelled."
        return
    fi
    code="${choice%% —*}"

    local new="" p2
    for p2 in "${parts[@]}"; do
        [[ "$p2" != "$code" ]] && new="${new:+${new},}${p2}"
    done
    set_env LANGUAGES "$new"
    ok "LANGUAGES updated → $new"
    printf '\n%sNote:%s model files for %s remain in the Docker volume (disk space not freed).\n' \
        "$Y" "$R" "$code"
    printf 'To reclaim disk: %smake stop && docker volume rm speech-server_weights_cache && make start%s\n' \
        "$C" "$R"
    printf '(Re-downloads active languages: %s)\n\n' "$new"
    printf 'Restart to apply: %smake stop && make start%s\n\n' "$C" "$R"
}

do_change_workers() {
    _require_env
    local current
    current=$(get_env WORKERS)
    current="${current:-1}"

    hdr "Change Workers"
    local langs
    langs=$(current_langs)
    local lang_count
    lang_count=$(echo "$langs" | tr ',' '\n' | wc -l | tr -d ' ')
    printf 'Current: %s%s%s workers | RAM per worker: ~%d MB (%d language(s) × 240 MB)\n\n' \
        "$C" "$current" "$R" $((lang_count * 240)) "$lang_count"
    WORKERS=$(gum input --placeholder "$current" --header "New WORKERS") || true
    WORKERS="${WORKERS:-$current}"
    case "$WORKERS" in
        ''|*[!0-9]*|0) warn "Invalid — keeping $current"; return ;;
    esac
    set_env WORKERS "$WORKERS"
    ok "WORKERS updated → $WORKERS"
    local total_ram=$(( lang_count * 240 * WORKERS ))
    printf 'Estimated RAM: ~%d MB (%d workers × %d languages × 240 MB)\n\n' \
        "$total_ram" "$WORKERS" "$lang_count"
    printf 'Restart to apply: %smake stop && make start%s\n\n' "$C" "$R"
}

do_update_token() {
    _require_env

    hdr "Update HF_TOKEN"
    HF_TOKEN=$(gum input --password --placeholder "hf_..." \
        --header "Get a free read-only token at: https://huggingface.co/settings/tokens") || true
    [[ -z "$HF_TOKEN" ]] && { warn "Empty token — no change made."; return; }
    set_env HF_TOKEN "$HF_TOKEN"
    ok "HF_TOKEN updated in .env"
    printf 'Takes effect on next container start.\n\n'
}

do_show_config() {
    _require_env

    hdr "Current Configuration"
    local langs workers hf_token key_enabled api_key max_syn
    langs=$(current_langs)
    workers=$(get_env WORKERS); workers="${workers:-1}"
    hf_token=$(get_env HF_TOKEN)
    key_enabled=$(get_env API_KEY_ENABLED); key_enabled="${key_enabled:-false}"
    max_syn=$(get_env MAX_CONCURRENT_SYNTHESES); max_syn="${max_syn:-2}"

    printf '  %-30s %s%s%s\n' "Languages:" "$C" "$langs" "$R"

    local lang_count
    lang_count=$(echo "$langs" | tr ',' '\n' | wc -l | tr -d ' ')
    local total_ram=$(( lang_count * 240 * workers ))

    printf '  %-30s %s%s%s  (~%d MB total RAM)\n' \
        "Workers:" "$C" "$workers" "$R" "$total_ram"
    printf '  %-30s %s%s%s\n' "Max concurrent syntheses:" "$C" "$max_syn" "$R"

    if [[ -n "$hf_token" ]]; then
        local masked="${hf_token:0:4}****${hf_token: -4}"
        printf '  %-30s %s%s%s\n' "HF_TOKEN:" "$C" "$masked" "$R"
    else
        printf '  %-30s %s(not set)%s\n' "HF_TOKEN:" "$Y" "$R"
    fi

    printf '  %-30s %s%s%s\n' "API key auth:" "$C" "$key_enabled" "$R"
    printf '\n  Config file: %s\n\n' "$ENV_FILE"
}

do_reset() {
    hdr "Reset"
    warn "This will delete .env and stop the server."
    CHOICE=$(gum choose \
        "Delete .env only (keep downloaded models)" \
        "Delete .env AND purge all downloaded models (frees disk)" \
        "Cancel") || true

    case "$CHOICE" in
        "Delete .env only"*)
            [[ -f "$ENV_FILE" ]] && rm "$ENV_FILE" && ok ".env deleted"
            printf 'Run %sconfigure.sh%s to set up again.\n\n' "$C" "$R" ;;
        "Delete .env AND purge"*)
            require_docker
            [[ -f "$ENV_FILE" ]] && rm "$ENV_FILE" && ok ".env deleted"
            local vol
            vol=$(docker volume ls -q | grep -E 'weights_cache$' | head -1 || true)
            if [[ -n "$vol" ]]; then
                # stop containers using the volume first
                docker compose -f "$REPO_ROOT/docker-compose.yml" down 2>/dev/null || true
                docker volume rm "$vol" && ok "Volume '$vol' removed (models purged)"
            else
                warn "No weights_cache volume found — models already gone or never downloaded"
            fi
            printf 'Run %sconfigure.sh%s then %smake build && make start%s.\n\n' \
                "$C" "$R" "$C" "$R" ;;
        *)
            printf 'Cancelled.\n\n' ;;
    esac
}

# ── Helpers ───────────────────────────────────────────────────────────────────
_require_env() {
    if [[ ! -f "$ENV_FILE" ]]; then
        err ".env not found. Run option 1 (first-time setup) first."
        exit 1
    fi
}

_print_next_steps() {
    local langs="$1"
    printf '\n%sAvailable commands:%s\n\n' "$B" "$R"
    (cd "$REPO_ROOT" && make help)
    printf '\n%sNote:%s first startup downloads voice models for: %s%s%s\n' \
        "$Y" "$R" "$B" "$langs" "$R"
    printf 'Subsequent starts are instant — models cached in Docker volume.\n\n'
    printf '%sNote:%s .env defaults to APP_ENV=production. For local dev, edit\n' "$Y" "$R"
    printf '.env and set %sAPP_ENV=development%s (DOMAIN then becomes optional).\n\n' "$C" "$R"
}

# ══════════════════════════════════════════════════════════════════════════════
# Main menu
# ══════════════════════════════════════════════════════════════════════════════

main_menu() {
    while true; do
        clear
        banner

        if [[ -f "$ENV_FILE" ]]; then
            local langs workers OPT
            langs=$(current_langs)
            workers=$(get_env WORKERS); workers="${workers:-1}"
            printf '  Current: languages=%s%s%s  workers=%s%s%s\n\n' \
                "$C" "$langs" "$R" "$C" "$workers" "$R"
            OPT=$(gum choose \
                "Show full config" \
                "Add a language" \
                "Remove a language" \
                "Change workers" \
                "Update HF token" \
                "First-time setup (re-run / overwrite)" \
                "Reset" \
                "Quit") || true
            case "$OPT" in
                "Show full config") do_show_config ;;
                "Add a language") do_add_language ;;
                "Remove a language") do_remove_language ;;
                "Change workers") do_change_workers ;;
                "Update HF token") do_update_token ;;
                "First-time setup"*) do_first_setup ;;
                "Reset") do_reset ;;
                *) printf '\n'; exit 0 ;;
            esac
            printf '\nPress Enter to continue...'; read -r _
        else
            local OPT
            printf '  No .env found.\n\n'
            OPT=$(gum choose "First-time setup" "Quit") || true
            case "$OPT" in
                "First-time setup") do_first_setup ;;
                *) printf '\n'; exit 0 ;;
            esac
            printf '\nPress Enter to continue...'; read -r _
        fi
    done
}

require_gum
main_menu
