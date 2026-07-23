#!/usr/bin/env bash
# configure.sh — Readium Speech Server setup & management wizard
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"
POCKET_ENV_FILE="$REPO_ROOT/pocket-tts.env"
ELEVENLABS_ENV_FILE="$REPO_ROOT/elevenlabs.env"
VOICES_JSON="$REPO_ROOT/app/data/voices/pocket/voices.json"
POCKET_PLAN="$REPO_ROOT/scripts/pocket_plan.py"

# ── Colours ───────────────────────────────────────────────────────────────────
B=$'\033[1m' R=$'\033[0m' G=$'\033[32m' Y=$'\033[33m' C=$'\033[36m' RED=$'\033[31m'

ok()   { printf '%s✓%s %s\n' "$G" "$R" "$*"; }
warn() { printf '%s!%s %s\n' "$Y" "$R" "$*"; }
err()  { printf '%s✗%s %s\n' "$RED" "$R" "$*" >&2; }
hdr()  { echo; gum style --bold --foreground 212 "── $* ──"; echo; }
banner() { gum style --border rounded --border-foreground 212 --bold --padding "0 2" --margin "1 0" "Readium Speech Server"; }

# ── Portable env-file read/write ────────────────────────────────────────────────
# .env: server/auth/concurrency/circuit-breaker — universal, provider-agnostic.
# pocket-tts.env: PocketTTS-scoped install config (LANGUAGES, VOICE_LANGUAGES,
# POCKET_DEFAULT_VOICE). Future providers get their own file the same way.
# get_env/set_env target .env; get_penv/set_penv target pocket-tts.env — both
# built on the same generic _get_kv/_set_kv.
_get_kv() {
    grep -E "^${2}=" "$1" 2>/dev/null | cut -d= -f2- || true
}

_set_kv() {
    local file="$1" key="$2" val="$3" tmp
    if [[ ! -f "$file" ]]; then
        printf '%s=%s\n' "$key" "$val" >> "$file"
        return
    fi
    if grep -qE "^${key}=" "$file"; then
        tmp=$(mktemp)
        while IFS= read -r line; do
            if [[ "$line" == "${key}="* ]]; then
                printf '%s=%s\n' "$key" "$val"
            else
                printf '%s\n' "$line"
            fi
        done < "$file" > "$tmp"
        mv "$tmp" "$file"
    else
        printf '%s=%s\n' "$key" "$val" >> "$file"
    fi
}

get_env()  { _get_kv "$ENV_FILE" "$1"; }
set_env()  { _set_kv "$ENV_FILE" "$1" "$2"; }
get_penv() { _get_kv "$POCKET_ENV_FILE" "$1"; }
set_penv() { _set_kv "$POCKET_ENV_FILE" "$1" "$2"; }
get_eenv() { _get_kv "$ELEVENLABS_ENV_FILE" "$1"; }
set_eenv() { _set_kv "$ELEVENLABS_ENV_FILE" "$1" "$2"; }

# ENABLED_PROVIDERS is a comma list in .env. Add (dedup) / remove a provider id.
_providers_add() {
    local cur; cur=$(get_env ENABLED_PROVIDERS); cur="${cur:-pocket}"
    lang_list_to_set "${cur},$1"  # lang_list_to_set is a generic CSV dedup
}
_providers_remove() {
    local cur out="" p; cur=$(get_env ENABLED_PROVIDERS); cur="${cur:-pocket}"
    IFS=',' read -ra _p <<< "$cur"
    for p in "${_p[@]}"; do
        p="${p// /}"
        [[ -z "$p" || "$p" == "$1" ]] && continue
        out="${out:+${out},}${p}"
    done
    echo "$out"
}
_provider_enabled() {  # $1=id → "yes"/"no"
    case ",$(get_env ENABLED_PROVIDERS)," in *",$1,"*) echo yes ;; *) echo no ;; esac
}

# Hardware-derived defaults. pocket-tts uses ~2 CPU cores per synthesis (its
# generate→decode pipeline; docs: "Uses only 2 CPU cores") and each worker holds a
# full model copy (~2 GB for en+fr). So 1 worker ≈ 2 cores + ~2 GB RAM. Derive
# non-thrashing WORKERS / MAX_CONCURRENT_SYNTHESES from the box instead of shipping a
# static default that only fits one machine. Sets DETECTED_* and SUGGESTED_* globals.
_detect_hw() {
    local mem_bytes w_by_core w_by_ram
    if [[ "$(uname)" == "Darwin" ]]; then
        DETECTED_CORES=$(sysctl -n hw.ncpu 2>/dev/null || echo 2)
        mem_bytes=$(sysctl -n hw.memsize 2>/dev/null || echo 0)
        DETECTED_RAM_GB=$(( mem_bytes / 1024 / 1024 / 1024 ))
    else
        DETECTED_CORES=$(nproc 2>/dev/null || echo 2)
        DETECTED_RAM_GB=$(awk '/MemTotal/ {print int($2/1024/1024)}' /proc/meminfo 2>/dev/null || echo 0)
    fi
    [[ "$DETECTED_CORES"  -ge 1 ]] || DETECTED_CORES=1
    [[ "$DETECTED_RAM_GB" -ge 1 ]] || DETECTED_RAM_GB=2   # unknown RAM → assume one worker

    w_by_core=$(( DETECTED_CORES / 2 )); [[ "$w_by_core" -ge 1 ]] || w_by_core=1
    w_by_ram=$(( DETECTED_RAM_GB / 2 )); [[ "$w_by_ram"  -ge 1 ]] || w_by_ram=1
    SUGGESTED_WORKERS=$(( w_by_core < w_by_ram ? w_by_core : w_by_ram ))
}

