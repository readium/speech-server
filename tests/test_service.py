import pytest
from httpx import AsyncClient


@pytest.mark.route
async def test_service_shape(client: AsyncClient) -> None:
    resp = await client.get("/service")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["output"]["formats"]) >= {"wav", "mp3", "opus"}
    assert body["output"]["default"] == "wav"
    assert body["limits"]["maxTextLength"] > 0
    assert body["limits"]["maxConcurrentSyntheses"] > 0
    assert any(p["id"] == "fake" for p in body["providers"])


@pytest.mark.route
async def test_service_provider_capabilities_shape(client: AsyncClient) -> None:
    resp = await client.get("/service")
    provider = next(p for p in resp.json()["providers"] if p["id"] == "fake")
    assert "installedLanguages" in provider
    # provider-level defaults, mirrored from /voices — but controls shows every key,
    # including disabled ones, since this is "what's possible" not "what's on"
    assert set(provider["controls"]) == {"pitch", "speed", "ssml", "boundary"}
    assert all(isinstance(v, bool) for v in provider["controls"].values())
    assert "quality" in provider


@pytest.mark.route
async def test_service_has_no_per_voice_list(client: AsyncClient) -> None:
    """The voice list lives on /voices; /service stays a server-wide summary."""
    resp = await client.get("/service")
    provider = next(p for p in resp.json()["providers"] if p["id"] == "fake")
    assert "voices" not in provider
