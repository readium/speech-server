import logging
import struct

from app.api.errors import AppError, PayloadTooLarge, RequestValidationFailed, ServiceNotReady
from app.config.settings import settings
from app.core.circuit_breaker import CircuitBreakerRegistry
from app.core.voice_catalog import VoiceCatalog
from app.domain.enums import AudioFormat
from app.drivers import ffmpeg as ffmpeg_driver
from app.schemas.audio import AudioResult, SynthesisParams, TimingMark
from app.schemas.utterance import SynthesizeRequest

_WAV_BITS = 16
_WAV_CHANNELS = 1


def _pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    block_align = _WAV_CHANNELS * (_WAV_BITS // 8)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(pcm),
        b"WAVE",
        b"fmt ",
        16,
        1,
        _WAV_CHANNELS,
        sample_rate,
        sample_rate * block_align,
        block_align,
        _WAV_BITS,
        b"data",
        len(pcm),
    )
    return header + pcm


logger = logging.getLogger(__name__)


class Synthesizer:
    def __init__(self, catalog: VoiceCatalog, breakers: CircuitBreakerRegistry) -> None:
        self._catalog = catalog
        self._breakers = breakers

    async def synthesize(
        self, request: SynthesizeRequest
    ) -> tuple[bytes, str, list[TimingMark], bool]:
        text = request.text.strip()
        if not text:
            raise RequestValidationFailed("text must not be empty or whitespace")

        if len(text) > settings.max_text_length:
            raise PayloadTooLarge(
                f"text exceeds {settings.max_text_length} characters",
                detail=f"received {len(text)}, limit is {settings.max_text_length}",
            )

        # POCKET_DEFAULT_VOICE is pocket-scoped by name but the only server-wide
        # default today; a request may omit voice and inherit it.
        voice_ref = request.voice or settings.pocket_default_voice
        if not voice_ref:
            raise RequestValidationFailed(
                "no voice specified and no default voice configured (POCKET_DEFAULT_VOICE)"
            )

        provider, voice = self._catalog.resolve(voice_ref)
        boundaries_supported = voice.controls.boundary

        out = request.output
        logger.info(
            "synthesize voice=%s provider=%s format=%s chars=%d boundary=%s",
            voice.identifier,
            provider.id,
            out.format.value,
            len(text),
            request.boundary,
        )
        params = SynthesisParams(
            text=text,
            ssml=request.ssml,
            language=request.language,
            voice_uri=voice.identifier,
            speed=out.speed,
            pitch=out.pitch,
            prev_utterance=request.prev_utterance,
            next_utterance=request.next_utterance,
        )

        breaker = self._breakers.get(provider.id) if settings.circuit_breaker_enabled else None
        if breaker is not None and not breaker.allow():
            raise ServiceNotReady(f"Provider '{provider.id}' is temporarily unavailable")

        try:
            result: AudioResult = await provider.synthesize(params)
        except AppError:
            if breaker is not None:
                breaker.record_failure()
            raise
        else:
            if breaker is not None:
                breaker.record_success()

        if out.format == AudioFormat.WAV:
            audio = _pcm_to_wav(result.pcm, result.sample_rate)
            logger.info("generated wav pcm_bytes=%d output_bytes=%d", len(result.pcm), len(audio))
            return (audio, "audio/wav", result.boundaries, boundaries_supported)

        encoded = await ffmpeg_driver.encode(
            result.pcm,
            result.sample_rate,
            out.format.value,
            ffmpeg_bin=settings.ffmpeg_bin,
            bitrate=out.bitrate,
        )
        logger.info(
            "generated %s pcm_bytes=%d output_bytes=%d",
            out.format.value,
            len(result.pcm),
            len(encoded),
        )
        return (
            encoded,
            ffmpeg_driver.content_type(out.format.value),
            result.boundaries,
            boundaries_supported,
        )
