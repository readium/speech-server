import logging
import struct

from app.api.errors import PayloadTooLarge, RequestValidationFailed
from app.config.settings import settings
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
    def __init__(self, catalog: VoiceCatalog) -> None:
        self._catalog = catalog

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

        provider, voice_uri = self._catalog.resolve(request.voice)
        boundaries_supported = provider.supports_boundaries

        out = request.output
        logger.info(
            "synthesize voice=%s provider=%s format=%s chars=%d boundary=%s",
            voice_uri,
            provider.id,
            out.format.value,
            len(text),
            request.boundary,
        )
        params = SynthesisParams(
            text=text,
            ssml=request.ssml,
            language=request.language,
            voice_uri=voice_uri,
            speed=out.speed,
            pitch=out.pitch,
            prev_utterance=request.prev_utterance,
            next_utterance=request.next_utterance,
        )

        result: AudioResult = await provider.synthesize(params)

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
