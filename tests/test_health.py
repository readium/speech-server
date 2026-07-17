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


@pytest.mark.route
async def test_readiness_gate_on_model_endpoints(app: FastAPI, client: AsyncClient) -> None:
    """While models are still loading (ready=False), endpoints that NEED the models
    return 503; model-independent ones stay up (the server never blocks at startup)."""
    app.state.ready = False
    # up regardless — liveness + config-only capabilities
    assert (await client.get("/healthz")).status_code == 200
    assert (await client.get("/service")).status_code == 200
    # gated — need loaded models
    assert (await client.get("/readyz")).status_code == 503
    assert (await client.get("/voices")).status_code == 503
    assert (await client.post("/synthesize", json={"text": "hi"})).status_code == 503
