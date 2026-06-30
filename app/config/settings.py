from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Server
    app_env: str = "development"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = Field(default=8000, gt=0, le=65535)
    api_v1_prefix: str = "/v1"
    workers: int = Field(default=1, ge=1)

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
    languages: str = "en"
    hf_token: str = ""

    @property
    def language_list(self) -> list[str]:
        langs = [v.strip().lower() for v in self.languages.split(",") if v.strip()]
        return langs or ["en"]

    # PocketTTS
    pocket_default_voice: str = "alba"

    # Audio / ffmpeg
    max_text_length: int = Field(default=2000, ge=1)
    ffmpeg_bin: str = "ffmpeg"

    @model_validator(mode="after")
    def validate_auth_and_providers(self) -> "Settings":
        if self.api_key_enabled and not self.api_key:
            raise ValueError("API_KEY must be set when API_KEY_ENABLED is true")
        providers = [p.strip() for p in self.enabled_providers.split(",")]
        if self.default_provider not in providers:
            raise ValueError(f"DEFAULT_PROVIDER '{self.default_provider}' not in ENABLED_PROVIDERS")
        return self


settings = Settings()
