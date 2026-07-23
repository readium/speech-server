from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # .env: server/auth/concurrency/circuit-breaker — universal, provider-agnostic.
        # pocket-tts.env / elevenlabs.env: provider-scoped config. Optional — each
        # provider gets its own file the same way; a missing file is silently skipped.
        env_file=(".env", "pocket-tts.env", "elevenlabs.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Server
    app_env: str = "development"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = Field(default=8000, gt=0, le=65535)
    workers: int = Field(default=1, ge=1)
    domain: str = ""

    # Auth (off by default for PoC)
    api_key_enabled: bool = False
    api_key: str = ""

    # Concurrency. Safe hardware-blind floor: 1 = never oversubscribe CPU. Each
    # synthesis uses ~2 cores (pocket-tts's generate→decode pipeline), so a 2-core box
    # thrashes at 2 under mixed-language load. configure.sh derives a higher value from
    # nproc/RAM for bigger hardware.
    max_concurrent_syntheses: int = Field(default=1, ge=1)

    # Providers
    enabled_providers: str = "pocket"
    default_provider: str = "pocket"

    # Languages (global; providers filter to their supported subset via active_languages())
    # Stored as comma-separated string to avoid pydantic-settings JSON-parsing list fields from env.
    # No hardcoded fallback: config is env-file driven (written by scripts/configure.sh). Unset =
    # empty = the provider loads no language models (no voices served), rather than silently
    # defaulting to English.
    languages: str = ""
    hf_token: str = ""

    @property
    def language_list(self) -> list[str]:
        return [v.strip().lower() for v in self.languages.split(",") if v.strip()]

    # PocketTTS. Empty = no server-side default voice; a request must name one.
    pocket_default_voice: str = ""

    # ElevenLabs (hosted HTTP provider). Only used when "elevenlabs" is in ENABLED_PROVIDERS.
    elevenlabs_api_key: str = ""
    elevenlabs_model_id: str = "eleven_multilingual_v2"
    # Languages are PROVIDER-SCOPED: ElevenLabs has its own set in elevenlabs.env, independent of
    # pocket's LANGUAGES. Empty = ElevenLabs serves no voices (like pocket's LANGUAGES unset).
    elevenlabs_languages: str = ""

    @property
    def elevenlabs_language_list(self) -> list[str]:
        return [v.strip().lower() for v in self.elevenlabs_languages.split(",") if v.strip()]

    elevenlabs_base_url: str = "https://api.elevenlabs.io"  # overridable for tests
    # Per-day usage cap so users can't spam the ElevenLabs API and burn credits. Counts CHARACTERS
    # sent, resets at UTC midnight. 0 = unlimited. Operators set ELEVENLABS_DAILY_CHAR_LIMIT in
    # elevenlabs.env — pick a value per the model's rate (https://elevenlabs.io/pricing/api;
    # flash/turbo bill half, so allow ~2× the characters for the same cost). Backed by a small JSON
    # file shared across workers (see app/core/daily_limit.py) so the cap is host-wide.
    elevenlabs_daily_char_limit: int = Field(default=0, ge=0)
    elevenlabs_usage_file: str = "/tmp/elevenlabs_usage.json"  # noqa: S108 — ephemeral counter; set a volume path to persist

    # Per-voice cross-language install config. Generic across providers. Format:
    # comma-separated "originalName:lang" pairs, "-" prefix to remove instead of add
    # (e.g. "alba:fr,alba:de,-javert:es"). Additions still bounded by `languages` (never
    # trigger a new base-model download) and must be a language that voice already
    # declares in its own otherLanguages. A bare "*:*" token means "every voice, every
    # declared otherLanguage that's enabled" (old install_mode="all"); its absence means
    # "primary only" (old install_mode="primary") — either way, explicit pairs in the
    # same list still layer on top as cherry-picks/prunes.
    voice_languages: str = ""

    @property
    def voice_install_all(self) -> bool:
        return any(p.strip() == "*:*" for p in self.voice_languages.split(","))

    @property
    def voice_language_add_map(self) -> dict[str, frozenset[str]]:
        return self._parse_voice_language_overrides()[0]

    @property
    def voice_language_remove_map(self) -> dict[str, frozenset[str]]:
        return self._parse_voice_language_overrides()[1]

    def _parse_voice_language_overrides(
        self,
    ) -> tuple[dict[str, frozenset[str]], dict[str, frozenset[str]]]:
        add: dict[str, set[str]] = {}
        remove: dict[str, set[str]] = {}
        for pair in self.voice_languages.split(","):
            pair = pair.strip()
            if not pair or pair == "*:*":
                continue
            target = add
            if pair.startswith("-"):
                target = remove
                pair = pair[1:]
            if ":" not in pair:
                continue
            voice, lang = pair.split(":", 1)
            voice, lang = voice.strip().lower(), lang.strip().lower()
            if voice and lang:
                target.setdefault(voice, set()).add(lang)
        return (
            {k: frozenset(v) for k, v in add.items()},
            {k: frozenset(v) for k, v in remove.items()},
        )

    # Audio / ffmpeg
    max_text_length: int = Field(default=2000, ge=1)
    ffmpeg_bin: str = "ffmpeg"

    # Circuit breaker (per provider, wraps synthesize() calls)
    circuit_breaker_enabled: bool = True
    circuit_breaker_failure_threshold: int = Field(default=5, ge=1)
    circuit_breaker_recovery_seconds: int = Field(default=30, ge=1)

    @model_validator(mode="after")
    def validate_auth_and_providers(self) -> "Settings":
        if self.api_key_enabled and not self.api_key:
            raise ValueError("API_KEY must be set when API_KEY_ENABLED is true")
        providers = [p.strip() for p in self.enabled_providers.split(",")]
        if self.default_provider not in providers:
            raise ValueError(f"DEFAULT_PROVIDER '{self.default_provider}' not in ENABLED_PROVIDERS")
        if "elevenlabs" in providers and not self.elevenlabs_api_key:
            raise ValueError(
                "ELEVENLABS_API_KEY must be set when 'elevenlabs' is in ENABLED_PROVIDERS"
            )
        if self.app_env == "production" and not self.domain:
            raise ValueError("DOMAIN must be set when APP_ENV=production")
        return self


settings = Settings()
