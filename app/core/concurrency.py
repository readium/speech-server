import asyncio
from collections.abc import Callable
from typing import Any

import anyio

from app.api.errors import RateLimited
from app.config.settings import settings

_semaphore: asyncio.Semaphore | None = None
_RETRY_AFTER_SECONDS = "5"  # a slot usually frees within one synthesis (a few seconds)


def init_semaphore(max_concurrent: int) -> None:
    global _semaphore
    _semaphore = asyncio.Semaphore(max_concurrent)


async def run_inference[T](fn: Callable[..., T], *args: Any) -> T:
    """Offload blocking CPU-bound work to a thread, bounded by the concurrency semaphore.

    Waiting for a free slot is capped (SYNTHESIS_QUEUE_TIMEOUT_SECONDS): past that the request
    fails fast with 429 instead of queueing behind other work indefinitely.
    Callers needing kwargs should wrap with functools.partial before passing.
    """
    sem = _semaphore
    if sem is None:
        raise RuntimeError("Semaphore not initialized — call init_semaphore() at startup.")
    try:
        await asyncio.wait_for(sem.acquire(), settings.synthesis_queue_timeout_seconds)
    except TimeoutError as exc:
        raise RateLimited(
            "Server is busy — try again shortly.", headers={"Retry-After": _RETRY_AFTER_SECONDS}
        ) from exc
    try:
        return await anyio.to_thread.run_sync(fn, *args)
    finally:
        sem.release()
