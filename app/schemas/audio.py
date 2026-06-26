from pydantic import BaseModel


class TimingMark(BaseModel):
    offset: float  # seconds from audio start
    text: str  # word or sentence text


class SynthesisParams(BaseModel):
    text: str
    ssml: bool
    language: str | None
    engineVoiceId: str
    speed: float
    pitch: float | None
    prev_utterance: str | None = None
    next_utterance: str | None = None


class AudioResult(BaseModel):
    pcm: bytes
    sample_rate: int
    timing_marks: list[TimingMark] | None = None  # scaffolded; unused until Phase 3+
