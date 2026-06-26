import struct

import pytest
from httpx import AsyncClient

_VOICE = "urn:readium:tts:fake:en-US-standard"
_URL = "/v1/synthesize"


def _is_valid_wav(data: bytes) -> bool:
    if len(data) < 44:
        return False
    return data[:4] == b"RIFF" and data[8:12] == b"WAVE" and data[12:16] == b"fmt "


@pytest.mark.route
async def test_synthesize_returns_wav(client: AsyncClient) -> None:
    resp = await client.post(_URL, json={"text": "Hello", "voice": _VOICE, "format": "wav"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/wav"
    assert _is_valid_wav(resp.content)


@pytest.mark.route
async def test_synthesize_wav_is_nonempty_audio(client: AsyncClient) -> None:
    resp = await client.post(_URL, json={"text": "Hello", "voice": _VOICE, "format": "wav"})
    data = resp.content
    # parse data chunk size from WAV header offset 40
    data_size = struct.unpack_from("<I", data, 40)[0]
    assert data_size > 0


@pytest.mark.route
async def test_synthesize_unknown_voice_returns_404(client: AsyncClient) -> None:
    resp = await client.post(_URL, json={"text": "Hello", "voice": "urn:unknown", "format": "wav"})
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "voice_not_found"


@pytest.mark.route
async def test_synthesize_empty_text_returns_400(client: AsyncClient) -> None:
    resp = await client.post(_URL, json={"text": "   ", "voice": _VOICE, "format": "wav"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "validation_failed"


@pytest.mark.route
async def test_synthesize_unsupported_format_returns_415(client: AsyncClient) -> None:
    resp = await client.post(_URL, json={"text": "Hello", "voice": _VOICE, "format": "mp3"})
    assert resp.status_code == 415
    assert resp.json()["error"]["code"] == "unsupported_format"


@pytest.mark.route
async def test_synthesize_schema_error_returns_422(client: AsyncClient) -> None:
    # missing required 'voice' field
    resp = await client.post(_URL, json={"text": "Hello", "format": "wav"})
    assert resp.status_code == 422


@pytest.mark.route
async def test_synthesize_content_disposition(client: AsyncClient) -> None:
    resp = await client.post(_URL, json={"text": "Hello", "voice": _VOICE, "format": "wav"})
    assert "attachment" in resp.headers.get("content-disposition", "")


@pytest.mark.route
async def test_synthesize_with_prosody_context(client: AsyncClient) -> None:
    resp = await client.post(
        _URL,
        json={
            "text": "She opened the door.",
            "voice": _VOICE,
            "format": "wav",
            "speed": 0.9,
            "prev_utterance": "It was dark.",
            "next_utterance": "The room was cold.",
            "publication_id": "urn:isbn:9780000000000",
        },
    )
    assert resp.status_code == 200
    assert _is_valid_wav(resp.content)