# Per-worker concurrent syntheses that fit the box's cores without oversubscribing:
# total 2-core jobs (cores/2) spread across the chosen worker count. Args: <workers>.
_concurrency_for() {
    local c=$(( DETECTED_CORES / (2 * $1) ))
    [[ "$c" -ge 1 ]] && echo "$c" || echo 1
}

# ── Migrations (one-time, idempotent — safe to call every run) ─────────────────
_migrate_pocket_env() {
    [[ -f "$ENV_FILE" ]] || return 0
    [[ -f "$POCKET_ENV_FILE" ]] && return 0
    local langs mode voice
    langs=$(get_env LANGUAGES)
    mode=$(get_env VOICE_INSTALL_MODE)
    voice=$(get_env POCKET_DEFAULT_VOICE)
    [[ -z "$langs" && -z "$mode" && -z "$voice" ]] && return 0

    cat > "$POCKET_ENV_FILE" << EOF
# PocketTTS — provider-scoped install config. Migrated from .env by configure.sh.
LANGUAGES=${langs}
POCKET_DEFAULT_VOICE=${voice}
VOICE_LANGUAGES=$([ "$mode" = "all" ] && echo '*:*')
EOF
    chmod 600 "$POCKET_ENV_FILE"

    local tmp
    tmp=$(mktemp)
    grep -vE '^(LANGUAGES|VOICE_INSTALL_MODE|POCKET_DEFAULT_VOICE)=' "$ENV_FILE" > "$tmp"
    mv "$tmp" "$ENV_FILE"

    ok "Migrated LANGUAGES/VOICE_INSTALL_MODE/POCKET_DEFAULT_VOICE → pocket-tts.env"
}

# Earlier versions of this script wrote VOICE_INSTALL_MODE into pocket-tts.env
# directly (before it merged into the VOICE_LANGUAGES wildcard). Fold it in.
_migrate_voice_install_mode() {
    [[ -f "$POCKET_ENV_FILE" ]] || return 0
    local mode
    mode=$(get_penv VOICE_INSTALL_MODE)
    [[ -z "$mode" ]] && return 0

    if [[ "$mode" == "all" ]]; then
        set_penv VOICE_LANGUAGES "$(_voicelang_prepend_wildcard "$(get_penv VOICE_LANGUAGES)")"
    fi
    local tmp
    tmp=$(mktemp)
    grep -v '^VOICE_INSTALL_MODE=' "$POCKET_ENV_FILE" > "$tmp"
    mv "$tmp" "$POCKET_ENV_FILE"
    ok "Migrated VOICE_INSTALL_MODE → VOICE_LANGUAGES wildcard"
}

# ── Language helpers ──────────────────────────────────────────────────────────
ALL_LANGS=(en fr it de es pt)
BASE_LANGS=""  # protected language base while custom coverage is being edited

lang_name() {
    case "$1" in
        en) echo "English" ;;    fr) echo "French" ;;
        it) echo "Italian" ;;    de) echo "German" ;;
        es) echo "Spanish" ;;    pt) echo "Portuguese" ;;
        hi) echo "Hindi" ;;
        *)  echo "$1" ;;
    esac
}

