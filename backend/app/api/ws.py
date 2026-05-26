"""WebSocket hub: broadcasts tick events / decisions / memory updates.

Event envelope::

    {
        "type": "tick" | "agent_decision" | "memory_update" | "scene_delta" | "behavior",
        "ts_sim": "2026-05-26T08:00:00",
        "agent_id": "demo_alice",
        "payload": { ... }
    }
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.events.bus import event_bus

router = APIRouter(tags=["ws"])


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = event_bus.subscribe()
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        event_bus.unsubscribe(queue)
