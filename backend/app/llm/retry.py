"""Retry / timeout / degrade helpers.

Strategy (used by `MemoryCompressor`, `SlotFiller`, etc.):
    1. Try real LLM call with `tenacity` exponential backoff (LLM_MAX_RETRIES).
    2. On exhaustion or timeout, fall back to `MockLLMAdapter`.
    3. Mark the produced artifact `degraded=True` so the UI can flag it.

We retry on transient transport / parsing errors only:
    httpx.HTTPError, httpx.TimeoutException, ValueError (bad JSON).

We deliberately do NOT retry on:
    httpx.HTTPStatusError 401 / 403 (auth), 400 (bad request) — these
    indicate misconfiguration, not transient flakiness.
"""

from __future__ import annotations

from typing import Awaitable, Callable, TypeVar

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.settings import get_settings

T = TypeVar("T")


_NON_RETRYABLE_STATUS = {400, 401, 403, 404, 422}


def _should_retry(exc: BaseException) -> bool:
    """Retry on transient errors; bail out on auth / config errors."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code not in _NON_RETRYABLE_STATUS
    if isinstance(exc, (httpx.TimeoutException, httpx.HTTPError)):
        return True
    if isinstance(exc, ValueError):
        return True
    return False


def make_retry() -> AsyncRetrying:
    s = get_settings()
    return AsyncRetrying(
        stop=stop_after_attempt(s.llm_max_retries),
        wait=wait_exponential(multiplier=0.5, max=4),
        retry=retry_if_exception(_should_retry),
        reraise=True,
    )


async def with_fallback(
    primary: Callable[[], Awaitable[T]],
    fallback: Callable[[], Awaitable[T]],
) -> tuple[T, bool]:
    """Run `primary` with retry; on failure, run `fallback`.

    Returns (result, degraded). `degraded=True` when fallback was used.
    """
    try:
        async for attempt in make_retry():
            with attempt:
                return await primary(), False
    except Exception:
        return await fallback(), True
    return await fallback(), True  # pragma: no cover (safety)


# ------------------------------------------------------------------
# Convenience alias preferred by newer callers.
# ------------------------------------------------------------------
async def safe_call(
    primary: Callable[[], Awaitable[T]],
    fallback: Callable[[], Awaitable[T]],
) -> tuple[T, bool]:
    """Typed alias for `with_fallback`. Same semantics."""
    return await with_fallback(primary, fallback)