current_langs() {
    local raw
    raw=$(get_penv LANGUAGES)
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

# Multi-select the language set, with a confirm-and-retry loop. ENTER is easy to
# hit reflexively before pressing SPACE to check anything — the confirm guards
# against a stray ENTER silently locking in an empty/wrong pick. Sets global
# PICKED_LANGS (not echoed — gum/confirm output would pollute a $(...) capture).
# $1 = fallback CSV used when nothing is checked (keep-current / "en").
_pick_languages() {
    PICKED_LANGS=""
    local fallback="${1:-en}"
    local lang_opts=() code
    for code in "${ALL_LANGS[@]}"; do
        lang_opts+=("$code — $(lang_name "$code")")
    done
    while true; do
        local choices=() line
        while IFS= read -r line; do
            [[ -n "$line" ]] && choices+=("$line")
        done < <(printf '%s\n' "${lang_opts[@]}" |
            gum choose --no-limit \
                --header "SPACE to check, ENTER when done (none checked → keep '$fallback')")

        local langs=""
        if [[ ${#choices[@]} -gt 0 ]]; then
            for line in "${choices[@]}"; do
                langs="${langs:+${langs},}${line%% —*}"
            done
        fi
        [[ -z "$langs" ]] && langs="$fallback"
        langs=$(lang_list_to_set "$langs")

        printf '\nSelected:\n'
        local c
        IFS=',' read -ra _codes <<< "$langs"
        for c in "${_codes[@]}"; do
            printf '  %s✓%s %s — %s\n' "$G" "$R" "$c" "$(lang_name "$c")"
        done
        if gum confirm "Use these languages?"; then
            PICKED_LANGS="$langs"
            return
        fi
        printf '\n'
    done
}

# ── VOICE_LANGUAGES helpers ──────────────────────────────────────────────────
# Comma-separated "originalName:lang" pairs; a leading "-" on a pair means remove
# instead of add, e.g. "alba:fr,alba:de,-javert:es". A bare "*:*" token means
# "every voice, every declared+enabled otherLanguage" (old install_mode=all).
_voicelang_upsert() {
    local list="$1" voice="$2" lang="$3" mode="$4" out="" p bare entry
    # bash 3.2 (macOS default) treats "${arr[@]}" on an empty array as unbound
    # under set -u — short-circuit rather than expand an array from "".
    if [[ -n "$list" ]]; then
        IFS=',' read -ra parts <<< "$list"
        for p in "${parts[@]}"; do
            [[ -z "$p" ]] && continue
            bare="${p#-}"
            [[ "$bare" != "${voice}:${lang}" ]] && out="${out:+${out},}${p}"
        done
    fi
    entry="${voice}:${lang}"
    [[ "$mode" == "remove" ]] && entry="-${entry}"
    [[ -z "$out" ]] && { echo "$entry"; return; }
    echo "${out},${entry}"
}

_voicelang_strip_wildcard() {
    local list="$1" out="" p
    if [[ -n "$list" ]]; then
        IFS=',' read -ra parts <<< "$list"
        for p in "${parts[@]}"; do
            [[ -z "$p" || "$p" == "*:*" ]] && continue
            out="${out:+${out},}${p}"
        done
    fi
    echo "$out"
}

_voicelang_prepend_wildcard() {
    local list
    list=$(_voicelang_strip_wildcard "$1")
    [[ -z "$list" ]] && { echo "*:*"; return; }
    echo "*:*,${list}"
}

# Prints "originalName|Display Name (gender, primaryLang)" per voice, one per
# line — e.g. "estelle|Estelle (female, fr)". Sorted primary-English voices
# first, then by language, matching how PocketTTS's own voice picker groups
# them (native-language voices called out distinctly from the English pool).
list_voice_choices() {
    python3 - "$VOICES_JSON" "${1:-}" << 'PY'
import json, sys
data = json.load(open(sys.argv[1]))
# Optional arg2: comma-separated enabled langs — restrict to installable voices
# (primary language selected). Empty/absent = no filter.
raw = sys.argv[2] if len(sys.argv) > 2 else ""
langs = {x.strip().lower() for x in raw.split(",") if x.strip()} or None
def sort_key(v):
    lang = v["language"].split("-")[0].lower()
    return (0 if lang == "en" else 1, lang, v["name"])
for v in sorted(data, key=sort_key):
    lang = v["language"].split("-")[0].lower()
    if langs is not None and lang not in langs:
        continue
    gender = v.get("gender") or "?"
    print(f'{v["originalName"]}|{v["name"]} ({gender}, {lang})')
PY
}

# Prints "primary|other1,other2,..." for a voice's originalName (case-insensitive
# match), empty if not found. Uses python3 (stdlib json) — more reliable than
# hand-rolled per-object regex extraction from multi-line JSON.
voice_info() {
    python3 - "$VOICES_JSON" "$1" << 'PY'
import json, sys
path, name = sys.argv[1], sys.argv[2].lower()
data = json.load(open(path))
for v in data:
    if v["originalName"].lower() == name:
        primary = v["language"].split("-")[0].lower()
        others = ",".join(l.split("-")[0].lower() for l in v.get("otherLanguages", []))
        print(f"{primary}|{others}")
        break
PY
}

# Sets global PICKED_VOICE (empty if cancelled/none found). Not returned via
# command substitution — warn()/gum output would otherwise get captured too.
# Shows each voice annotated with gender + primary language so the primary
# language is visible right in the picker, not just something you find out
# after adding a now-obviously-redundant override.
_pick_voice() {
    PICKED_VOICE=""
    local names=() displays=() line orig disp
    # All voices — custom can pull in a voice whose primary language isn't selected
    # yet (adding a pair for it extends LANGUAGES to include that primary).
    while IFS='|' read -r orig disp; do
        [[ -z "$orig" ]] && continue
        names+=("$orig")
        displays+=("$disp")
    done < <(list_voice_choices "")
    if [[ ${#names[@]} -eq 0 ]]; then
        warn "No installable voices for your selected languages ($(current_langs))."
        return
    fi
    local picked
    # Explicit exit row so you don't have to guess that ESC backs out.
    local back="‹ Back (done)"
    picked=$(printf '%s\n' "$back" "${displays[@]}" | gum choose --header "Voice (or Back)") || true
    [[ -z "$picked" || "$picked" == "$back" ]] && return
    local i
    for i in "${!displays[@]}"; do
        if [[ "${displays[$i]}" == "$picked" ]]; then
            PICKED_VOICE="${names[$i]}"
            return
        fi
    done
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
    local os_name
    os_name=$(uname -s)
    case "$os_name" in
        Darwin|Linux) ;;
        *)
            err "gum is not installed (used for this wizard's menus/prompts)."
            printf '  Install: https://github.com/charmbracelet/gum#installation\n\n'
            exit 1
            ;;
    esac

    warn "gum not found — downloading a local copy (no brew/sudo needed)..."
    local arch tag url tmp api_json
    arch=$(uname -m)
    [[ "$arch" == "arm64" || "$arch" == "aarch64" ]] && arch="arm64" || arch="x86_64"
    # Fetch into a variable first, then parse — piping curl straight into
    # `grep -m1` under pipefail lets grep close the pipe early, SIGPIPE-ing
    # curl and killing the script via set -e.
    api_json=$(curl -fsSL https://api.github.com/repos/charmbracelet/gum/releases/latest 2>/dev/null) || true
    tag=$(printf '%s' "$api_json" | grep -m1 '"tag_name"' | cut -d'"' -f4) || true
    tag="${tag:-v0.14.5}"
    url="https://github.com/charmbracelet/gum/releases/download/${tag}/gum_${tag#v}_${os_name}_${arch}.tar.gz"

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
        printf '  Install manually: https://github.com/charmbracelet/gum#installation\n\n'
        exit 1
    fi
}

# ══════════════════════════════════════════════════════════════════════════════
# First-time setup
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

    hdr "Step 1/5 — Languages"
    printf 'The languages PocketTTS installs voices for. English ships 21 voices; each\n'
    printf 'other language ships 1 native voice. Coverage (native vs cross-language)\n'
    printf 'is the next step. (Model sizes / RAM: see docs/configuration.md.)\n\n'
    _pick_languages "en"
    LANGS="$PICKED_LANGS"
    ok "Languages: $LANGS"

    # Persist pocket-tts.env now (with the chosen languages) so Step 2's coverage
    # picker can read/write it and compute the plan against real config.
    _write_pocket_env "$LANGS"

    hdr "Step 2/5 — Voice coverage"
    _set_coverage

    hdr "Step 3/5 — Workers & concurrency"
    _detect_hw
    ok "Detected: ${DETECTED_CORES} cores, ~${DETECTED_RAM_GB} GB RAM"
    WORKERS=$(gum input --placeholder "$SUGGESTED_WORKERS" \
        --header "Uvicorn workers (each ≈2 cores + ~2 GB RAM; suggested $SUGGESTED_WORKERS)") || true
    WORKERS="${WORKERS:-$SUGGESTED_WORKERS}"
    case "$WORKERS" in
        ''|*[!0-9]*|0) warn "Invalid — using $SUGGESTED_WORKERS"; WORKERS=$SUGGESTED_WORKERS ;;
    esac
    ok "Workers: $WORKERS"

    # Derive per-worker concurrency for the ACTUAL worker count chosen, so cores stay
    # ≈ workers × concurrency × 2 and never oversubscribe (which slows every request).
    MAX_CONCURRENT=$(_concurrency_for "$WORKERS")
    ok "Max concurrent syntheses/worker: $MAX_CONCURRENT (${DETECTED_CORES} cores ÷ 2 ÷ ${WORKERS} workers)"

    hdr "Step 4/5 — HuggingFace Token"
    HF_TOKEN=$(gum input --password --placeholder "hf_..." \
        --header "Get a free read-only token at: https://huggingface.co/settings/tokens") || true
    if [[ -z "$HF_TOKEN" ]]; then
        warn "No token entered — model downloads may be rate-limited until HF_TOKEN is set."
    else
        ok "Token recorded"
    fi

    hdr "Step 5/5 — Domain"
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
# Provider-specific config lives in its own env file — see pocket-tts.env
# (PocketTTS) and elevenlabs.env (ElevenLabs).

# ── Server ──
APP_ENV=production
LOG_LEVEL=INFO
HOST=0.0.0.0
PORT=8000
WORKERS=1
DOMAIN=

# ── Auth (off by default) ──
API_KEY_ENABLED=false
API_KEY=

# ── Concurrency ──
MAX_CONCURRENT_SYNTHESES=2

# ── Circuit breaker (per provider, wraps synthesize() calls) ──
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_RECOVERY_SECONDS=30

# ── Providers ──
ENABLED_PROVIDERS=pocket
DEFAULT_PROVIDER=pocket

# ── HuggingFace (shared across any provider that pulls models from HF) ──
HF_TOKEN=

# ── Audio / ffmpeg ──
FFMPEG_BIN=ffmpeg
MAX_TEXT_LENGTH=2000
EOF
    chmod 600 "$ENV_FILE"
    set_env WORKERS "$WORKERS"
    set_env MAX_CONCURRENT_SYNTHESES "$MAX_CONCURRENT"
    set_env HF_TOKEN "$HF_TOKEN"
    set_env DOMAIN "$DOMAIN_INPUT"

    ok "Written → .env, pocket-tts.env"
    _print_next_steps "$LANGS"
}

# Writes pocket-tts.env with the given LANGUAGES; coverage (VOICE_LANGUAGES) is
# set separately by _set_coverage. Called early in first-setup so the coverage
# step has a real config file to read/mutate.
_write_pocket_env() {
    local langs="$1"
    cat > "$POCKET_ENV_FILE" << 'EOF'
# PocketTTS — provider-scoped install config. Full details + model sizes:
# docs/configuration.md.
# LANGUAGES: comma BCP-47 prefixes — the languages to install voices for.
# VOICE_LANGUAGES: cross-language pairs added on top of the native defaults.
# Format: "originalName:lang", "-" prefix to remove (e.g. "alba:fr,-javert:es");
# a bare "*:*" = every voice in every selected language (the 'all' coverage mode).
LANGUAGES=en
POCKET_DEFAULT_VOICE=
VOICE_LANGUAGES=
EOF
    chmod 600 "$POCKET_ENV_FILE"
    set_penv LANGUAGES "$langs"
}

# ══════════════════════════════════════════════════════════════════════════════
# PocketTTS provider actions
# ══════════════════════════════════════════════════════════════════════════════

# Live install plan for the current LANGUAGES/VOICE_LANGUAGES/WORKERS. Delegates
# what-installs view via scripts/pocket_plan.py, which reuses the provider's own
# resolver — so this can never drift from what the server actually loads.
_show_plan() {
    local langs voice_lang
    langs=$(current_langs)
    voice_lang=$(get_penv VOICE_LANGUAGES)
    python3 "$POCKET_PLAN" "$VOICES_JSON" "$langs" "$voice_lang"
}

do_show_pocket_config() {
    hdr "PocketTTS Configuration"
    local default_voice
    default_voice=$(get_penv POCKET_DEFAULT_VOICE)
    printf '  %-24s %s%s%s\n' "Default voice:" "$C" "${default_voice:-(unset)}" "$R"
    _show_plan
    printf '\n'
}

# Step 1 of the flow: pick the language set. Whatever you check becomes LANGUAGES —
# the languages PocketTTS installs voices for. Reuses the trap-guarded picker.
_menu_change_languages() {
    hdr "Languages"
    local current new
    current=$(current_langs)
    printf 'Languages to install voices for. English has many voices; each other\n'
    printf 'language has one. Coverage (native vs cross-language) is the next step.\n'
    printf 'This REPLACES the current set. Currently: %s%s%s\n\n' "$C" "$current" "$R"
    _pick_languages "$current"
    new="$PICKED_LANGS"
    if [[ "$new" == "$current" ]]; then
        warn "Unchanged ($current)."
        return
    fi
    set_penv LANGUAGES "$new"
    ok "LANGUAGES updated → $new"
    printf '\n%sNote:%s new languages download on next start; removed ones stay on disk\n' "$Y" "$R"
    printf '(reclaim: %smake prune-models-apply%s). Restart to apply: %smake stop && make start%s\n\n' \
        "$C" "$R" "$C" "$R"
    _show_plan
    _show_plan
}

# Step 2 of the flow: choose how many voices/languages install. default and all
# work over your currently-selected languages; custom can pull in any voice and any
# of its languages, extending LANGUAGES to match (removes prune it back down).
_set_coverage() {
    hdr "Voice coverage"
    local langs
    langs=$(current_langs)
    printf 'Selected languages: %s%s%s\n\n' "$C" "$langs" "$R"
    printf '  default — one voice per selected language, in its own language only.\n'
    printf '  all     — every installed voice also speaks every OTHER selected language.\n'
    printf '  custom  — hand-pick any voice + any of its languages; LANGUAGES follows.\n\n'

    local COV
    COV=$(gum choose \
        "default — native voices only" \
        "all — every voice, every selected language" \
        "custom — per-voice, per-language (can add languages)" \
        "Cancel") || true
    case "$COV" in
        default*)
            set_penv VOICE_LANGUAGES ""
            ok "Coverage → default (native voices only)"
            ;;
        all*)
            set_penv VOICE_LANGUAGES "*:*"
            ok "Coverage → all (every voice, every selected language)"
            ;;
        custom*)
            # Custom derives LANGUAGES from the picks: snapshot the current selection
            # as the protected base (native voices you keep) — adds extend LANGUAGES,
            # removes prune back to this base. Drop any "*:*" so picks are explicit.
            BASE_LANGS=$(current_langs)
            set_penv VOICE_LANGUAGES "$(_voicelang_strip_wildcard "$(get_penv VOICE_LANGUAGES)")"
            _custom_voice_loop
            _custom_sync_languages
            ;;
        *) warn "Cancelled."; return ;;
    esac
    printf '\nNow: %sLANGUAGES=%s%s | %sVOICE_LANGUAGES=%s%s\n\n' \
        "$C" "$(current_langs)" "$R" "$C" "$(get_penv VOICE_LANGUAGES)" "$R"
    _show_plan
    printf '\nRestart to apply: %smake stop && make start%s\n\n' "$C" "$R"
}

