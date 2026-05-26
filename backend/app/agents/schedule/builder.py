"""Convert a confirmed schedule item (template block or chosen fragment)
into a `ShortTermItem` and append it to the agent's STM.

This is the *only* source of STM entries per the spec.

`bulk_build_for_day` collapses contiguous slots that share the same
(activity, location_uid, source_id) into a single STM entry, so a
2-hour `attend_class` block becomes ONE memory rather than 24.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Iterator

from app.agents.memory.short_term import ShortTermItem

from .timeline import DailyTimeline, Slot, SlotKind


def schedule_item_to_stm(slot: Slot, agent_id: str, now: datetime | None = None) -> ShortTermItem:
    """Build an STM entry tagged with the in-game time.

    `ts` defaults to `slot.start` (the in-game start of the slot) so that
    memories chronologically align with the sim clock rather than wall-clock.
    Caller may override with `now` (e.g. `world.sim_time`) to record at the
    precise tick when the slot was confirmed.
    """
    text = (
        f"[{slot.start.strftime('%H:%M')}-{slot.end.strftime('%H:%M')}] "
        f"{slot.activity or '(no activity)'}@{slot.location_uid or '?'}"
    )
    # English mirror — activity names are already snake_case English (move,
    # sleep, lab_work, attend_class…) so the same shape reads fine in English.
    text_en = text
    return ShortTermItem(
        id=f"stm_{uuid.uuid4().hex[:8]}",
        text=text,
        text_en=text_en,
        ts=now or slot.start,
        source=f"schedule:{slot.source_id}",
        meta={
            "agent_id": agent_id,
            "slot_index": slot.index,
            "kind": slot.kind.value,
            "activity": slot.activity,
            "location_uid": slot.location_uid,
            "slot_start": slot.start.isoformat(),
            "slot_end": slot.end.isoformat(),
        },
    )


def _runs(timeline: DailyTimeline) -> Iterator[tuple[Slot, Slot]]:
    """Yield (first_slot, last_slot) for each maximal run of contiguous
    non-empty slots that share (activity, location_uid, source_id).
    """
    slots = timeline.slots
    i = 0
    n = len(slots)
    while i < n:
        if slots[i].kind == SlotKind.EMPTY:
            i += 1
            continue
        j = i
        key = (slots[i].activity, slots[i].location_uid, slots[i].source_id, slots[i].kind)
        while (
            j + 1 < n
            and slots[j + 1].kind != SlotKind.EMPTY
            and (
                slots[j + 1].activity,
                slots[j + 1].location_uid,
                slots[j + 1].source_id,
                slots[j + 1].kind,
            ) == key
        ):
            j += 1
        yield slots[i], slots[j]
        i = j + 1


def bulk_build_for_day(timeline: DailyTimeline, agent_id: str) -> list[ShortTermItem]:
    """One STM entry per contiguous activity range across the whole day.

    Used at the start of the day to bootstrap STM with the day's plan
    rather than waiting for slot-by-slot ticking. `ts` is the in-game start
    of each contiguous run.
    """
    items: list[ShortTermItem] = []
    for first, last in _runs(timeline):
        text = (
            f"[{first.start.strftime('%H:%M')}-{last.end.strftime('%H:%M')}] "
            f"{first.activity or '(no activity)'}@{first.location_uid or '?'}"
        )
        items.append(
            ShortTermItem(
                id=f"stm_{uuid.uuid4().hex[:8]}",
                text=text,
                text_en=text,
                ts=first.start,
                source=f"schedule:{first.source_id}",
                meta={
                    "agent_id": agent_id,
                    "slot_index_from": first.index,
                    "slot_index_to": last.index,
                    "kind": first.kind.value,
                    "activity": first.activity,
                    "location_uid": first.location_uid,
                    "slot_start": first.start.isoformat(),
                    "slot_end": last.end.isoformat(),
                },
            )
        )
    return items
