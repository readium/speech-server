from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # .env: server/auth/concurrency/circuit-breaker — universal, provider-agnostic.
        # pocket-tts.env: PocketTTS-scoped install config. Optional — later providers get
        # their own file the same way; a missing file is silently skipped, not an error.
        env_file=(".env", "pocket-tts.env"),
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

    # Concurrency
    max_concurrent_syntheses: int = Field(default=2, ge=1)

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
        if self.app_env == "production" and not self.domain:
            raise ValueError("DOMAIN must be set when APP_ENV=production")
        return self


settings = Settings()
