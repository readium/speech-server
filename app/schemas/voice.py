from typing import Literal

from pydantic import BaseModel

from app.domain.enums import Gender, Quality


class Voice(BaseModel):
    # --- Readium ReadiumSpeechVoice-aligned fields ---
    source: Literal["json", "browser"] = "json"
    label: str
    name: str
    originalName: str
    voiceURI: str
    language: str  # BCP-47
    localizedName: str | None = None  # "android" | "apple"
    altNames: list[str] | None = None
    altLanguage: str | None = None
    otherLanguages: list[str] | None = None
    multiLingual: bool | None = None
    gender: Gender | None = None
    children: bool | None = None
    quality: Quality | None = None
    pitchControl: bool = False
    pitch: float | None = None
    rate: float | None = None
    preloaded: bool = False
    nativeID: str | list[str] | None = None
    note: str | None = None

    # --- server extensions (not in ReadiumSpeechVoice) ---
    provider: str
    engineVoiceId: str
    sampleRate: int
    mimeTypes: list[str]
    boundary: bool = False  # true when provider supports word-level timing marks
