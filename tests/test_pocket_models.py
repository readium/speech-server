"""Pocket model map + Dutch data — fast, no model download."""

import json
import subprocess
import sys
from importlib.util import find_spec
from pathlib import Path

import pytest

from app.providers.pocket_tts import _LANG_MODEL, _VOICES_PATH, PocketTTSProvider

_ROOT = Path(__file__).parent.parent


def test_defaults_are_new_models() -> None:
    assert _LANG_MODEL["en"] == "english_18m_2026-10"
    assert _LANG_MODEL["fr"] == "french"
    assert _LANG_MODEL["nl"] == "dutch"


def test_no_legacy_24_layer_models() -> None:
    assert not [m for m in _LANG_MODEL.values() if "24l" in m]


def test_supported_languages_match_model_map() -> None:
    assert PocketTTSProvider.supported_languages == frozenset(_LANG_MODEL)


def test_every_model_ships_in_installed_pocket_tts() -> None:
    spec = find_spec("pocket_tts")
    assert spec and spec.submodule_search_locations
    configs = Path(next(iter(spec.submodule_search_locations))) / "config"
    for model in _LANG_MODEL.values():
        assert (configs / f"{model}.yaml").is_file(), f"{model} missing in pocket-tts"


def test_every_voice_language_has_a_model() -> None:
    for v in json.loads(_VOICES_PATH.read_text()):
        langs = {v["language"].split("-")[0].lower()} | {
            code.split("-")[0].lower() for code in v.get("otherLanguages", [])
        }
        assert langs <= set(_LANG_MODEL), (v["originalName"], langs - set(_LANG_MODEL))


def test_daan_is_native_dutch() -> None:
    daan = next(v for v in json.loads(_VOICES_PATH.read_text()) if v["originalName"] == "daan")
    assert daan["language"].split("-")[0] == "nl"


def test_pocket_plan_selftest() -> None:
    subprocess.run(
        [sys.executable, str(_ROOT / "scripts" / "pocket_plan.py"), "--selftest"], check=True
    )


@pytest.mark.parametrize("lang", ["fr", "nl"])
def test_every_voice_declares_dutch_and_french(lang: str) -> None:
    for v in json.loads(_VOICES_PATH.read_text()):
        langs = {v["language"].split("-")[0].lower()} | {
            c.split("-")[0].lower() for c in v.get("otherLanguages", [])
        }
        assert lang in langs, v["originalName"]
