from collections.abc import AsyncGenerator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.concurrency import init_semaphore
from app.core.registry import ProviderRegistry
from app.core.voice_catalog import VoiceCatalog
from app.main import create_app
from app.providers.fake import FakeProvider


@pytest.fixture(autouse=True)
def mock_ffmpeg(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.drivers.ffmpeg as ffmpeg_mod

    monkeypatch.setattr(ffmpeg_mod, "is_available", lambda *_: True)

    async def _fake_encode(pcm: bytes, sample_rate: int, format: str, **kwargs: object) -> bytes:
        return b"\x00" * 200

    monkeypatch.setattr(ffmpeg_mod, "encode", _fake_encode)


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    # lifespan doesn't fire with ASGITransport — bootstrap state manually
    init_semaphore(2)
    registry = ProviderRegistry()
    registry.register(FakeProvider())
    catalog = VoiceCatalog(registry)
    await catalog.load()
    app.state.registry = registry
    app.state.voice_catalog = catalog
    app.state.ready = True

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
