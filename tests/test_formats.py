import pytest
from httpx import AsyncClient

_VOICE = "urn:readium:tts:fake:en-US-standard"
_SYNTH = "/synthesize"


def _body(fmt: str) -> dict:  # type: ignore[type-arg]
    return {"text": "Hello", "voice": _VOICE, "output": {"format": fmt}}


@pytest.mark.route
async def test_wav_returns_riff(client: AsyncClient) -> None:
    resp = await client.post(_SYNTH, json=_body("wav"))
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/wav"
    assert resp.content[:4] == b"RIFF"
    assert resp.content[8:12] == b"WAVE"


@pytest.mark.route
async def test_mp3_returns_audio(client: AsyncClient) -> None:
    resp = await client.post(_SYNTH, json=_body("mp3"))
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/mpeg"
    assert len(resp.content) > 100


@pytest.mark.route
async def test_opus_returns_audio(client: AsyncClient) -> None:
    resp = await client.post(_SYNTH, json=_body("opus"))
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/ogg"
    assert len(resp.content) > 100


@pytest.mark.route
async def test_default_format_is_mp3(client: AsyncClient) -> None:
    resp = await client.post(_SYNTH, json={"text": "Hello", "voice": _VOICE})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/mpeg"


@pytest.mark.route
async def test_output_bitrate_accepted(client: AsyncClient) -> None:
    body = {"text": "Hello", "voice": _VOICE, "output": {"format": "mp3", "bitrate": 64}}
    resp = await client.post(_SYNTH, json=body)
    assert resp.status_code == 200
