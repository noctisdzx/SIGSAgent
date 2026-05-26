"""Async pub/sub for tick / agent_decision / memory_update events.

Each WebSocket client gets a private `asyncio.Queue` subscription. To help
late subscribers catch up, the bus also keeps a ring buffer of the last
`BUFFER_SIZE` events; on `subscribe()`, those are replayed into the new
queue before any live events.
"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any, Deque

BUFFER_SIZE = 200


class EventBus:
    def __init__(self, buffer_size: int = BUFFER_SIZE) -> None:
        self._subscribers: list[asyncio.Queue] = []
        self._buffer: Deque[dict[str, Any]] = deque(maxlen=buffer_size)

    def subscribe(self, maxsize: int = 1000, *, replay: bool = True) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        if replay:
            for ev in self._buffer:
                try:
                    q.put_nowait(ev)
                except asyncio.QueueFull:
                    break
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    def recent(self, n: int | None = None) -> list[dict[str, Any]]:
        if n is None or n >= len(self._buffer):
            return list(self._buffer)
        return list(self._buffer)[-n:]

    async def publish(self, event: dict[str, Any]) -> None:
        self._buffer.append(event)
        for q in list(self._subscribers):
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                await q.put(event)
            except Exception:
                continue


event_bus = EventBus()
