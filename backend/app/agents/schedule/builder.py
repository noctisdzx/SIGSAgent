"""Convert a confirmed schedule item (template block or chosen fragment)
into a `ShortTermItem` and append it to the agent's STM.

This is the *only* source of STM entries per the spec.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from app.agents.memory.short_term import ShortTermItem
from .timeline import Slot


def schedule_item_to_stm(slot: Slot, agent_id: str) -> ShortTermItem:
    text = f"[{slot.start.strftime('%H:%M')}-{slot.end.strftime('%H:%M')}] " \
           f"{slot.activity or '(no activity)'}@{slot.location_uid or '?'}"
    return ShortTermItem(
        id=f"stm_{uuid.uuid4().hex[:8]}",
        text=text,
        ts=datetime.utcnow(),
        source=f"schedule:{slot.source_id}",
        meta={"agent_id": agent_id, "slot_index": slot.index, "kind": slot.kind.value},
    )
