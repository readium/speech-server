from pydantic import BaseModel, model_serializer

from app.domain.enums import Gender, Quality


class Controls(BaseModel):
    """Which prosody/format controls a voice accepts. Provider-level defaults,
    overridable per voice (see app/providers/voice_loading.py).

    Serializes only the controls that are ENABLED — a control the voice doesn't
    support is simply absent, not `false`. Keeps `/voices` and `/service` lean and
    works the same for any provider (pocket → `{}`, an SSML voice → `{"ssml": true}`).
    Internal Python access (e.g. `voice.controls.boundary`) still sees all fields."""

    pitch: bool = False
    speed: bool = False
    ssml: bool = False
    boundary: bool = False  # true when the provider returns word-level timing marks

    @model_serializer
    def _serialize_enabled_only(self) -> dict[str, bool]:
        return {k: True for k, v in self.__dict__.items() if v}


class Voice(BaseModel):
    # --- Readium ReadiumSpeechVoice-aligned fields ---
    name: str
    originalName: str
    identifier: str
    language: str  # BCP-47, primary
    otherLanguages: list[str] = []  # ACTUALLY INSTALLED cross-language support, not the
    # aspirational full list from voices.json (see app/providers/voice_loading.py)
    gender: Gender | None = None
    quality: Quality | None = None

    # --- server extensions (not in ReadiumSpeechVoice) ---
    provider: str
    controls: Controls = Controls()


def voice_language_prefixes(voice: Voice) -> frozenset[str]:
    return frozenset(lang.split("-")[0].lower() for lang in [voice.language, *voice.otherLanguages])
