from app.domain.enums import Gender, Quality
from app.providers.voice_loading import (
    ControlsOverride,
    VoiceEntry,
    build_voice,
    plan_install,
    resolve_install_languages,
)
from app.schemas.voice import Controls


def _entry(**overrides: object) -> VoiceEntry:
    base: dict[str, object] = {
        "name": "Test",
        "originalName": "test",
        "identifier": "urn:x:test",
        "language": "en-US",
        "otherLanguages": ["fr", "es"],
    }
    base.update(overrides)
    return VoiceEntry(**base)  # type: ignore[arg-type]


def test_resolve_primary_mode_ignores_other_languages() -> None:
    primary, other = resolve_install_languages(_entry(), frozenset({"en", "fr", "es"}), False)
    assert primary == "en"
    assert other == frozenset()


def test_resolve_all_mode_bounded_by_enabled_languages() -> None:
    """The crux of the install-mode design: cross-language support never exceeds
    what's already enabled via LANGUAGES, even if voices.json declares more."""
    primary, other = resolve_install_languages(_entry(), frozenset({"en", "fr"}), True)
    assert primary == "en"
    assert other == frozenset({"fr"})  # "es" is declared but not enabled — excluded


def test_resolve_all_mode_never_installs_beyond_enabled_set() -> None:
    entry = _entry(otherLanguages=["fr", "es", "de", "it", "pt"])
    _, other = resolve_install_languages(entry, frozenset({"en"}), True)
    assert other == frozenset()  # nothing else enabled — no new model gets pulled in


def test_resolve_excludes_primary_from_other_set() -> None:
    entry = _entry(language="en-US", otherLanguages=["en", "fr"])
    _, other = resolve_install_languages(entry, frozenset({"en", "fr"}), True)
    assert other == frozenset({"fr"})  # "en" is primary, not an "other" language


def test_resolve_add_promotes_declared_language_when_not_install_all() -> None:
    """The per-voice override: cherry-pick an addition without switching install_all
    on (which would pull in everything every voice declares)."""
    entry = _entry(otherLanguages=["fr", "es"])
    _, other = resolve_install_languages(
        entry, frozenset({"en", "fr", "es"}), False, add_langs=frozenset({"fr"})
    )
    assert other == frozenset({"fr"})


def test_resolve_add_bounded_by_enabled_languages() -> None:
    """Add can never exceed LANGUAGES either — same invariant as install_all=True."""
    entry = _entry(otherLanguages=["fr", "es"])
    _, other = resolve_install_languages(
        entry, frozenset({"en", "fr"}), False, add_langs=frozenset({"fr", "es"})
    )
    assert other == frozenset({"fr"})  # "es" not enabled — dropped despite being in add_langs


def test_resolve_add_cannot_invent_undeclared_capability() -> None:
    """Add can only promote a language the voice already declares in otherLanguages —
    never a language voices.json doesn't claim that voice supports."""
    entry = _entry(otherLanguages=["fr"])
    _, other = resolve_install_languages(
        entry, frozenset({"en", "fr", "de"}), False, add_langs=frozenset({"de"})
    )
    assert other == frozenset()  # "de" not in this voice's otherLanguages — ignored


def test_resolve_remove_prunes_base_install_all() -> None:
    entry = _entry(otherLanguages=["fr", "es"])
    _, other = resolve_install_languages(
        entry, frozenset({"en", "fr", "es"}), True, remove_langs=frozenset({"fr"})
    )
    assert other == frozenset({"es"})


def test_resolve_remove_wins_when_same_pair_also_added() -> None:
    entry = _entry(otherLanguages=["fr", "es"])
    _, other = resolve_install_languages(
        entry,
        frozenset({"en", "fr", "es"}),
        False,
        add_langs=frozenset({"fr", "es"}),
        remove_langs=frozenset({"fr"}),
    )
    assert other == frozenset({"es"})  # fr added then removed — net result excludes it


# ── plan_install: a voice can run in a non-primary language without its primary ──


def test_plan_install_primary_enabled_default_mode() -> None:
    # Normal case: primary enabled, no cross-language → installs primary only.
    plan = plan_install(_entry(), frozenset({"en", "fr"}), False)
    assert plan == ("en", frozenset({"en"}))


def test_plan_install_primary_not_enabled_but_added_other_installs() -> None:
    # estelle-style: primary (en here) NOT enabled, but an explicit add pulls the
    # voice in for a non-primary language using only that language's model.
    entry = _entry(language="en-US", otherLanguages=["fr", "es"])
    plan = plan_install(entry, frozenset({"fr"}), False, add_langs=frozenset({"fr"}))
    assert plan is not None
    default, installed = plan
    assert installed == frozenset({"fr"})  # installed for fr only — no en base model
    assert default == "fr"  # primary not installed → first installed language


def test_plan_install_no_enabled_language_returns_none() -> None:
    # Primary not enabled and no cross-language applies → voice not installed.
    entry = _entry(language="en-US", otherLanguages=["fr", "es"])
    assert plan_install(entry, frozenset({"de"}), False) is None


def test_plan_install_primary_preferred_as_default_when_installed() -> None:
    entry = _entry(language="en-US", otherLanguages=["fr"])
    plan = plan_install(entry, frozenset({"en", "fr"}), True)  # install_all
    assert plan == ("en", frozenset({"en", "fr"}))  # primary stays the default


def test_controls_serialize_only_enabled() -> None:
    """A false control is absent from the payload; only enabled ones appear."""
    assert Controls().model_dump() == {}
    assert Controls(ssml=True).model_dump() == {"ssml": True}
    assert Controls(ssml=True, boundary=True).model_dump() == {"ssml": True, "boundary": True}
    # internal attribute access is unaffected (all fields still exist)
    assert Controls().boundary is False


def test_build_voice_uses_provider_defaults() -> None:
    entry = _entry(gender=Gender.MALE)
    voice = build_voice(entry, "pocket", frozenset({"fr"}), Quality.VERY_HIGH, Controls())
    assert voice.quality == Quality.VERY_HIGH
    assert voice.otherLanguages == ["fr"]
    assert voice.controls == Controls()
    assert voice.provider == "pocket"
    assert voice.gender == Gender.MALE


def test_build_voice_quality_override_wins_over_default() -> None:
    entry = _entry(quality=Quality.LOW)
    voice = build_voice(entry, "pocket", frozenset(), Quality.VERY_HIGH, Controls())
    assert voice.quality == Quality.LOW


def test_build_voice_partial_controls_override() -> None:
    entry = _entry(controls=ControlsOverride(ssml=True))
    defaults = Controls(pitch=False, speed=False, ssml=False, boundary=False)
    voice = build_voice(entry, "pocket", frozenset(), None, defaults)
    assert voice.controls.ssml is True
    assert voice.controls.pitch is False  # untouched fields fall back to the default
    assert voice.controls.boundary is False


def test_build_voice_other_languages_reflect_installed_not_aspirational() -> None:
    """voices.json declares 2 other languages, but only 1 was actually resolved
    for install — the served Voice must reflect what's installed."""
    entry = _entry(otherLanguages=["fr", "es"])
    voice = build_voice(entry, "pocket", frozenset({"fr"}), None, Controls())
    assert voice.otherLanguages == ["fr"]
