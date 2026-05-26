"""Seed a tiny demo NPC roster so the frontend has something to display.

Idempotent: skips files that already exist.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PERSONAS = ROOT / "data" / "personas"
TEMPLATES = ROOT / "data" / "schedule_templates"


DEMO_NPCS = [
    {
        "id": "demo_bob",
        "name": "Bob",
        "role": "graduate",
        "personality": {
            "openness": 0.6, "conscientiousness": 0.7,
            "extraversion": 0.4, "agreeableness": 0.7, "neuroticism": 0.4,
        },
        "preferences": {
            "favorite_locations": ["3877431b", "cb0199d8"],
            "favorite_tags": ["study"],
        },
        "relations": {"demo_alice": "labmate"},
        "initial_location_uid": "3877431b",
        "schedule_template_id": "demo_bob",
    },
]

DEMO_TEMPLATES = [
    {
        "id": "demo_bob",
        "description": "Demo template for Bob.",
        "week": {
            "monday": [
                {"start": "08:00", "end": "10:00", "activity": "lab_work", "location_uid": "3877431b"},
                {"start": "12:00", "end": "12:30", "activity": "have_lunch", "location_uid": "9a49343c"},
                {"start": "14:00", "end": "17:00", "activity": "attend_lecture", "location_uid": "cb0199d8"},
                {"start": "23:00", "end": "23:30", "activity": "sleep", "location_uid": "438038e3"},
            ]
        }
    },
]


def write_if_missing(path: Path, payload: dict) -> bool:
    if path.exists():
        print(f"[keep] {path.name}")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[seed] {path}")
    return True


def main() -> int:
    for n in DEMO_NPCS:
        write_if_missing(PERSONAS / f"{n['id']}.json", n)
    for t in DEMO_TEMPLATES:
        write_if_missing(TEMPLATES / f"{t['id']}.json", t)
    return 0


if __name__ == "__main__":
    sys.exit(main())
