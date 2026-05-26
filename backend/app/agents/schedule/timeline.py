"""Per-NPC daily timeline at 5-min granularity.

A `DailyTimeline` is a sequence of `Slot`s for one calendar day.
Each slot is either:
- TEMPLATE: locked in from `ScheduleTemplate`,
- FRAGMENT: chosen by `decision/slot_filler.py` to fill a gap,
- EMPTY: not yet decided (and thus not yet a memory).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import Enum


SLOT_MINUTES = 5
SLOTS_PER_DAY = 24 * 60 // SLOT_MINUTES  # 288


class SlotKind(str, Enum):
    EMPTY = "empty"
    TEMPLATE = "template"
    FRAGMENT = "fragment"


@dataclass
class Slot:
    index: int                 # 0..287
    start: datetime
    end: datetime
    kind: SlotKind = SlotKind.EMPTY
    activity: str | None = None
    location_uid: str | None = None
    source_id: str | None = None   # template block id or fragment id
    meta: dict = field(default_factory=dict)


class DailyTimeline:
    def __init__(self, day: date) -> None:
        self.day = day
        base = datetime.combine(day, time(0, 0))
        self.slots: list[Slot] = [
            Slot(
                index=i,
                start=base + timedelta(minutes=SLOT_MINUTES * i),
                end=base + timedelta(minutes=SLOT_MINUTES * (i + 1)),
            )
            for i in range(SLOTS_PER_DAY)
        ]

    # ----- queries -----

    def gaps(self) -> list[tuple[int, int]]:
        """Return [(start_idx, end_idx_exclusive), ...] of EMPTY ranges."""
        gaps: list[tuple[int, int]] = []
        i = 0
        while i < SLOTS_PER_DAY:
            if self.slots[i].kind == SlotKind.EMPTY:
                j = i
                while j < SLOTS_PER_DAY and self.slots[j].kind == SlotKind.EMPTY:
                    j += 1
                gaps.append((i, j))
                i = j
            else:
                i += 1
        return gaps

    # ----- mutation -----

    def set_template(self, idx_from: int, idx_to: int, activity: str, location_uid: str,
                     source_id: str) -> None:
        for k in range(idx_from, idx_to):
            self.slots[k] = Slot(
                index=k,
                start=self.slots[k].start,
                end=self.slots[k].end,
                kind=SlotKind.TEMPLATE,
                activity=activity,
                location_uid=location_uid,
                source_id=source_id,
            )

    def set_fragment(self, idx_from: int, idx_to: int, activity: str,
                     location_uid: str | None, fragment_id: str) -> None:
        for k in range(idx_from, idx_to):
            self.slots[k] = Slot(
                index=k,
                start=self.slots[k].start,
                end=self.slots[k].end,
                kind=SlotKind.FRAGMENT,
                activity=activity,
                location_uid=location_uid,
                source_id=fragment_id,
            )
