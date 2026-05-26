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


def _block_footprint(template, weekday: str) -> tuple[int, int]:
    """Return `(raw_sum, unique_slots)` for the template's `weekday`.

    `raw_sum` matches `populate_from_template`'s `n_written` (block lengths
    summed, may overcount when consecutive blocks share a boundary slot due
    to integer-ceil rounding). `unique_slots` is the number of *distinct*
    timeline indices the blocks actually occupy.
    """
    raw_sum = 0
    seen: set[int] = set()
    for b in template.blocks_for(weekday):
        sh, sm = map(int, b.start.split(":"))
        eh, em = map(int, b.end.split(":"))
        a = (sh * 60 + sm) // SLOT_MINUTES
        z = (eh * 60 + em) // SLOT_MINUTES
        a = max(0, min(SLOTS_PER_DAY, a))
        z = max(a, min(SLOTS_PER_DAY, z))
        if z <= a:
            continue
        raw_sum += z - a
        for k in range(a, z):
            seen.add(k)
    return raw_sum, len(seen)


def test_populate_from_template_demo_alice():
    template = ScheduleTemplate.from_json(DEMO_TEMPLATE)
    tl = DailyTimeline(date(2026, 5, 25))  # Monday
    written = tl.populate_from_template(template, "monday")
    raw_sum, unique_slots = _block_footprint(template, "monday")
    assert written == raw_sum > 0
    template_count = sum(1 for s in tl.slots if s.kind == SlotKind.TEMPLATE)
    empty_count = sum(1 for s in tl.slots if s.kind == SlotKind.EMPTY)
    assert template_count == unique_slots
    assert template_count + empty_count == SLOTS_PER_DAY


def test_no_overlap_corrupts_kind_flags():
    """Back-to-back blocks (same end/start minute) are allowed by the generator.
    What we *do* require: every populated slot has a non-empty source_id and a
    valid activity, and source_id transitions only happen at slot boundaries.
    """
    template = ScheduleTemplate.from_json(DEMO_TEMPLATE)
    tl = DailyTimeline(date(2026, 5, 25))
    tl.populate_from_template(template, "monday")
    for s in tl.slots:
        if s.kind == SlotKind.TEMPLATE:
            assert s.source_id, "template slot missing source_id"
            assert s.activity, "template slot missing activity"
            assert s.location_uid, "template slot missing location_uid"


def test_gaps_complement_template():
    template = ScheduleTemplate.from_json(DEMO_TEMPLATE)
    tl = DailyTimeline(date(2026, 5, 25))
    tl.populate_from_template(template, "monday")

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
    template_count = sum(1 for s in tl.slots if s.kind == SlotKind.TEMPLATE)
    total_empty = sum(end - start for start, end in tl.gaps())
    assert total_empty == SLOTS_PER_DAY - template_count


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
    # Pick a deterministic block from inside the template itself.
    monday_blocks = template.blocks_for("monday")
    assert monday_blocks, "template has no monday blocks"
    first = monday_blocks[0]
    sh, sm = map(int, first.start.split(":"))
    eh, em = map(int, first.end.split(":"))
    # Mid-point of first block must resolve to that block.
    mid_min = ((sh * 60 + sm) + (eh * 60 + em)) // 2
    mid = f"{mid_min // 60:02d}:{mid_min % 60:02d}"
    block = template.current_block_for("monday", mid)
    assert block is not None
    assert block.activity == first.activity

    # End-exclusive boundary: a query at exactly `end` must NOT match the same
    # block (it may match the next contiguous block or return None).
    end_str = first.end
    boundary = template.current_block_for("monday", end_str)
    assert boundary is None or boundary.start == first.end

    # A weekday with no overlapping block at 03:00 yields None.
    assert template.current_block_for("monday", "03:00") is None
    # Different weekday: 03:00 should also be empty for any weekday.
    assert template.current_block_for("sunday", "03:00") is None
