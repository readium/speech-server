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
    """Every supported language is some voice's PRIMARY language at least once."""
    voices = json.loads(_POCKET_JSON.read_text())
    present = {v["language"].split("-")[0].lower() for v in voices}
    assert present == _SUPPORTED


def test_pocket_json_english_voice_count() -> None:
    voices = json.loads(_POCKET_JSON.read_text())
    en = [v for v in voices if v["language"].split("-")[0].lower() == "en"]
    assert len(en) == 21  # voices whose PRIMARY language is English (not all 26 — each
    # voice appears once now, not duplicated per language)


def test_pocket_json_non_english_languages_each_have_voices() -> None:
    voices = json.loads(_POCKET_JSON.read_text())
    by_lang: dict[str, int] = {}
    for v in voices:
        lang = v["language"].split("-")[0].lower()
        by_lang[lang] = by_lang.get(lang, 0) + 1
    for lang in _SUPPORTED - {"en"}:
        assert by_lang.get(lang, 0) >= 1, f"No voices for language: {lang}"


def test_pocket_json_all_voices_have_required_fields() -> None:
    required = {"name", "originalName", "identifier", "language"}
    for v in json.loads(_POCKET_JSON.read_text()):
        missing = required - v.keys()
        assert not missing, f"{v.get('identifier')} missing: {missing}"


def test_pocket_json_no_duplicate_identifiers() -> None:
    voices = json.loads(_POCKET_JSON.read_text())
    ids = [v["identifier"] for v in voices]
    assert len(ids) == len(set(ids))


def test_pocket_json_original_names_are_lowercase() -> None:
    """PocketTTS predefined-voice ids are lowercase; originalName is looked up
    case-sensitively at warm time (get_state_for_audio_prompt). A stray capital
    (e.g. "Vera") silently falls through to the unavailable voice-cloning path."""
    for v in json.loads(_POCKET_JSON.read_text()):
        name = v["originalName"]
        assert name == name.lower(), f"originalName must be lowercase: {name!r}"


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
#
# otherLanguages here is voices.json's full aspirational list, standing in for a
# scenario where every declared cross-language pair happens to be installed (e.g.
# VOICE_LANGUAGES=*:* with every supported language enabled). This exercises
# list_voices()'s voice_language_prefixes()-based filter directly, independent of
# install-mode bookkeeping (covered separately in tests/unit/test_voice_loading.py).


def _loaded_provider(*langs: str):  # type: ignore[no-untyped-def]
    """Return a PocketTTSProvider with all pocket.json voices pre-injected."""
    from app.providers.pocket_tts import PocketTTSProvider
    from app.schemas.voice import Voice

    provider = PocketTTSProvider()
    provider._voices = [  # noqa: SLF001
        Voice(
            name=v["name"],
            originalName=v["originalName"],
            provider="pocket",
            identifier=v["identifier"],
            language=v["language"],
            otherLanguages=v.get("otherLanguages", []),
            gender=v.get("gender"),
        )
        for v in json.loads(_POCKET_JSON.read_text())
    ]
    return provider, langs


@pytest.mark.asyncio
async def test_list_voices_filters_to_single_language() -> None:
    provider, langs = _loaded_provider("fr")
    with language_config(*langs):
        result = await provider.list_voices()
    assert all("fr" in _prefixes(v) for v in result)
    assert len(result) == 26  # every voice declares French as primary or additional


@pytest.mark.asyncio
async def test_list_voices_multiple_languages() -> None:
    provider, langs = _loaded_provider("en", "fr")
    with language_config(*langs):
        result = await provider.list_voices()
    assert all({"en", "fr"} & _prefixes(v) for v in result)
    assert len(result) == 26  # each voice counted once, not per matching language


@pytest.mark.asyncio
async def test_list_voices_all_languages_returns_all() -> None:
    provider, langs = _loaded_provider(*_SUPPORTED)
    with language_config(*langs):
        result = await provider.list_voices()
    assert len(result) == 26  # all voices, each still counted once


@pytest.mark.asyncio
async def test_list_voices_unsupported_config_returns_empty() -> None:
    """zh not in supported_languages — must not leak all voices."""
    provider, langs = _loaded_provider("zh")
    with language_config(*langs):
        result = await provider.list_voices()
    assert list(result) == []


def _prefixes(voice) -> set[str]:  # type: ignore[no-untyped-def]
    from app.schemas.voice import voice_language_prefixes

    return set(voice_language_prefixes(voice))


def test_resolve_lang_key_never_falls_back_to_uninstalled_language() -> None:
    """A requested language a voice ISN'T installed for must NOT silently fall back
    to another language — pocket-tts needs the specific (voice, language) embedding,
    so an uninstalled combo is genuinely unavailable, not a synonym for the default."""
    from app.providers.pocket_tts import PocketTTSProvider

    p = PocketTTSProvider()
    p._voice_langs = {"v": frozenset({"en", "fr"})}  # noqa: SLF001
    p._voice_default_lang = {"v": "en"}  # noqa: SLF001
    assert p._resolve_lang_key("v", "fr") == "fr"  # installed → used  # noqa: SLF001
    assert p._resolve_lang_key("v", None) == "en"  # omitted → default  # noqa: SLF001
    assert p._resolve_lang_key("v", "es") is None  # NOT installed → no fallback  # noqa: SLF001
