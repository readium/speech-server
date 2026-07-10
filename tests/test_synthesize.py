import struct

import pytest
from httpx import AsyncClient

_VOICE = "urn:readium:tts:fake:en-US-standard"
_VOICE_FR = "urn:readium:tts:fake:fr-FR-standard"
_URL = "/synthesize"
_WAV = {"output": {"format": "wav"}}


def _is_valid_wav(data: bytes) -> bool:
    if len(data) < 44:
        return False
    return data[:4] == b"RIFF" and data[8:12] == b"WAVE" and data[12:16] == b"fmt "


@pytest.mark.route
async def test_synthesize_returns_wav(client: AsyncClient) -> None:
    resp = await client.post(_URL, json={"text": "Hello", "voice": _VOICE, **_WAV})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/wav"
    assert _is_valid_wav(resp.content)


@pytest.mark.route
async def test_synthesize_wav_is_nonempty_audio(client: AsyncClient) -> None:
    resp = await client.post(_URL, json={"text": "Hello", "voice": _VOICE, **_WAV})
    data_size = struct.unpack_from("<I", resp.content, 40)[0]
    assert data_size > 0


@pytest.mark.route
async def test_synthesize_unknown_voice_returns_404(client: AsyncClient) -> None:
    resp = await client.post(_URL, json={"text": "Hello", "voice": "urn:unknown", **_WAV})
    assert resp.status_code == 404
    assert resp.json()["type"] == "https://readium.org/speech-server/error#voice_not_found"


@pytest.mark.route
async def test_synthesize_empty_text_returns_400(client: AsyncClient) -> None:
    resp = await client.post(_URL, json={"text": "   ", "voice": _VOICE, **_WAV})
    assert resp.status_code == 400
    assert resp.json()["type"] == "https://readium.org/speech-server/error#validation_failed"


@pytest.mark.route
async def test_synthesize_invalid_format_returns_422(client: AsyncClient) -> None:
    body = {"text": "Hello", "voice": _VOICE, "output": {"format": "flac"}}
    resp = await client.post(_URL, json=body)
    assert resp.status_code == 422


@pytest.mark.route
async def test_synthesize_schema_error_returns_422(client: AsyncClient) -> None:
    resp = await client.post(_URL, json={"text": "Hello", "output": {"format": "wav"}})
    assert resp.status_code == 422


@pytest.mark.route
async def test_synthesize_content_disposition(client: AsyncClient) -> None:
    resp = await client.post(_URL, json={"text": "Hello", "voice": _VOICE, **_WAV})
    assert "inline" in resp.headers.get("content-disposition", "")


@pytest.mark.route
async def test_synthesize_boundary_returns_json(client: AsyncClient) -> None:
    resp = await client.post(
        _URL,
        json={"text": "Ceci est un test.", "voice": _VOICE_FR, "boundary": True},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/json"
    body = resp.json()
    assert "audio" in body
    assert "format" in body
    assert "boundaries" in body
    assert body["boundaries"] is None  # FakeProvider.supports_boundaries = False
    import base64

    assert len(base64.b64decode(body["audio"])) > 0


@pytest.mark.route
async def test_synthesize_with_prosody_context(client: AsyncClient) -> None:
    resp = await client.post(
        _URL,
        json={
            "text": "She opened the door.",
            "voice": _VOICE,
            "prev_utterance": "It was dark.",
            "next_utterance": "The room was cold.",
            "publication_id": "urn:isbn:9780000000000",
            "output": {"format": "wav", "speed": 0.9},
        },
    )
    assert resp.status_code == 200
    assert _is_valid_wav(resp.content)
