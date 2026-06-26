from pydantic import BaseModel

from app.domain.enums import Gender, ProviderId, Quality


class Voice(BaseModel):
    # Readium IVoices-aligned fields
    label: str
    voiceURI: str
    name: str
    language: str  # BCP-47
    gender: Gender | None = None
    age: str | None = None
    offlineAvailability: bool = False
    quality: Quality | None = None
    pitchControl: bool = False
    recommendedPitch: float | None = None
    recommendedRate: float | None = None

    # Server extensions
    provider: ProviderId
    engineVoiceId: str
    sampleRate: int
    mimeTypes: list[str]
