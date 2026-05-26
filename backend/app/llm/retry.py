"""Retry / timeout / degrade helpers.

Strategy (used by `MemoryCompressor`, `SlotFiller`, etc.):
    1. Try real LLM call with `tenacity` exponential backoff (LLM_MAX_RETRIES).
    2. On exhaustion or timeout, fall back to `MockLLMAdapter`.
    3. Mark the produced artifact `degraded=True` so the UI can flag it.
"""

from __future__ import annotations

from typing import Awaitable, Callable, TypeVar

from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.settings import get_settings

T = TypeVar("T")


def make_retry() -> AsyncRetrying:
    s = get_settings()
    return AsyncRetrying(
        stop=stop_after_attempt(s.llm_max_retries),
        wait=wait_exponential(multiplier=0.5, max=4),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )


async def with_fallback(
    primary: Callable[[], Awaitable[T]],
    fallback: Callable[[], Awaitable[T]],
) -> tuple[T, bool]:
    """Return (result, degraded). degraded=True when fallback was used."""
    try:
        async for attempt in make_retry():
            with attempt:
                return await primary(), False
    except Exception:
        return await fallback(), True
    return await fallback(), True  # pragma: no cover (safety)
