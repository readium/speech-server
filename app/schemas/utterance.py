from pydantic import BaseModel, Field

from app.domain.enums import AudioFormat


class OutputConfig(BaseModel):
    """Requested output parameters — nested under 'output' in the API body."""

    format: AudioFormat = AudioFormat.WAV
    bitrate: int | None = None  # kbps; only meaningful for mp3/opus
    sample_rate: int | None = None
    speed: float = 1.0
    pitch: float | None = None


class Utterance(BaseModel):
    """Mirrors ReadiumSpeechUtterance."""

    id: str | None = None
    text: str
    ssml: bool = False
    language: str | None = None  # BCP-47


class SynthesizeRequest(Utterance):
    # Voice identifier (URI) or originalName. Optional: when omitted, the server
    # falls back to POCKET_DEFAULT_VOICE; if that's unset too, the request is rejected.
    voice: str | None = None
    prev_utterance: str | None = None  # preceding text/ID for prosody context
    next_utterance: str | None = None  # following text/ID for prosody context
    boundary: bool = False  # if true, response is JSON with base64 audio + timing marks
    output: OutputConfig = Field(default_factory=OutputConfig)
    publication_id: str | None = None  # server extension: cache-key scope
