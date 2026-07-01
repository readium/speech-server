import pytest
from httpx import AsyncClient

_VOICE = "urn:readium:tts:fake:en-US-standard"
_URL = "/v1/synthesize"


@pytest.mark.route
async def test_text_too_long_returns_413(client: AsyncClient) -> None:
    resp = await client.post(_URL, json={"text": "x" * 2001, "voice": _VOICE})
    assert resp.status_code == 413
    assert resp.headers["content-type"] == "application/problem+json"
    body = resp.json()
    assert body["type"] == "https://readium.org/speech-server/error#payload_too_large"
    assert body["title"] == "Payload Too Large"
    assert body["status"] == 413
    assert "received 2001" in body["detail"]
    assert body["instance"] == f"urn:uuid:{resp.headers['x-request-id']}"
    assert "errors" not in body


@pytest.mark.route
async def test_unknown_route_returns_about_blank_problem(client: AsyncClient) -> None:
    resp = await client.get("/v1/does-not-exist")
    assert resp.status_code == 404
    assert resp.headers["content-type"] == "application/problem+json"
    body = resp.json()
    assert body["type"] == "about:blank"
    assert body["title"] == "Not Found"
    assert body["status"] == 404


@pytest.mark.route
async def test_validation_error_includes_field_errors(client: AsyncClient) -> None:
    resp = await client.post(_URL, json={"text": "Hello"})  # missing required "voice"
    assert resp.status_code == 422
    body = resp.json()
    assert body["type"] == "https://readium.org/speech-server/error#validation_failed"
    assert body["title"] == "Invalid Request"
    assert any(err["loc"] == ["body", "voice"] for err in body["errors"])


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
