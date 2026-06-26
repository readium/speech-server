from pydantic import BaseModel

from app.domain.enums import AudioFormat


class Utterance(BaseModel):
    """Mirrors ReadiumSpeechUtterance."""

    id: str | None = None
    text: str
    ssml: bool = False
    language: str | None = None  # BCP-47


class SynthesizeRequest(Utterance):
    voice: str  # voiceURI — required
    format: AudioFormat = AudioFormat.MP3
    sampleRate: int | None = None
    bitrate: int | None = None  # kbps; meaningful for mp3/opus only
    speed: float = 1.0  # rate multiplier
    pitch: float | None = None
    prev_utterance: str | None = None  # preceding plain-text for prosody context
    next_utterance: str | None = None  # following plain-text for prosody context
    publication_id: str | None = None  # URI/ID for cache-key scoping (Redis in v2)
