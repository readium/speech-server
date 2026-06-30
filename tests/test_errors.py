import pytest
from httpx import AsyncClient

_VOICE = "urn:readium:tts:fake:en-US-standard"
_URL = "/v1/synthesize"


@pytest.mark.route
async def test_text_too_long_returns_413(client: AsyncClient) -> None:
    resp = await client.post(_URL, json={"text": "x" * 2001, "voice": _VOICE})
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "payload_too_large"


@pytest.mark.route
async def test_ssml_true_does_not_500(client: AsyncClient) -> None:
    resp = await client.post(
        _URL,
        json={
            "text": "<speak>Hello <emphasis>world</emphasis></speak>",
            "voice": _VOICE,
            "ssml": True,
        },
    )
    assert resp.status_code == 200


@pytest.mark.route
async def test_readyz_returns_200_when_ready(client: AsyncClient) -> None:
    resp = await client.get("/readyz")
    assert resp.status_code == 200
