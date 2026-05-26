"""Weekly schedule templates (like a class timetable).

Each template only defines *key* time blocks per weekday (1h/2h granularity).
Gaps between blocks are filled at runtime by `decision/slot_filler.py` using
the `FragmentLibrary`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TemplateBlock:
    start: str  # "HH:MM"
    end: str    # "HH:MM"
    activity: str
    location_uid: str


@dataclass
class ScheduleTemplate:
    id: str
    description: str
    week: dict[str, list[TemplateBlock]]

    @classmethod
    def from_json(cls, path: Path) -> "ScheduleTemplate":
        raw = json.loads(path.read_text(encoding="utf-8"))
        week = {
            day: [TemplateBlock(**b) for b in blocks]
            for day, blocks in raw.get("week", {}).items()
        }
        return cls(id=raw["id"], description=raw.get("description", ""), week=week)

    def blocks_for(self, weekday_name: str) -> list[TemplateBlock]:
        return list(self.week.get(weekday_name, []))