# Prints one BCP-47 lang per line: every language this voice can ALSO speak (its
# declared otherLanguages, minus its own primary). Unbounded by LANGUAGES — custom
# can pull a new language in, and adding one syncs LANGUAGES to match.
_voice_xlang_candidates() {
    local voice="$1" info primary others l
    info=$(voice_info "$voice")
    IFS='|' read -r primary others <<< "$info"
    IFS=',' read -ra _o <<< "$others"
    for l in "${_o[@]}"; do
        [[ -z "$l" || "$l" == "$primary" ]] && continue
        echo "$l"
    done
}

# Languages the explicit VOICE_LANGUAGES pairs require: each pair's target language,
# plus the primary language of each pair's voice (a voice can't run without its own
# base model). Wildcard/removal tokens are ignored.
_langs_used_by_pairs() {
    local list="$1" p voice lang out=""
    [[ -z "$list" ]] && { echo ""; return; }
    IFS=',' read -ra _p <<< "$list"
    for p in "${_p[@]}"; do
        [[ -z "$p" || "$p" == "*:*" || "$p" == -* ]] && continue
        voice="${p%%:*}"; lang="${p#*:}"
        out="${out:+${out},}${lang},$(voice_info "$voice" | cut -d'|' -f1)"
    done
    lang_list_to_set "$out"
}

