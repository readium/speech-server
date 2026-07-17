"""Integration tests for PocketTTSProvider — requires real model download.

Run with: pytest -m integration
Skipped by default (CI uses fast suite only).
"""

import pytest

from app.providers.pocket_tts import PocketTTSProvider
from app.schemas.audio import SynthesisParams
from tests.helpers.audio import assert_valid_pcm, pcm_duration_seconds

pytestmark = pytest.mark.integration


@pytest.fixture
async def pocket() -> PocketTTSProvider:
    p = PocketTTSProvider()
    await p.load()
    return p


async def test_health_ready(pocket: PocketTTSProvider) -> None:
    assert await pocket.health() is True


async def test_list_voices_nonempty_and_shaped(pocket: PocketTTSProvider) -> None:
    voices = await pocket.list_voices()
    assert len(voices) >= 1
    for v in voices:
        assert v.identifier.startswith("urn:readium:tts:pocket:")
        assert v.name and v.language
        assert v.provider == "pocket"
        assert v.quality is not None


async def test_voiceuri_unique(pocket: PocketTTSProvider) -> None:
    ids = [v.identifier for v in await pocket.list_voices()]
    assert len(ids) == len(set(ids))


async def test_synthesize_returns_valid_pcm(pocket: PocketTTSProvider) -> None:
    v = (await pocket.list_voices())[0]
    params = SynthesisParams(
        text="Hello world, this is a test.",
        ssml=False,
        language="en-US",
        voice_uri=v.identifier,
        speed=1.0,
        pitch=None,
    )
    result = await pocket.synthesize(params)
    assert_valid_pcm(result)
    assert result.sample_rate == 24000


async def test_longer_text_yields_more_audio(pocket: PocketTTSProvider) -> None:
    v = (await pocket.list_voices())[0]

    def params(text: str) -> SynthesisParams:
        return SynthesisParams(
            text=text,
            ssml=False,
            language=None,
            voice_uri=v.identifier,
            speed=1.0,
            pitch=None,
        )

    short = await pocket.synthesize(params("Hi."))
    long_ = await pocket.synthesize(params("Hi. " * 20))
    assert pcm_duration_seconds(long_) > pcm_duration_seconds(short)


@pytest.mark.skip(
    reason=(
        "PocketTTS has no native speed parameter — generate_audio() does not accept rate. "
        "Speed via ffmpeg atempo post-processing is not yet implemented."
    )
)
async def test_speed_affects_duration(pocket: PocketTTSProvider) -> None: ...
