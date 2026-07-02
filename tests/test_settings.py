import pytest

from app.config.settings import Settings


def test_production_requires_domain() -> None:
    with pytest.raises(ValueError, match="DOMAIN must be set"):
        Settings(app_env="production", domain="")


def test_production_with_domain_is_valid() -> None:
    settings = Settings(app_env="production", domain="tts.example.com")
    assert settings.domain == "tts.example.com"


def test_development_without_domain_is_valid() -> None:
    settings = Settings(app_env="development", domain="")
    assert settings.domain == ""
