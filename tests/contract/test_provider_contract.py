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
from app.schemas.audio import SynthesisParams
from tests.helpers.audio import assert_valid_audio, audio_len
from tests.helpers.fake_provider import FakeProvider

PROVIDERS = [
    pytest.param("fake", id="fake"),
    pytest.param("pocket", id="pocket", marks=pytest.mark.integration),
    pytest.param("elevenlabs", id="elevenlabs", marks=pytest.mark.integration),
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
    if name == "elevenlabs":
        from app.providers.elevenlabs import ElevenLabsProvider

        el = ElevenLabsProvider()
        await el.load()
        return el
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
            assert v.identifier and v.name and v.language
            assert v.provider == provider.id

    async def test_voiceuri_is_unique(self, provider: TTSProvider) -> None:
        ids = [v.identifier for v in await provider.list_voices()]
        assert len(ids) == len(set(ids))

    async def test_synthesize_returns_valid_audio(self, provider: TTSProvider) -> None:
        v = (await provider.list_voices())[0]
        res = await provider.synthesize(_params(v.identifier))
        assert res.sample_rate > 0
        assert_valid_audio(res)

    async def test_longer_text_yields_longer_audio(self, provider: TTSProvider) -> None:
        v = (await provider.list_voices())[0]
        short = await provider.synthesize(_params(v.identifier, "Hi."))
        long_ = await provider.synthesize(_params(v.identifier, "Hi. " * 20))
        assert audio_len(long_) > audio_len(short)

    async def test_speed_affects_duration(self, provider: TTSProvider) -> None:
        if provider.id == "pocket":
            pytest.xfail("PocketTTS has no native speed param; ffmpeg atempo not yet implemented.")
        v = (await provider.list_voices())[0]
        slow = await provider.synthesize(_params(v.identifier, speed=0.8))
        fast = await provider.synthesize(_params(v.identifier, speed=1.5))
        assert audio_len(fast) < audio_len(slow)

    async def test_synthesize_is_async_non_blocking(self, provider: TTSProvider) -> None:
        assert inspect.iscoroutinefunction(provider.synthesize)

    async def test_health_returns_bool(self, provider: TTSProvider) -> None:
        assert isinstance(await provider.health(), bool)
