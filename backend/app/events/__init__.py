"""Process-internal event bus broadcast to WebSocket subscribers."""

from .bus import event_bus, EventBus

__all__ = ["event_bus", "EventBus"]
