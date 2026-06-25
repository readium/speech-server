import pytest


@pytest.mark.route
async def test_healthz(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.route
async def test_readyz_when_ready(client):
    resp = await client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.route
async def test_readyz_before_ready(app):
    """Simulate app not yet ready."""
    from httpx import ASGITransport, AsyncClient

    app.state.ready = False
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/readyz")
        assert resp.status_code == 503
        assert resp.json() == {"status": "not ready"}
