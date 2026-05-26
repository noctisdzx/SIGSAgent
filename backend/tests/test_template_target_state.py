"""End-to-end checks that template `target_state` survives JSON -> Slot.

These tests pin the contract:
- Every generated template JSON in `data/schedule_templates/` carries a
  `target_state` dict on every block.
- `TemplateBlock.from_dict` propagates the field.
- `DailyTimeline.populate_from_template` forwards it to every covered slot.
- `Slot.target_state` is the same dict object semantics (key set + values).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.agents.schedule.template import ScheduleTemplate, TemplateBlock
from app.agents.schedule.timeline import DailyTimeline, SlotKind


REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = REPO_ROOT / "data" / "schedule_templates"


def _all_templates() -> list[Path]:
    return sorted(TEMPLATES_DIR.glob("*.json"))


def test_all_template_blocks_carry_target_state():
    files = _all_templates()
    assert files, "no schedule templates found"
    weekdays = {"monday", "tuesday", "wednesday", "thursday",
                "friday", "saturday", "sunday"}
    n_blocks = 0
    for p in files:
        raw = json.loads(p.read_text(encoding="utf-8"))
        assert set(raw.get("week", {}).keys()) == weekdays, (
            f"{p.name}: weekdays != Mon..Sun"
        )
        for day, blocks in raw["week"].items():
            assert blocks, f"{p.name}.{day}: empty"
            for b in blocks:
                assert "target_state" in b, (
                    f"{p.name}.{day}: block missing target_state: {b}"
                )
                ts = b["target_state"]
                assert isinstance(ts, dict) and ts, (
                    f"{p.name}.{day}: target_state must be non-empty dict"
                )
                n_blocks += 1
    assert n_blocks > 60 * 7  # 61 npcs * 7 days at minimum


def test_template_block_from_dict_keeps_target_state_and_narrative():
    b = TemplateBlock.from_dict({
        "start": "07:00", "end": "07:30",
        "activity": "wake_up", "location_uid": "room_a",
        "narrative_zh": "起床",
        "target_state": {"agent.location_uid": "room_a", "agent.energy": ">=3"},
        "extra_field_should_be_ignored": True,
    })
    assert b.target_state == {
        "agent.location_uid": "room_a",
        "agent.energy": ">=3",
    }
    assert b.narrative_zh == "起床"


@pytest.mark.parametrize("name", ["npc01_lin_xiaowei.json", "demo_alice.json"])
def test_populate_forwards_target_state_to_slots(name: str):
    path = TEMPLATES_DIR / name
    if not path.exists():
        pytest.skip(f"{name} not in templates dir")
    tpl = ScheduleTemplate.from_json(path)
    tl = DailyTimeline(date(2026, 5, 25))  # Monday
    written = tl.populate_from_template(tpl, "monday")
    assert written > 0

    # Pick the first monday block from JSON, find a slot inside its time range,
    # and verify Slot.target_state matches what the template carried.
    monday_blocks = tpl.blocks_for("monday")
    first = monday_blocks[0]
    assert first.target_state, f"{name}: first monday block has no target_state"

    sh, sm = map(int, first.start.split(":"))
    eh, em = map(int, first.end.split(":"))
    mid_min = ((sh * 60 + sm) + (eh * 60 + em)) // 2
    mid_idx = mid_min // 5  # SLOT_MINUTES
    s = tl.slots[mid_idx]
    assert s.kind == SlotKind.TEMPLATE
    assert s.target_state == first.target_state, (
        f"{name}: mid-slot target_state ({s.target_state}) != "
        f"block target_state ({first.target_state})"
    )
