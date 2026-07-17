import pytest
from httpx import AsyncClient


@pytest.mark.route
async def test_list_voices_returns_all(client: AsyncClient) -> None:
    resp = await client.get("/voices")
    assert resp.status_code == 200
    voices = resp.json()
    assert len(voices) == 2
    ids = {v["identifier"] for v in voices}
    assert "urn:readium:tts:fake:en-US-standard" in ids
    assert "urn:readium:tts:fake:fr-FR-standard" in ids


@pytest.mark.route
async def test_list_voices_shape(client: AsyncClient) -> None:
    resp = await client.get("/voices")
    voice = resp.json()[0]
    required = (
        "name",
        "originalName",
        "provider",
        "identifier",
        "language",
        "controls",
    )
    for field in required:
        assert field in voice, f"Missing field: {field}"


@pytest.mark.route
async def test_filter_by_language(client: AsyncClient) -> None:
    resp = await client.get("/voices", params={"language": "en"})
    assert resp.status_code == 200
    voices = resp.json()
    assert len(voices) == 1
    assert voices[0]["language"] == "en-US"


@pytest.mark.route
async def test_filter_by_provider(client: AsyncClient) -> None:
    resp = await client.get("/voices", params={"provider": "fake"})
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.route
async def test_filter_by_unknown_language_returns_empty(client: AsyncClient) -> None:
    resp = await client.get("/voices", params={"language": "zh"})
    assert resp.status_code == 200
    assert resp.json() == []
