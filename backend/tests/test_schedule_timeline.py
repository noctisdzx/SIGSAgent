"""DailyTimeline tests:
- exactly 288 5-min slots,
- TEMPLATE blocks from `demo_alice` populate without overlap,
- `gaps()` is the exact complement of populated slots,
- `slot_at` resolves wall-clock time correctly.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from app.agents.schedule.template import ScheduleTemplate
from app.agents.schedule.timeline import (
    SLOT_MINUTES,
    SLOTS_PER_DAY,
    DailyTimeline,
    SlotKind,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_TEMPLATE = REPO_ROOT / "data" / "schedule_templates" / "demo_alice.json"


def test_slot_count():
    tl = DailyTimeline(date(2026, 5, 25))  # 2026-05-25 is a Monday
    assert len(tl.slots) == SLOTS_PER_DAY == 288
    assert all((s.end - s.start).total_seconds() == SLOT_MINUTES * 60 for s in tl.slots)


def test_populate_from_template_demo_alice():
    template = ScheduleTemplate.from_json(DEMO_TEMPLATE)
    tl = DailyTimeline(date(2026, 5, 25))  # Monday
    written = tl.populate_from_template(template, "monday")
    # demo_alice monday spans (in minutes):
    # 07:00-07:30 (30) + 08:00-10:00 (120) + 12:00-12:30 (30)
    #   + 14:00-16:00 (120) + 18:30-19:00 (30) + 23:00-23:30 (30) = 360
    assert written == 360 // SLOT_MINUTES == 72

    template_count = sum(1 for s in tl.slots if s.kind == SlotKind.TEMPLATE)
    empty_count = sum(1 for s in tl.slots if s.kind == SlotKind.EMPTY)
    assert template_count == 72
    assert template_count + empty_count == SLOTS_PER_DAY


def test_no_overlap_between_blocks():
    template = ScheduleTemplate.from_json(DEMO_TEMPLATE)
    tl = DailyTimeline(date(2026, 5, 25))
    tl.populate_from_template(template, "monday")
    # Each TEMPLATE slot has exactly one source_id; switching ids must coincide
    # with kind transitions. We verify activities don't bleed into each other:
    # i.e. consecutive non-empty slots with different source_id MUST be allowed
    # only when there's at least one EMPTY slot between, OR explicit boundary.
    last_kind = SlotKind.EMPTY
    last_src = None
    for s in tl.slots:
        if s.kind == SlotKind.TEMPLATE:
            if last_kind == SlotKind.TEMPLATE and last_src != s.source_id:
                # demo_alice has no back-to-back blocks (always a gap),
                # so this should never fire. Assert it.
                raise AssertionError(
                    f"unexpected back-to-back template at idx={s.index}: "
                    f"{last_src!r} -> {s.source_id!r}"
                )
            last_src = s.source_id
        else:
            last_src = None
        last_kind = s.kind


def test_gaps_complement_template():
    template = ScheduleTemplate.from_json(DEMO_TEMPLATE)
    tl = DailyTimeline(date(2026, 5, 25))
    tl.populate_from_template(template, "monday")

    # Walk the slots, recompute the gap list manually, compare.
    expected: list[tuple[int, int]] = []
    i = 0
    while i < SLOTS_PER_DAY:
        if tl.slots[i].kind == SlotKind.EMPTY:
            j = i
            while j < SLOTS_PER_DAY and tl.slots[j].kind == SlotKind.EMPTY:
                j += 1
            expected.append((i, j))
            i = j
        else:
            i += 1

    assert tl.gaps() == expected
    # Total empty slots equals SLOTS_PER_DAY - template_count (= 288 - 72)
    total_empty = sum(end - start for start, end in tl.gaps())
    assert total_empty == SLOTS_PER_DAY - 72


def test_slot_at():
    tl = DailyTimeline(date(2026, 5, 25))
    s = tl.slot_at(datetime(2026, 5, 25, 8, 7))
    assert s is not None
    # 8h07 → minute 487, slot index 487 // 5 = 97
    assert s.index == 97
    assert s.start.strftime("%H:%M") == "08:05"

    # midnight boundary
    s0 = tl.slot_at(datetime(2026, 5, 25, 0, 0))
    assert s0 is not None and s0.index == 0

    # other day → None
    assert tl.slot_at(datetime(2026, 5, 26, 0, 0)) is None


def test_template_current_block_for():
    template = ScheduleTemplate.from_json(DEMO_TEMPLATE)
    block = template.current_block_for("monday", "08:30")
    assert block is not None
    assert block.activity == "attend_class"
    # boundary: end-exclusive
    assert template.current_block_for("monday", "10:00") is None
    # outside any block
    assert template.current_block_for("monday", "11:00") is None
    # other day
    assert template.current_block_for("sunday", "08:30") is None
