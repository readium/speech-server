from typing import Literal

from pydantic import BaseModel

from app.domain.enums import AudioFormat


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
    # Requested container/codec + bitrate. A provider that encodes server-side
    # (e.g. ElevenLabs) uses these to fetch already-encoded audio; PCM providers
    # (pocket/fake) ignore them and the Synthesizer encodes downstream.
    audio_format: AudioFormat = AudioFormat.WAV
    bitrate: int | None = None
    prev_utterance: str | None = None
    next_utterance: str | None = None


class AudioResult(BaseModel):
    pcm: bytes = b""
    sample_rate: int
    boundaries: list[TimingMark] = []  # empty when provider doesn't support word timing
    # Pre-encoded audio from a provider that encodes server-side. When set, the
    # Synthesizer returns it as-is (with content_type) and skips WAV/ffmpeg. When
    # None, `pcm` is authoritative and the Synthesizer encodes it.
    encoded: bytes | None = None
    content_type: str | None = None
