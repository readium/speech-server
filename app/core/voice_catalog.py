from app.api.errors import VoiceNotFound
from app.core.registry import ProviderRegistry
from app.providers.base import TTSProvider
from app.schemas.voice import Voice, voice_language_prefixes


class VoiceCatalog:
    def __init__(self, registry: ProviderRegistry) -> None:
        self._registry = registry
        self._voices: list[Voice] = []
        self._index: dict[str, tuple[TTSProvider, Voice]] = {}
        self._name_index: dict[str, tuple[TTSProvider, Voice]] = {}

    async def load(self) -> None:
        # The catalog serves GET /voices — the voices actually INSTALLED on this
        # deployment (realtime: language + otherLanguages reflect what's loaded).
        # resolve() maps a known voice to its provider for synthesis.
        voices: list[Voice] = []
        index: dict[str, tuple[TTSProvider, Voice]] = {}
        # provider exists today; revisit if a second one collides on a name.
        name_index: dict[str, tuple[TTSProvider, Voice]] = {}
        for provider in self._registry.all():
            for voice in await provider.list_voices():
                voices.append(voice)
                index[voice.identifier] = (provider, voice)
                name_index[voice.originalName.lower()] = (provider, voice)
        self._voices = voices
        self._index = index
        self._name_index = name_index

    def list(self, language: str | None = None, provider: str | None = None) -> list[Voice]:
        result = self._voices
        if language:
            lang_prefix = language.split("-")[0].lower()
            result = [v for v in result if lang_prefix in voice_language_prefixes(v)]
        if provider:
            result = [v for v in result if v.provider == provider]
        return result

    def resolve(self, identifier: str) -> tuple[TTSProvider, Voice]:
        # Match the full identifier URI first, then fall back to originalName
        # (case-insensitive) — lets POCKET_DEFAULT_VOICE=alba resolve without a URI.
        entry = self._index.get(identifier) or self._name_index.get(identifier.lower())
        if entry is None:
            raise VoiceNotFound(f"Voice '{identifier}' not found.")
        return entry
