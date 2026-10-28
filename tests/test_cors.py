"""CORS for the Readium Speech demos, plus the busy-queue and API-key guards."""

import asyncio

import pytest
from httpx import AsyncClient

from app.api.errors import RateLimited
from app.config.settings import Settings, settings
from app.core import concurrency

_DEMO = "https://readium.org"


async def test_preflight_allows_demo_origin(client: AsyncClient) -> None:
    resp = await client.options(
        "/synthesize",
        headers={
            "Origin": _DEMO,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == _DEMO


async def test_preflight_rejects_other_origin(client: AsyncClient) -> None:
    resp = await client.options(
        "/synthesize",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in resp.headers


async def test_voices_exposes_pagination_headers_to_demo(client: AsyncClient) -> None:
    resp = await client.get("/voices", headers={"Origin": _DEMO})
    assert resp.headers["access-control-allow-origin"] == _DEMO
    assert "x-total-count" in resp.headers["access-control-expose-headers"].lower()


def test_cors_origin_list_strips_slash_and_blanks() -> None:
    s = Settings(_env_file=None, cors_origins=" https://a.org/ ,, https://b.org")  # type: ignore[arg-type]
    assert s.cors_origin_list == ["https://a.org", "https://b.org"]


def test_api_key_enabled_is_rejected() -> None:
    with pytest.raises(ValueError, match="API_KEY_ENABLED is not supported"):
        Settings(_env_file=None, api_key_enabled=True, api_key="k")  # type: ignore[arg-type]


async def test_run_inference_busy_returns_429(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "synthesis_queue_timeout_seconds", 0.05)
    concurrency.init_semaphore(1)
    sem = concurrency._semaphore  # noqa: SLF001
    assert sem is not None
    await sem.acquire()  # the only slot is taken
    with pytest.raises(RateLimited):
        await concurrency.run_inference(lambda: None)
    sem.release()
    assert await asyncio.wait_for(concurrency.run_inference(lambda: 7), 2) == 7


async def test_busy_synthesize_returns_429_with_retry_after(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "synthesis_queue_timeout_seconds", 0.05)
    concurrency.init_semaphore(1)
    sem = concurrency._semaphore  # noqa: SLF001
    assert sem is not None
    await sem.acquire()
    voice = (await client.get("/voices")).json()[0]["identifier"]
    resp = await client.post("/synthesize", json={"text": "Hello.", "voice": voice})
    sem.release()
    assert resp.status_code == 429
    assert resp.headers["retry-after"] == "5"
    assert resp.headers["content-type"].startswith("application/problem+json")
