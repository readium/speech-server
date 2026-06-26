from app.providers.base import TTSProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, TTSProvider] = {}

    def register(self, provider: TTSProvider) -> None:
        self._providers[provider.id] = provider

    def get(self, provider_id: str) -> TTSProvider | None:
        return self._providers.get(provider_id)

    def all(self) -> list[TTSProvider]:
        return list(self._providers.values())
