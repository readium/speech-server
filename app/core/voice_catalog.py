from app.api.errors import VoiceNotFound
from app.core.registry import ProviderRegistry
from app.providers.base import TTSProvider
from app.schemas.voice import Voice


class VoiceCatalog:
    def __init__(self, registry: ProviderRegistry) -> None:
        self._registry = registry
        self._voices: list[Voice] = []
        self._index: dict[str, tuple[TTSProvider, str]] = {}

    async def load(self) -> None:
        voices: list[Voice] = []
        index: dict[str, tuple[TTSProvider, str]] = {}
        for provider in self._registry.all():
            for voice in await provider.list_voices():
                voices.append(voice)
                index[voice.voiceURI] = (provider, voice.voiceURI)
        self._voices = voices
        self._index = index

    def list(self, language: str | None = None, provider: str | None = None) -> list[Voice]:
        result = self._voices
        if language:
            lang_prefix = language.split("-")[0].lower()
            result = [v for v in result if v.language.split("-")[0].lower() == lang_prefix]
        if provider:
            result = [v for v in result if v.provider == provider]
        return result

    def resolve(self, voice_uri: str) -> tuple[TTSProvider, str]:
        entry = self._index.get(voice_uri)
        if entry is None:
            raise VoiceNotFound(f"Voice '{voice_uri}' not found.")
        return entry
