"""Provider Contract Suite — every TTSProvider must pass these.

FakeProvider runs in the fast suite (no model download).
PocketTTS runs under `pytest -m integration` (requires real model).

NOTE: test_speed_affects_duration is marked xfail for pocket — PocketTTS has
no native speed parameter. Speed via ffmpeg atempo is not yet implemented.
"""

from __future__ import annotations

import inspect

import pytest

from app.core.concurrency import init_semaphore
from app.providers.base import TTSProvider
from app.providers.fake import FakeProvider
from app.schemas.audio import SynthesisParams
from tests.helpers.audio import assert_valid_pcm, pcm_duration_seconds

PROVIDERS = [
    pytest.param("fake", id="fake"),
    pytest.param("pocket", id="pocket", marks=pytest.mark.integration),
]


@pytest.fixture
async def provider(request: pytest.FixtureRequest) -> TTSProvider:
    init_semaphore(2)
    name: str = request.param
    if name == "fake":
        return FakeProvider()
    if name == "pocket":
        from app.providers.pocket_tts import PocketTTSProvider

        p = PocketTTSProvider()
        await p.load()
        return p
    raise ValueError(f"Unknown provider: {name}")


def _params(
    voice_uri: str,
    text: str = "Hello world, this is a test.",
    speed: float = 1.0,
) -> SynthesisParams:
    return SynthesisParams(
        text=text,
        ssml=False,
        language="en-US",
        voice_uri=voice_uri,
        speed=speed,
        pitch=None,
    )


@pytest.mark.contract
@pytest.mark.parametrize("provider", PROVIDERS, indirect=True)
class TestProviderContract:
    async def test_list_voices_nonempty_and_shaped(self, provider: TTSProvider) -> None:
        voices = await provider.list_voices()
        assert len(voices) >= 1
        for v in voices:
            assert v.voiceURI and v.name and v.language
            assert v.provider == provider.id
            assert v.engineVoiceId
            assert v.sampleRate > 0

    async def test_voiceuri_is_unique(self, provider: TTSProvider) -> None:
        uris = [v.voiceURI for v in await provider.list_voices()]
        assert len(uris) == len(set(uris))

    async def test_synthesize_returns_valid_audio(self, provider: TTSProvider) -> None:
        v = (await provider.list_voices())[0]
        res = await provider.synthesize(_params(v.voiceURI))
        assert res.sample_rate > 0
        assert_valid_pcm(res)

    async def test_longer_text_yields_longer_audio(self, provider: TTSProvider) -> None:
        v = (await provider.list_voices())[0]
        short = await provider.synthesize(_params(v.voiceURI, "Hi."))
        long_ = await provider.synthesize(_params(v.voiceURI, "Hi. " * 20))
        assert pcm_duration_seconds(long_) > pcm_duration_seconds(short)

    async def test_speed_affects_duration(self, provider: TTSProvider) -> None:
        if provider.id == "pocket":
            pytest.xfail("PocketTTS has no native speed param; ffmpeg atempo not yet implemented.")
        v = (await provider.list_voices())[0]
        slow = await provider.synthesize(_params(v.voiceURI, speed=0.8))
        fast = await provider.synthesize(_params(v.voiceURI, speed=1.5))
        assert pcm_duration_seconds(fast) < pcm_duration_seconds(slow)

    async def test_synthesize_is_async_non_blocking(self, provider: TTSProvider) -> None:
        assert inspect.iscoroutinefunction(provider.synthesize)

    async def test_health_returns_bool(self, provider: TTSProvider) -> None:
        assert isinstance(await provider.health(), bool)
