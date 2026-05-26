"""Weekly schedule templates (like a class timetable).

Each template only defines *key* time blocks per weekday (1h/2h granularity).
Gaps between blocks are filled at runtime by `decision/slot_filler.py` using
the `FragmentLibrary`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TemplateBlock:
    start: str  # "HH:MM"
    end: str    # "HH:MM"
    activity: str
    location_uid: str
    # Optional GOAP goal state (e.g. {"agent.location_uid": "...", "agent.energy": ">=3"}).
    target_state: dict[str, Any] = field(default_factory=dict)
    # Narrative copy for the frontend; runtime ignores.
    narrative_zh: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TemplateBlock":
        """Construct from a JSON dict, tolerating extra fields."""
        return cls(
            start=d["start"],
            end=d["end"],
            activity=d["activity"],
            location_uid=d["location_uid"],
            target_state=dict(d.get("target_state") or {}),
            narrative_zh=d.get("narrative_zh"),
        )


@dataclass
class ScheduleTemplate:
    id: str
    description: str
    week: dict[str, list[TemplateBlock]]

    @classmethod
    def from_json(cls, path: Path) -> "ScheduleTemplate":
        raw = json.loads(path.read_text(encoding="utf-8"))
        week = {
            day: [TemplateBlock.from_dict(b) for b in blocks]
            for day, blocks in raw.get("week", {}).items()
        }
        return cls(id=raw["id"], description=raw.get("description", ""), week=week)

    def blocks_for(self, weekday_name: str) -> list[TemplateBlock]:
        return list(self.week.get(weekday_name, []))

    def current_block_for(
        self,
        weekday_name: str,
        hh_mm: str,
    ) -> TemplateBlock | None:
        """Return the template block covering `hh_mm` on `weekday_name`, if any.

        Boundary: block is `[start, end)` so a query at exactly `end` is *not*
        covered; this matches how `DailyTimeline` slots are aligned.
        """
        for b in self.week.get(weekday_name, []):
            if b.start <= hh_mm < b.end:
                return b
        return None
