from pydantic import BaseModel

from app.domain.enums import Gender, Quality
from app.schemas.voice import Controls, Voice


class ControlsOverride(BaseModel):
    """Partial per-voice override of a provider's default Controls. Unset (None)
    fields fall back to the provider default — see merge_controls()."""

    pitch: bool | None = None
    speed: bool | None = None
    ssml: bool | None = None
    boundary: bool | None = None


class VoiceEntry(BaseModel):
    """Raw per-voice shape read from a provider's voices.json — documents what's
    POSSIBLE. otherLanguages here is aspirational, not what's actually installed."""

    name: str
    originalName: str
    identifier: str
    language: str
    otherLanguages: list[str] = []
    gender: Gender | None = None
    quality: Quality | None = None
    controls: ControlsOverride | None = None


def _lang_prefix(lang: str) -> str:
    return lang.split("-")[0].lower()


def resolve_install_languages(
    entry: VoiceEntry,
    enabled: frozenset[str],
    install_all: bool,
    add_langs: frozenset[str] = frozenset(),
    remove_langs: frozenset[str] = frozenset(),
) -> tuple[str, frozenset[str]]:
    """Returns (primary_lang_key, other_lang_keys) actually to install for this
    voice — always bounded by `enabled` (the operator's configured LANGUAGES), so
    this never triggers a new base-model download on its own. install_all=False
    -> other_lang_keys starts empty; install_all=True -> starts as every declared
    otherLanguage that's enabled (Settings.voice_install_all, the "*:*" wildcard).

    add_langs / remove_langs (Settings.voice_language_add_map/remove_map, looked up
    per voice) then adjust that base set: add_langs can only pull in languages this
    voice already declares in otherLanguages (still bounded by `enabled` — it can
    promote a declared-but-not-installed language, never invent support voices.json
    doesn't claim); remove_langs prunes any pair the base mode would have included.
    The primary language is never affected by either."""
    primary = _lang_prefix(entry.language)
    declared_other = frozenset(_lang_prefix(lang) for lang in entry.otherLanguages)
    base_other = declared_other & enabled if install_all else frozenset()
    other = (base_other | (add_langs & declared_other & enabled)) - remove_langs - {primary}
    return primary, other


def plan_install(
    entry: VoiceEntry,
    enabled: frozenset[str],
    install_all: bool,
    add_langs: frozenset[str] = frozenset(),
    remove_langs: frozenset[str] = frozenset(),
) -> tuple[str, frozenset[str]] | None:
    """Decide what a voice actually installs. Unlike a naive "primary must be
    enabled" rule, a voice may run in a non-primary language WITHOUT its primary
    base model — pocket_tts loads a voice's speaker embedding from the *target*
    language's model dir, not the primary's (see models/tts_model.py), so any
    (voice, language) with an embedding works using only that language's model.

    Returns (default_lang, installed_langs), or None when no enabled language
    applies (voice not installed at all). installed_langs is every enabled language
    among {primary} ∪ resolved others. default_lang — used when a synth request
    omits `language` — is the primary if it's installed, else the first installed
    language (deterministic)."""
    primary, other = resolve_install_languages(entry, enabled, install_all, add_langs, remove_langs)
    installed = (frozenset({primary}) & enabled) | other
    if not installed:
        return None
    default_lang = primary if primary in installed else min(installed)
    return default_lang, installed


def merge_controls(default: Controls, override: ControlsOverride | None) -> Controls:
    if override is None:
        return default
    return Controls(
        pitch=override.pitch if override.pitch is not None else default.pitch,
        speed=override.speed if override.speed is not None else default.speed,
        ssml=override.ssml if override.ssml is not None else default.ssml,
        boundary=override.boundary if override.boundary is not None else default.boundary,
    )


def build_voice(
    entry: VoiceEntry,
    provider_id: str,
    installed_other: frozenset[str],
    default_quality: Quality | None,
    default_controls: Controls,
) -> Voice:
    """The merge point where 'possible' (voices.json) becomes 'installed'
    (served via /voices): otherLanguages is installed_other, not entry.otherLanguages."""
    return Voice(
        name=entry.name,
        originalName=entry.originalName,
        provider=provider_id,
        identifier=entry.identifier,
        language=entry.language,
        otherLanguages=sorted(installed_other),
        gender=entry.gender,
        quality=entry.quality or default_quality,
        controls=merge_controls(default_controls, entry.controls),
    )