# Re-derive LANGUAGES = protected base (the selection when custom started) ∪ every
# language the current pairs require. Adds extend it; removes prune back to base.
_custom_sync_languages() {
    local base used
    base="${BASE_LANGS:-$(current_langs)}"
    used=$(_langs_used_by_pairs "$(get_penv VOICE_LANGUAGES)")
    set_penv LANGUAGES "$(lang_list_to_set "${base}${used:+,$used}")"
}

# Space-separated extra langs currently added for a voice (explicit non-removal
# pairs in VOICE_LANGUAGES). Custom mode has no "*:*", so these are the real adds.
_voice_added_langs() {
    local voice="$1" list p out=""
    list=$(get_penv VOICE_LANGUAGES)
    [[ -z "$list" ]] && return
    IFS=',' read -ra _p <<< "$list"
    for p in "${_p[@]}"; do
        [[ -z "$p" || "$p" == -* ]] && continue
        [[ "$p" == "${voice}:"* ]] && out="${out:+${out} }${p#*:}"
    done
    echo "$out"
}

# Delete any "voice:lang" pair (add or removal form) from a VOICE_LANGUAGES list.
_voicelang_delete() {
    local list="$1" voice="$2" lang="$3" out="" p bare
    [[ -z "$list" ]] && return
    IFS=',' read -ra _p <<< "$list"
    for p in "${_p[@]}"; do
        [[ -z "$p" ]] && continue
        bare="${p#-}"
        [[ "$bare" == "${voice}:${lang}" ]] && continue
        out="${out:+${out},}${p}"
    done
    echo "$out"
}

# Per-voice cross-language editor. All steps are single-select (ENTER picks the
# highlighted row) — no SPACE-to-check trap, no silent dead-ends.
_custom_voice_loop() {
    hdr "Custom cross-language"
    printf 'Pick any voice, then add/remove the languages it should speak. Adding a\n'
    printf 'language a voice needs pulls it into LANGUAGES automatically; removing it\n'
    printf 'prunes back to your base selection when nothing else needs it.\n\n'
    while true; do
        _pick_voice
        local voice="$PICKED_VOICE"
        [[ -z "$voice" ]] && { warn "Done."; return; }
        _custom_voice_one "$voice"
        gum confirm "Configure another voice?" || return
    done
}

