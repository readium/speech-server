import math
import struct
from collections.abc import Sequence

from app.core.concurrency import run_inference
from app.domain.enums import Gender, ProviderId, Quality
from app.providers.base import TTSProvider
from app.schemas.audio import AudioResult, SynthesisParams
from app.schemas.voice import Voice

_SAMPLE_RATE = 22050
_DURATION = 0.5  # seconds
_FREQ = 440.0  # Hz


def _generate_tone(sample_rate: int = _SAMPLE_RATE, duration: float = _DURATION) -> bytes:
    n = int(sample_rate * duration)
    samples = [int(32767 * math.sin(2 * math.pi * _FREQ * i / sample_rate)) for i in range(n)]
    return struct.pack(f"<{n}h", *samples)


_VOICES: list[Voice] = [
    Voice(
        label="Fake Voice (English)",
        voiceURI="urn:readium:tts:fake:en-US-standard",
        name="fake-en-US",
        language="en-US",
        gender=Gender.NEUTRAL,
        offlineAvailability=True,
        quality=Quality.MEDIUM,
        provider=ProviderId.FAKE,
        engineVoiceId="fake-en",
        sampleRate=_SAMPLE_RATE,
        mimeTypes=["audio/wav"],
    ),
    Voice(
        label="Fake Voice (French)",
        voiceURI="urn:readium:tts:fake:fr-FR-standard",
        name="fake-fr-FR",
        language="fr-FR",
        gender=Gender.NEUTRAL,
        offlineAvailability=True,
        quality=Quality.MEDIUM,
        provider=ProviderId.FAKE,
        engineVoiceId="fake-fr",
        sampleRate=_SAMPLE_RATE,
        mimeTypes=["audio/wav"],
    ),
]


class FakeProvider(TTSProvider):
    id = "fake"

    async def list_voices(self) -> Sequence[Voice]:
        return _VOICES

    async def synthesize(self, params: SynthesisParams) -> AudioResult:
        pcm = await run_inference(_generate_tone)
        return AudioResult(pcm=pcm, sample_rate=_SAMPLE_RATE)
