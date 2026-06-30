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
    VERY_LOW = "veryLow"
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    VERY_HIGH = "veryHigh"
