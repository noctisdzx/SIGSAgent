"""WebSocket hub: broadcasts tick events / decisions / memory updates.

Event envelope::

    {
        "type": "tick" | "agent_decision" | "memory_update" | "scene_delta" | "behavior" | "welcome",
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

    # 1) Welcome message: latest world snapshot + last 50 buffered events.
    app_state = websocket.app.state
    world = getattr(app_state, "world", None)
    sim = getattr(app_state, "sim", None)
    welcome = {
        "type": "welcome",
        "ts_sim": (world.sim_time.isoformat() if world else None),
        "agent_id": None,
        "payload": {
            "world": world.snapshot() if world else None,
            "sim_running": bool(getattr(sim, "is_running", False)),
            "recent_events": event_bus.recent(50),
        },
    }
    try:
        await websocket.send_json(welcome)
    except Exception:
        await websocket.close()
        return

    # 2) Subscribe; we asked recent events to be replayed via welcome, so skip replay here.
    queue = event_bus.subscribe(replay=False)
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        event_bus.unsubscribe(queue)
