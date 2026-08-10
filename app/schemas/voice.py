from pydantic import BaseModel

from app.domain.enums import Gender, Quality


class Controls(BaseModel):
    """Which prosody/format controls a provider supports. Server-wide per provider —
    see GET /service — not per voice."""

    pitch: bool = False
    speed: bool = False
    ssml: bool = False
    boundary: bool = False  # true when the provider returns word-level timing marks

    def as_dict(self) -> dict[str, bool]:
        """Full booleans, including disabled ones — unlike the enabled-only JSON
        serialization above. Used by GET /service to show what a provider CAN do,
        not just what a given voice has turned on."""
        return {
            "pitch": self.pitch,
            "speed": self.speed,
            "ssml": self.ssml,
            "boundary": self.boundary,
        }


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


def voice_language_prefixes(voice: Voice) -> frozenset[str]:
    return frozenset(lang.split("-")[0].lower() for lang in [voice.language, *voice.otherLanguages])
