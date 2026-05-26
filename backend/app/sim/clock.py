"""5-min tick scheduler (asyncio-based).

`sim_tick_seconds` = how much sim-world time one tick represents (default 300s = 5min).
`sim_real_tick_seconds` = how long the real-world wall waits between ticks (default 1s
 for fast-forwarded simulation; raise for "real-time" feel).
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Awaitable, Callable

from app.settings import get_settings


class TickClock:
    def __init__(self, on_tick: Callable[[int], Awaitable[None]]) -> None:
        self.on_tick = on_tick
        self._task: asyncio.Task | None = None
        self._running = False
        self._tick_index = 0

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def step(self) -> None:
        await self._fire()

    @property
    def sim_tick_delta(self) -> timedelta:
        return timedelta(seconds=get_settings().sim_tick_seconds)

    async def _loop(self) -> None:
        while self._running:
            await self._fire()
            await asyncio.sleep(get_settings().sim_real_tick_seconds)

    async def _fire(self) -> None:
        await self.on_tick(self._tick_index)
        self._tick_index += 1
