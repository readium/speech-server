from enum import StrEnum


class AudioFormat(StrEnum):
    MP3 = "mp3"
    WAV = "wav"
    OPUS = "opus"


class Gender(StrEnum):
    MALE = "male"
    FEMALE = "female"
    NEUTRAL = "neutral"


class Quality(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    PREMIUM = "premium"


class ProviderId(StrEnum):
    POCKET = "pocket"
    KOKORO = "kokoro"
    ELEVENLABS = "elevenlabs"
    AZURE = "azure"
    FAKE = "fake"
