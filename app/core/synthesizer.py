import struct

from app.api.errors import RequestValidationFailed, UnsupportedFormat
from app.core.voice_catalog import VoiceCatalog
from app.domain.enums import AudioFormat
from app.schemas.audio import AudioResult, SynthesisParams
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


class Synthesizer:
    def __init__(self, catalog: VoiceCatalog) -> None:
        self._catalog = catalog

    async def synthesize(self, request: SynthesizeRequest) -> tuple[bytes, str]:
        if not request.text.strip():
            raise RequestValidationFailed("text must not be empty or whitespace")

        # Phase 1: WAV only; ffmpeg formats land in Phase 3
        if request.format != AudioFormat.WAV:
            raise UnsupportedFormat(
                f"Format '{request.format}' not supported yet — use 'wav'",
                detail="mp3 and opus will be available after Phase 3 (ffmpeg integration)",
            )

        provider, engine_voice_id = self._catalog.resolve(request.voice)

        params = SynthesisParams(
            text=request.text,
            ssml=request.ssml,
            language=request.language,
            engineVoiceId=engine_voice_id,
            speed=request.speed,
            pitch=request.pitch,
            prev_utterance=request.prev_utterance,
            next_utterance=request.next_utterance,
        )

        result: AudioResult = await provider.synthesize(params)
        if result.encoded is not None:
            content_type = f"audio/{result.format or 'wav'}"
            return result.encoded, content_type
        if result.pcm is None:
            raise ValueError("AudioResult must set either pcm or encoded")
        wav_bytes = _pcm_to_wav(result.pcm, result.sample_rate)
        return wav_bytes, "audio/wav"