_custom_voice_one() {
    local voice="$1" added primary ACT
    primary=$(voice_info "$voice" | cut -d'|' -f1)
    while true; do
        added=$(_voice_added_langs "$voice")
        printf '\n%s%s%s (native %s) — extra languages: %s%s%s\n' \
            "$B" "$voice" "$R" "$primary" "$C" "${added:-none}" "$R"
        ACT=$(gum choose "Add a language" "Remove a language" "Done (this voice)") || true
        case "$ACT" in
            "Add a language") _custom_add "$voice" ;;
            "Remove a language") _custom_remove "$voice" ;;
            *) return ;;
        esac
    done
}

_custom_add() {
    local voice="$1" cand=() added l pick
    added=" $(_voice_added_langs "$voice") "
    while IFS= read -r l; do
        [[ -z "$l" ]] && continue
        [[ "$added" == *" $l "* ]] && continue
        cand+=("$l — $(lang_name "$l")")
    done < <(_voice_xlang_candidates "$voice")
    if [[ ${#cand[@]} -eq 0 ]]; then
        warn "No more languages to add for '$voice'."
        return
    fi
    pick=$(printf '%s\n' "${cand[@]}" | gum choose --header "Add language for '$voice'") || true
    [[ -z "$pick" ]] && { warn "Cancelled."; return; }
    pick="${pick%% —*}"
    set_penv VOICE_LANGUAGES "$(_voicelang_upsert "$(get_penv VOICE_LANGUAGES)" "$voice" "$pick" add)"
    _custom_sync_languages
    ok "Added: $voice → $pick   (LANGUAGES now: $(current_langs))"
}

_custom_remove() {
    local voice="$1" cand=() l pick
    for l in $(_voice_added_langs "$voice"); do
        cand+=("$l — $(lang_name "$l")")
    done
    if [[ ${#cand[@]} -eq 0 ]]; then
        warn "'$voice' has no extra languages to remove."
        return
    fi
    pick=$(printf '%s\n' "${cand[@]}" | gum choose --header "Remove language for '$voice'") || true
    [[ -z "$pick" ]] && { warn "Cancelled."; return; }
    pick="${pick%% —*}"
    set_penv VOICE_LANGUAGES "$(_voicelang_delete "$(get_penv VOICE_LANGUAGES)" "$voice" "$pick")"
    _custom_sync_languages
    ok "Removed: $voice → $pick   (LANGUAGES now: $(current_langs))"
}

do_pocket_menu() {
    while true; do
        clear
        banner
        hdr "PocketTTS"

        do_show_pocket_config

        printf '\n  %sSteps:%s 1) set Languages first  2) pick Voice coverage.\n' "$B" "$R"
        printf '  Coverage: %sdefault%s = native voices only · %sall%s = every voice/language ·\n' \
            "$C" "$R" "$C" "$R"
        printf '  %scustom%s = default + cross-language pairs you add. Sizes/RAM: docs/configuration.md\n\n' \
            "$C" "$R"

        local OPT
        OPT=$(gum choose \
            "Languages" \
            "Voice coverage" \
            "Back") || true
        case "$OPT" in
            "Languages") _menu_change_languages ;;
            "Voice coverage") _set_coverage ;;
            *) return ;;
        esac
        printf '\nPress Enter to continue...'; read -r _
    done
}

# ══════════════════════════════════════════════════════════════════════════════
# ElevenLabs provider actions
# ══════════════════════════════════════════════════════════════════════════════

# elevenlabs.env — provider-scoped config, same pattern as pocket-tts.env. Only the
# provider-specific keys live here; universal keys (ENABLED_PROVIDERS etc.) stay in .env.
_write_elevenlabs_env() {
    cat > "$ELEVENLABS_ENV_FILE" << 'EOF'
# ElevenLabs — provider-scoped config. Generated by configure.sh.
# Only loaded/required when "elevenlabs" is in ENABLED_PROVIDERS (.env).
# ELEVENLABS_LANGUAGES is ElevenLabs' OWN language set (independent of pocket's LANGUAGES);
# empty = no ElevenLabs voices served.
# ELEVENLABS_DAILY_CHAR_LIMIT caps characters sent per day so users can't spam it; 0 = unlimited.
# Resets at 00:00 UTC. Pick a value per your model's rate — https://elevenlabs.io/pricing/api
# (flash/turbo bill half, so the same cost buys ~2× the characters).
ELEVENLABS_API_KEY=
ELEVENLABS_MODEL_ID=eleven_multilingual_v2
ELEVENLABS_LANGUAGES=
ELEVENLABS_DAILY_CHAR_LIMIT=0
EOF
    chmod 600 "$ELEVENLABS_ENV_FILE"
}

# ElevenLabs languages offered in the wizard — the set COMMON TO ALL models (model-independent),
# all free-tier usable. Mirrors _SUPPORTED_LANGUAGES in app/providers/elevenlabs.py.
EL_LANGS=(
    "ar — Arabic" "bg — Bulgarian" "cs — Czech" "da — Danish" "de — German" "el — Greek"
    "en — English" "es — Spanish" "fi — Finnish" "fil — Filipino" "fr — French" "hi — Hindi"
    "hr — Croatian" "id — Indonesian" "it — Italian" "ja — Japanese" "ko — Korean" "ms — Malay"
    "nl — Dutch" "pl — Polish" "pt — Portuguese" "ro — Romanian" "ru — Russian" "sk — Slovak"
    "sv — Swedish" "ta — Tamil" "tr — Turkish" "uk — Ukrainian" "zh — Chinese"
)

# Multi-select ElevenLabs languages → ELEVENLABS_LANGUAGES. Pre-checks the currently configured
# set so you edit from what's there, not a blank slate. Sets global PICKED_EL_LANGS.
_pick_el_languages() {
    PICKED_EL_LANGS=""
    local choices=() line langs="" sel="" code opt
    IFS=',' read -ra _cur <<< "$(get_eenv ELEVENLABS_LANGUAGES)"
    for code in "${_cur[@]}"; do
        code="${code// /}"; [[ -z "$code" ]] && continue
        for opt in "${EL_LANGS[@]}"; do
            [[ "${opt%% —*}" == "$code" ]] && sel="${sel:+${sel},}${opt}"
        done
    done
    while IFS= read -r line; do
        [[ -n "$line" ]] && choices+=("$line")
    done < <(printf '%s\n' "${EL_LANGS[@]}" |
        gum choose --no-limit ${sel:+--selected="$sel"} \
            --header "SPACE to toggle, ENTER when done")
    for line in "${choices[@]}"; do langs="${langs:+${langs},}${line%% —*}"; done
    PICKED_EL_LANGS=$(lang_list_to_set "$langs")
}

do_elevenlabs_menu() {
    while true; do
        clear; banner; hdr "ElevenLabs"
        local key model masked langs daily
        key=$(get_eenv ELEVENLABS_API_KEY)
        model=$(get_eenv ELEVENLABS_MODEL_ID); model="${model:-eleven_multilingual_v2}"
        langs=$(get_eenv ELEVENLABS_LANGUAGES)
        daily=$(get_eenv ELEVENLABS_DAILY_CHAR_LIMIT); daily="${daily:-0}"
        [[ -n "$key" ]] && masked="${key:0:4}****${key: -4}" || masked="(not set)"
        printf '  %-18s %s%s%s\n'   "Enabled:" "$C" "$(_provider_enabled elevenlabs)" "$R"
        printf '  %-18s %s%s%s\n'   "API key:" "$C" "$masked" "$R"
        printf '  %-18s %s%s%s\n'   "Model:"   "$C" "$model" "$R"
        printf '  %-18s %s%s%s\n'   "Languages:" "$C" "${langs:-(none — no voices served)}" "$R"
        printf '  %-18s %s%s%s\n\n' "Daily limit:" "$C" "$([ "$daily" = 0 ] && echo 'unlimited' || echo "$daily chars/day")" "$R"
        printf '  Voices: hosted API — no local models. Refresh the catalog from your\n'
        printf '  account with %sscripts/fetch_elevenlabs_voices.py%s.\n\n' "$C" "$R"

        local OPT
        OPT=$(gum choose "Set API key" "Set model" "Set languages" "Set daily limit" \
            "Enable provider" "Disable provider" "Back") || true
        case "$OPT" in
            "Set API key")
                local k
                k=$(gum input --password --placeholder "sk_..." \
                    --header "ElevenLabs API key (elevenlabs.io → profile → API key)") || true
                [[ -z "$k" ]] && { warn "No change."; }
                if [[ -n "$k" ]]; then
                    [[ -f "$ELEVENLABS_ENV_FILE" ]] || _write_elevenlabs_env
                    set_eenv ELEVENLABS_API_KEY "$k"
                    ok "API key saved → elevenlabs.env"
                fi ;;
            "Set model")
                local m
                printf 'Cost = credits/char (model sets the multiplier). flash/turbo v2.5 = 0.5×\n'
                printf '(cheapest); multilingual_v2 / v3 = 1×. Compare + current pricing:\n'
                printf '  %shttps://elevenlabs.io/docs/models%s  ·  %shttps://elevenlabs.io/pricing%s\n' \
                    "$C" "$R" "$C" "$R"
                printf '  (details: docs/providers/elevenlabs.md)\n\n'
                m=$(gum choose \
                    "eleven_multilingual_v2" "eleven_flash_v2_5" \
                    "eleven_turbo_v2_5" "eleven_v3" --header "Model") || true
                if [[ -n "$m" ]]; then
                    [[ -f "$ELEVENLABS_ENV_FILE" ]] || _write_elevenlabs_env
                    set_eenv ELEVENLABS_MODEL_ID "$m"
                    ok "Model → $m"
                fi ;;
            "Set languages")
                printf 'ElevenLabs languages (its own set, independent of pocket). Every voice\n'
                printf 'speaks all of them. Empty = no ElevenLabs voices served.\n\n'
                _pick_el_languages
                [[ -f "$ELEVENLABS_ENV_FILE" ]] || _write_elevenlabs_env
                set_eenv ELEVENLABS_LANGUAGES "$PICKED_EL_LANGS"
                ok "ElevenLabs languages → ${PICKED_EL_LANGS:-(none)}   (restart to apply)" ;;
            "Set daily limit")
                printf 'Max characters sent to ElevenLabs per day, so users can'"'"'t spam it.\n'
                printf '0 = unlimited. Resets 00:00 UTC. Pick per your model'"'"'s rate:\n'
                printf '  %shttps://elevenlabs.io/pricing/api%s (flash/turbo bill half → allow ~2× chars).\n\n' "$C" "$R"
                local d
                d=$(gum input --placeholder "$daily" --header "Daily character limit (0 = unlimited)") || true
                d="${d:-$daily}"
                case "$d" in
                    ''|*[!0-9]*) warn "Invalid — must be a whole number. Unchanged." ;;
                    *) [[ -f "$ELEVENLABS_ENV_FILE" ]] || _write_elevenlabs_env
                       set_eenv ELEVENLABS_DAILY_CHAR_LIMIT "$d"
                       ok "Daily limit → $([ "$d" = 0 ] && echo unlimited || echo "$d chars/day")   (restart to apply)" ;;
                esac ;;
            "Enable provider")
                if [[ -z "$(get_eenv ELEVENLABS_API_KEY)" ]]; then
                    warn "Set the API key first — the server refuses to start without it."
                else
                    set_env ENABLED_PROVIDERS "$(_providers_add elevenlabs)"
                    ok "elevenlabs enabled. Restart: make stop && make start"
                fi ;;
            "Disable provider")
                set_env ENABLED_PROVIDERS "$(_providers_remove elevenlabs)"
                # Keep DEFAULT_PROVIDER valid (settings validation rejects an unlisted default).
                [[ "$(get_env DEFAULT_PROVIDER)" == "elevenlabs" ]] && set_env DEFAULT_PROVIDER pocket
                ok "elevenlabs disabled." ;;
            *) return ;;
        esac
        printf '\nPress Enter to continue...'; read -r _
    done
}

