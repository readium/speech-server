import asyncio
from collections.abc import Callable
from typing import Any

import anyio

_semaphore: asyncio.Semaphore | None = None


def init_semaphore(max_concurrent: int) -> None:
    global _semaphore
    _semaphore = asyncio.Semaphore(max_concurrent)


async def run_inference[T](fn: Callable[..., T], *args: Any) -> T:
    """Offload blocking CPU-bound work to a thread, bounded by the concurrency semaphore.

    Callers needing kwargs should wrap with functools.partial before passing.
    """
    sem = _semaphore
    if sem is None:
        raise RuntimeError("Semaphore not initialized — call init_semaphore() at startup.")
    async with sem:
        return await anyio.to_thread.run_sync(fn, *args)
