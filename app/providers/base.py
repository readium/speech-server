from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.schemas.audio import AudioResult, SynthesisParams
from app.schemas.voice import Voice


class TTSProvider(ABC):
    """Uniform interface for every TTS backend (local model or proxied HTTP)."""

    id: str

    @abstractmethod
    async def list_voices(self) -> Sequence[Voice]:
        """Return this provider's voices in the Readium Voice shape."""

    @abstractmethod
    async def synthesize(self, params: SynthesisParams) -> AudioResult:
        """Produce raw PCM + sample rate. Encoding to mp3/wav/opus is the Synthesizer's job.

        Implementations MUST offload CPU-bound work off the event loop via run_inference().
        """

    async def health(self) -> bool:
        """Optional readiness signal. Override to check model loaded / remote reachable."""
        return True
