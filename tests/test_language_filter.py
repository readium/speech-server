"""Fast unit tests for language filtering logic — no model download required."""

import json
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import PropertyMock, patch

import pytest

from app.config.settings import Settings

_POCKET_JSON = Path(__file__).parent.parent / "app" / "data" / "voices" / "pocket" / "voices.json"
_SUPPORTED = {"en", "fr", "it", "de", "es", "pt"}


@contextmanager
def language_config(*langs: str) -> Generator[None, None, None]:
    """Temporarily override settings.language_list for a block."""
    with patch.object(
        Settings, "language_list", new_callable=PropertyMock, return_value=list(langs)
    ):  # noqa: E501
        yield


# ── pocket.json data integrity ──────────────────────────────────────────────


def test_pocket_json_covers_all_supported_languages() -> None:
    voices = json.loads(_POCKET_JSON.read_text())
    present = {v["language"].split("-")[0].lower() for v in voices}
    assert present == _SUPPORTED


def test_pocket_json_english_voice_count() -> None:
    voices = json.loads(_POCKET_JSON.read_text())
    en = [v for v in voices if v["language"].split("-")[0].lower() == "en"]
    assert len(en) == 26  # all 26 voices under language "en"


def test_pocket_json_non_english_languages_each_have_voices() -> None:
    voices = json.loads(_POCKET_JSON.read_text())
    by_lang: dict[str, int] = {}
    for v in voices:
        lang = v["language"].split("-")[0].lower()
        by_lang[lang] = by_lang.get(lang, 0) + 1
    for lang in _SUPPORTED - {"en"}:
        assert by_lang.get(lang, 0) >= 1, f"No voices for language: {lang}"


def test_pocket_json_all_voices_have_required_fields() -> None:
    required = {
        "source",
        "label",
        "name",
        "originalName",
        "voiceURI",
        "language",
        "provider",
        "engineVoiceId",
        "sampleRate",
        "mimeTypes",
    }
    for v in json.loads(_POCKET_JSON.read_text()):
        missing = required - v.keys()
        assert not missing, f"{v.get('voiceURI')} missing: {missing}"


# ── active_languages() intersection logic ────────────────────────────────────


def test_active_languages_single() -> None:
    from app.providers.pocket_tts import PocketTTSProvider

    with language_config("en"):
        assert PocketTTSProvider().active_languages() == {"en"}


def test_active_languages_multiple() -> None:
    from app.providers.pocket_tts import PocketTTSProvider

    with language_config("en", "fr", "de"):
        assert PocketTTSProvider().active_languages() == {"en", "fr", "de"}


def test_active_languages_unsupported_lang_excluded() -> None:
    from app.providers.pocket_tts import PocketTTSProvider

    with language_config("en", "zh"):
        assert PocketTTSProvider().active_languages() == {"en"}  # zh not supported


def test_active_languages_all_unsupported_returns_empty() -> None:
    from app.providers.pocket_tts import PocketTTSProvider

    with language_config("zh", "ar"):
        assert PocketTTSProvider().active_languages() == frozenset()


# ── list_voices() filtering (no model load — injects Voice objects directly) ─


def _loaded_provider(*langs: str):  # type: ignore[no-untyped-def]
    """Return a PocketTTSProvider with all pocket.json voices pre-injected."""
    from app.providers.pocket_tts import PocketTTSProvider
    from app.schemas.voice import Voice

    provider = PocketTTSProvider()
    provider._voices = [Voice(**v) for v in json.loads(_POCKET_JSON.read_text())]  # noqa: SLF001
    return provider, langs


@pytest.mark.asyncio
async def test_list_voices_filters_to_single_language() -> None:
    provider, langs = _loaded_provider("fr")
    with language_config(*langs):
        result = await provider.list_voices()
    assert {v.language.split("-")[0].lower() for v in result} == {"fr"}
    assert len(result) == 26  # all 26 voices available in French


@pytest.mark.asyncio
async def test_list_voices_multiple_languages() -> None:
    provider, langs = _loaded_provider("en", "fr")
    with language_config(*langs):
        result = await provider.list_voices()
    langs_in_result = {v.language.split("-")[0].lower() for v in result}
    assert langs_in_result == {"en", "fr"}
    assert len(result) == 52  # 26 en + 26 fr


@pytest.mark.asyncio
async def test_list_voices_all_languages_returns_all() -> None:
    provider, langs = _loaded_provider(*_SUPPORTED)
    with language_config(*langs):
        result = await provider.list_voices()
    assert len(result) == 156  # 26 voices × 6 languages


@pytest.mark.asyncio
async def test_list_voices_unsupported_config_returns_empty() -> None:
    """zh not in supported_languages — must not leak all voices."""
    provider, langs = _loaded_provider("zh")
    with language_config(*langs):
        result = await provider.list_voices()
    assert list(result) == []
