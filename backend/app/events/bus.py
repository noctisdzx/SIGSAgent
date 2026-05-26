"""Async pub/sub for tick / agent_decision / memory_update events.

Frontend WebSocket clients each get a private asyncio.Queue subscription.
"""

from __future__ import annotations

import asyncio
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self, maxsize: int = 1000) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    async def publish(self, event: dict[str, Any]) -> None:
        for q in list(self._subscribers):
            if q.full():
                # Drop oldest to keep the bus lossy-but-live.
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            await q.put(event)


event_bus = EventBus()
