import pytest

from app.config.settings import Settings


def _settings(**overrides: object) -> Settings:
    # _env_file=None: don't let this repo's real .env/pocket-tts.env leak into
    # tests expecting clean defaults — construct from kwargs only.
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


def test_production_requires_domain() -> None:
    with pytest.raises(ValueError, match="DOMAIN must be set"):
        _settings(app_env="production", domain="")


def test_production_with_domain_is_valid() -> None:
    settings = _settings(app_env="production", domain="tts.example.com")
    assert settings.domain == "tts.example.com"


def test_development_without_domain_is_valid() -> None:
    settings = _settings(app_env="development", domain="")
    assert settings.domain == ""


def test_voice_language_add_map_parses_unprefixed_pairs() -> None:
    settings = _settings(
        app_env="development", domain="", voice_languages="alba:fr,alba:de,Estelle:EN"
    )
    assert settings.voice_language_add_map == {
        "alba": frozenset({"fr", "de"}),
        "estelle": frozenset({"en"}),
    }
    assert settings.voice_language_remove_map == {}


def test_voice_language_remove_map_parses_minus_prefixed_pairs() -> None:
    settings = _settings(
        app_env="development", domain="", voice_languages="alba:fr,-javert:es,-javert:de"
    )
    assert settings.voice_language_add_map == {"alba": frozenset({"fr"})}
    assert settings.voice_language_remove_map == {"javert": frozenset({"es", "de"})}


def test_voice_language_maps_empty_by_default() -> None:
    settings = _settings(app_env="development", domain="")
    assert settings.voice_language_add_map == {}
    assert settings.voice_language_remove_map == {}


def test_voice_language_maps_ignore_malformed_entries() -> None:
    settings = _settings(
        app_env="development", domain="", voice_languages="alba:fr,malformed,:missing,x:,-"
    )
    assert settings.voice_language_add_map == {"alba": frozenset({"fr"})}
    assert settings.voice_language_remove_map == {}


def test_voice_install_all_false_by_default() -> None:
    settings = _settings(app_env="development", domain="")
    assert settings.voice_install_all is False


def test_voice_install_all_true_with_wildcard() -> None:
    settings = _settings(app_env="development", domain="", voice_languages="*:*")
    assert settings.voice_install_all is True


def test_voice_install_all_wildcard_coexists_with_overrides() -> None:
    settings = _settings(app_env="development", domain="", voice_languages="*:*,-javert:es")
    assert settings.voice_install_all is True
    assert settings.voice_language_remove_map == {"javert": frozenset({"es"})}
    assert settings.voice_language_add_map == {}  # "*:*" itself is not a voice:lang pair