# ══════════════════════════════════════════════════════════════════════════════
# Provider picker
# ══════════════════════════════════════════════════════════════════════════════

do_manage_provider() {
    hdr "Providers"
    local provider
    provider=$(gum choose "pocket" "elevenlabs" --header "Provider") || true
    [[ -z "$provider" ]] && { warn "Cancelled."; return; }
    case "$provider" in
        pocket) do_pocket_menu ;;
        elevenlabs) do_elevenlabs_menu ;;
    esac
}

# ══════════════════════════════════════════════════════════════════════════════
# Universal (.env) actions
# ══════════════════════════════════════════════════════════════════════════════

do_change_workers() {
    local current
    current=$(get_env WORKERS)
    current="${current:-1}"

    hdr "Change Workers"
    printf 'Current: %s%s%s workers. More workers = more throughput; each loads its own\n' \
        "$C" "$current" "$R"
    printf 'copy of the models, so RAM scales with worker count (sizes: see docs).\n\n'
    WORKERS=$(gum input --placeholder "$current" --header "New WORKERS") || true
    WORKERS="${WORKERS:-$current}"
    case "$WORKERS" in
        ''|*[!0-9]*|0) warn "Invalid — keeping $current"; return ;;
    esac
    set_env WORKERS "$WORKERS"
    ok "WORKERS updated → $WORKERS"
    printf 'Restart to apply: %smake stop && make start%s\n\n' "$C" "$R"
}

