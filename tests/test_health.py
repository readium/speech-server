import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


@pytest.mark.route
async def test_healthz(client: AsyncClient) -> None:
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.route
async def test_readyz_when_ready(client: AsyncClient) -> None:
    resp = await client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.route
async def test_readyz_before_ready(app: FastAPI) -> None:
    """Simulate app not yet ready."""
    app.state.ready = False
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/readyz")
        assert resp.status_code == 503
        assert resp.json()["type"] == "https://readium.org/speech-server/error#service_not_ready"
