import functools
import math
import struct
from collections.abc import Sequence

from app.core.concurrency import run_inference
from app.domain.enums import Gender, Quality
from app.providers.base import TTSProvider
from app.schemas.audio import AudioResult, SynthesisParams
from app.schemas.voice import Voice

_SAMPLE_RATE = 24000  # matches PocketTTS native output
_FREQ = 440.0  # Hz

_VOICES: list[Voice] = [
    Voice(
        source="json",
        label="Fake Voice (English)",
        name="fake-en-US",
        originalName="fake-en-US",
        voiceURI="urn:readium:tts:fake:en-US-standard",
        language="en-US",
        gender=Gender.NEUTRAL,
        quality=Quality.NORMAL,
        preloaded=True,
        provider="fake",
        engineVoiceId="fake-en",
        sampleRate=_SAMPLE_RATE,
        mimeTypes=["audio/mpeg", "audio/wav", "audio/ogg"],
    ),
    Voice(
        source="json",
        label="Fake Voice (French)",
        name="fake-fr-FR",
        originalName="fake-fr-FR",
        voiceURI="urn:readium:tts:fake:fr-FR-standard",
        language="fr-FR",
        gender=Gender.NEUTRAL,
        quality=Quality.NORMAL,
        preloaded=True,
        provider="fake",
        engineVoiceId="fake-fr",
        sampleRate=_SAMPLE_RATE,
        mimeTypes=["audio/mpeg", "audio/wav", "audio/ogg"],
    ),
]


def _generate_tone(sample_rate: int, duration: float) -> bytes:
    n = int(sample_rate * duration)
    samples = [int(32767 * math.sin(2 * math.pi * _FREQ * i / sample_rate)) for i in range(n)]
    return struct.pack(f"<{n}h", *samples)


class FakeProvider(TTSProvider):
    id = "fake"

    async def _all_voices(self) -> Sequence[Voice]:
        return _VOICES

    async def synthesize(self, params: SynthesisParams) -> AudioResult:
        duration = max(0.1, len(params.text) * 0.05) / max(0.1, params.speed)
        pcm = await run_inference(functools.partial(_generate_tone, _SAMPLE_RATE, duration))
        return AudioResult(pcm=pcm, sample_rate=_SAMPLE_RATE)
