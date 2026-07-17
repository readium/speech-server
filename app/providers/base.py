from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import ClassVar

from app.domain.enums import Quality
from app.schemas.audio import AudioResult, SynthesisParams
from app.schemas.voice import Controls, Voice, voice_language_prefixes


class TTSProvider(ABC):
    """Uniform interface for every TTS backend (local model or proxied HTTP)."""

    id: ClassVar[str]

    # BCP-47 language prefixes this provider can serve.
    # Empty (default) = language-agnostic; list_voices() returns all voices unfiltered.
    supported_languages: ClassVar[frozenset[str]] = frozenset()

    # Model-level defaults merged into every voice this provider serves, unless a
    # voice overrides them (see app/providers/voice_loading.py).
    default_quality: ClassVar[Quality | None] = None
    default_controls: ClassVar[Controls] = Controls()

    def active_languages(self) -> frozenset[str]:
        """Intersection of global LANGUAGES config and this provider's supported set.
        Returns empty frozenset when supported_languages is unset (= no filtering)."""
        if not self.supported_languages:
            return frozenset()
        from app.config.settings import settings

        configured = {lang.split("-")[0].lower() for lang in settings.language_list}
        supported = {lang.split("-")[0].lower() for lang in self.supported_languages}
        return frozenset(supported & configured)

    @abstractmethod
    async def _all_voices(self) -> Sequence[Voice]:
        """All voices this provider knows about, regardless of language config."""

    async def list_voices(self) -> Sequence[Voice]:
        """Voices actually INSTALLED (filtered to active_languages()), reflecting the
        realtime install state — this is what `GET /voices` serves. Providers do NOT
        override this."""
        voices = await self._all_voices()
        if not self.supported_languages:
            return voices  # language-agnostic provider: return all
        active = self.active_languages()
        return [v for v in voices if voice_language_prefixes(v) & active]

    @abstractmethod
    async def synthesize(self, params: SynthesisParams) -> AudioResult:
        """Produce raw PCM + sample rate. Encoding to mp3/wav/opus is the Synthesizer's job.

        Implementations MUST offload CPU-bound work off the event loop via run_inference().
        """

    async def load(self) -> None:
        """Called once at startup. Override to load models or warm up connections."""

    async def health(self) -> bool:
        """Optional readiness signal. Override to check model loaded / remote reachable."""
        return True
