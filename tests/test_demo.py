import pytest
from httpx import AsyncClient


@pytest.mark.route
async def test_demo_page(client: AsyncClient) -> None:
    resp = await client.get("/demo")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