do_update_token() {
    hdr "Update HF_TOKEN"
    HF_TOKEN=$(gum input --password --placeholder "hf_..." \
        --header "Get a free read-only token at: https://huggingface.co/settings/tokens") || true
    [[ -z "$HF_TOKEN" ]] && { warn "Empty token — no change made."; return; }
    set_env HF_TOKEN "$HF_TOKEN"
    ok "HF_TOKEN updated in .env"
    printf 'Takes effect on next container start.\n\n'
}

do_show_config() {
    hdr "Current Configuration"
    local workers hf_token key_enabled max_syn
    workers=$(get_env WORKERS); workers="${workers:-1}"
    hf_token=$(get_env HF_TOKEN)
    key_enabled=$(get_env API_KEY_ENABLED); key_enabled="${key_enabled:-false}"
    max_syn=$(get_env MAX_CONCURRENT_SYNTHESES); max_syn="${max_syn:-2}"

    printf '  %-30s %s%s%s\n' "Workers:" "$C" "$workers" "$R"
    printf '  %-30s %s%s%s\n' "Max concurrent syntheses:" "$C" "$max_syn" "$R"

    if [[ -n "$hf_token" ]]; then
        local masked="${hf_token:0:4}****${hf_token: -4}"
        printf '  %-30s %s%s%s\n' "HF_TOKEN:" "$C" "$masked" "$R"
    else
        printf '  %-30s %s(not set)%s\n' "HF_TOKEN:" "$Y" "$R"
    fi

    printf '  %-30s %s%s%s\n' "API key auth:" "$C" "$key_enabled" "$R"
    printf '  %-30s %s%s%s\n' "Enabled providers:" "$C" "$(get_env ENABLED_PROVIDERS)" "$R"
    printf '\n  %sSee "Manage provider" for provider-specific config.%s\n' "$Y" "$R"
    printf '  Config files: %s, %s' "$ENV_FILE" "$POCKET_ENV_FILE"
    [[ -f "$ELEVENLABS_ENV_FILE" ]] && printf ', %s' "$ELEVENLABS_ENV_FILE"
    printf '\n\n'
}

do_reset() {
    hdr "Reset"
    warn "This will delete .env / pocket-tts.env / elevenlabs.env and stop the server."
    CHOICE=$(gum choose \
        "Delete config only (keep downloaded models)" \
        "Delete config AND purge all downloaded models (frees disk)" \
        "Cancel") || true

    case "$CHOICE" in
        "Delete config only"*)
            [[ -f "$ENV_FILE" ]] && rm "$ENV_FILE"
            [[ -f "$POCKET_ENV_FILE" ]] && rm "$POCKET_ENV_FILE"
            [[ -f "$ELEVENLABS_ENV_FILE" ]] && rm "$ELEVENLABS_ENV_FILE"
            ok "Config deleted"
            printf 'Run %sconfigure.sh%s to set up again.\n\n' "$C" "$R" ;;
        "Delete config AND purge"*)
            require_docker
            [[ -f "$ENV_FILE" ]] && rm "$ENV_FILE"
            [[ -f "$POCKET_ENV_FILE" ]] && rm "$POCKET_ENV_FILE"
            [[ -f "$ELEVENLABS_ENV_FILE" ]] && rm "$ELEVENLABS_ENV_FILE"
            ok "Config deleted"
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
        _migrate_pocket_env
        _migrate_voice_install_mode

        if [[ -f "$ENV_FILE" ]]; then
            local langs workers OPT
            langs=$(current_langs)
            workers=$(get_env WORKERS); workers="${workers:-1}"
            printf '  Current: languages=%s%s%s  workers=%s%s%s\n\n' \
                "$C" "$langs" "$R" "$C" "$workers" "$R"
            OPT=$(gum choose \
                "Show full config" \
                "Manage provider" \
                "Change workers" \
                "Update HF token" \
                "First-time setup (re-run / overwrite)" \
                "Reset" \
                "Quit") || true
            case "$OPT" in
                "Show full config") do_show_config ;;
                "Manage provider") do_manage_provider ;;
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
