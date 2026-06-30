from typing import Literal

from pydantic import BaseModel


class TimingMark(BaseModel):
    """Mirrors the Web Speech API SpeechSynthesisEvent boundary fields.
    charIndex + charLength index into the original SynthesizeRequest.text."""

    name: Literal["word", "sentence"] = "word"
    charIndex: int  # character offset of word start in utterance text
    charLength: int  # character length of the word span
    elapsedTime: float  # seconds from audio start when word begins


class SynthesisParams(BaseModel):
    text: str
    ssml: bool
    language: str | None
    voice_uri: str
    speed: float
    pitch: float | None
    prev_utterance: str | None = None
    next_utterance: str | None = None


class AudioResult(BaseModel):
    pcm: bytes
    sample_rate: int
    boundaries: list[TimingMark] = []  # empty when provider doesn't support word timing
