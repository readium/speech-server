import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    app.state.ready = True  # ASGITransport doesn't fire lifespan; set manually for tests
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
