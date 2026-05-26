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
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .template import ScheduleTemplate


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
    # GOAP goal state authored by the template (forwarded to planner).
    target_state: dict = field(default_factory=dict)
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
                     source_id: str, target_state: dict | None = None) -> None:
        ts = dict(target_state or {})
        for k in range(idx_from, idx_to):
            self.slots[k] = Slot(
                index=k,
                start=self.slots[k].start,
                end=self.slots[k].end,
                kind=SlotKind.TEMPLATE,
                activity=activity,
                location_uid=location_uid,
                source_id=source_id,
                target_state=dict(ts),
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

    # ----- helpers -----

    def slot_at(self, dt: datetime) -> Slot | None:
        """Return the slot covering `dt` on this day, or None if `dt` falls
        outside the day. Aligns to 5-min boundaries from midnight.
        """
        if dt.date() != self.day:
            return None
        minutes = dt.hour * 60 + dt.minute
        idx = minutes // SLOT_MINUTES
        if 0 <= idx < SLOTS_PER_DAY:
            return self.slots[idx]
        return None

    def populate_from_template(
        self,
        template: "ScheduleTemplate",
        weekday_name: str,
    ) -> int:
        """Mark TEMPLATE slots from a parsed template's blocks for `weekday_name`.

        Returns the number of slots written. Skips blocks that cannot be parsed.
        Idempotent: re-running for the same weekday overwrites the same slots.
        """
        n_written = 0
        for block in template.blocks_for(weekday_name):
            try:
                start_idx = _hhmm_to_slot_idx(block.start)
                end_idx = _hhmm_to_slot_idx(block.end)
            except ValueError:
                continue
            if end_idx <= start_idx:
                continue
            end_idx = min(end_idx, SLOTS_PER_DAY)
            block_id = f"{template.id}:{weekday_name}:{block.start}-{block.end}"
            self.set_template(
                idx_from=start_idx,
                idx_to=end_idx,
                activity=block.activity,
                location_uid=block.location_uid,
                source_id=block_id,
                target_state=getattr(block, "target_state", None) or {},
            )
            n_written += end_idx - start_idx
        return n_written


def _hhmm_to_slot_idx(hh_mm: str) -> int:
    """Convert "HH:MM" to a slot index in [0, SLOTS_PER_DAY]."""
    if not isinstance(hh_mm, str) or ":" not in hh_mm:
        raise ValueError(f"bad HH:MM string: {hh_mm!r}")
    hh, mm = hh_mm.split(":", 1)
    h = int(hh)
    m = int(mm)
    if not (0 <= h <= 24 and 0 <= m < 60):
        raise ValueError(f"bad HH:MM: {hh_mm!r}")
    minutes = h * 60 + m
    return minutes // SLOT_MINUTES
