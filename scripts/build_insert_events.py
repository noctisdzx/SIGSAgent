"""Normalise + enrich the raw `InternationalPhase1_InsertEvents_60.json` into
an LLM-selectable insert-event library: `data/insert_events/insert_events.json`.

An "insert event" is a special A→B trip dropped into a free gap of an NPC's
daily timeline, chosen by an LLM the same way `slot_filler` picks a fragment.
Each event therefore needs a NATURAL-LANGUAGE description + semantic tags +
time, in addition to the machine fields used for pre-filtering/scoring.

This script:
1. Resolves `start`/`end` place names to room UIDs (LOCATION_MAP).
2. Converts `slots` (half-hour count) → `duration_minutes`.
3. Normalises `cause_tags` (1..100) → [0,1], split into OCEAN-5 + 10 drives.
4. Maps the event `role` → eligible persona archetypes.
5. Derives semantic `tags` from the dominant drives + the destination room's
   scene tags (shared vocabulary with `fragments.json`).
6. Bakes a bilingual `description_zh/en` via the LLM (offline, one-time).
   Use `--no-llm` to skip and use a deterministic templated description.

Run from repo root:
    python scripts/build_insert_events.py            # with LLM descriptions
    python scripts/build_insert_events.py --no-llm   # templated descriptions
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "InternationalPhase1_InsertEvents_60.json"
PERSONAS_DIR = ROOT / "data" / "personas"
SCENES_PATH = ROOT / "data" / "scenes" / "guoyi_rooms_v2.json"
OUT_DIR = ROOT / "data" / "insert_events"
OUT_PATH = OUT_DIR / "insert_events.json"

SLOT_MINUTES = 30  # the events were authored on a half-hour grid

# Make the backend package importable for the LLM adapter + load .env.
sys.path.insert(0, str(ROOT / "backend"))

# ---------------------------------------------------------------------------
# Room UIDs (data/scenes/guoyi_rooms_v2.json)
# ---------------------------------------------------------------------------

DORM = "438038e3"
DINING = "9a49343c"
CLASSROOM = "4d7a7e81"
LECTURE = "cb0199d8"
LIBRARY = "64a9bc35"
GARDEN_LOW = "66cb10e7"
GARDEN_ROOF = "7a281fd7"
CAFE_DOWN = "a62839dd"

LOCATION_MAP: dict[str, dict] = {
    "International Phase I Dormitory": {"uid": DORM, "weak": False},
    "H Building": {"uid": CLASSROOM, "weak": False},
    "Heyuan Canteen": {"uid": DINING, "weak": False},
    "Roof Garden": {"uid": GARDEN_ROOF, "weak": False},
    "Study Space": {"uid": LIBRARY, "weak": False},
    "Gym": {"uid": GARDEN_LOW, "weak": True},
    "Lawson": {"uid": CAFE_DOWN, "weak": True},
    "Parcel Station": {"uid": LECTURE, "weak": True},  # mapped to the largest hall
}

OCEAN_KEYS = ["openness", "conscientiousness", "extroversion", "agreeableness", "neuroticism"]
DRIVE_KEYS = [
    "stress", "curiosity", "procrastination", "budget", "loneliness",
    "weather_sensitivity", "health_awareness", "club_engagement",
    "research_interest", "romantic_interest",
]

ROLE_TO_ARCHETYPES: dict[str, list[str]] = {
    "student": ["undergrad", "grad"],
    "faculty": ["faculty"],
    "logistics": ["logistics"],
    "staff": ["faculty", "logistics", "other"],
}

# Drive (when high) -> semantic tags (shared vocabulary with fragments.json).
DRIVE_TO_TAGS: dict[str, list[str]] = {
    "club_engagement": ["social", "club"],
    "loneliness": ["social"],
    "research_interest": ["study"],
    "curiosity": ["leisure"],
    "health_awareness": ["fitness"],
    "romantic_interest": ["romance"],
    "procrastination": ["leisure", "rest"],
    "stress": ["rest"],
}
DRIVE_TAG_THRESHOLD = 0.6
MAX_TAGS = 4


# ---------------------------------------------------------------------------
# Persona archetype classifier
# ---------------------------------------------------------------------------

def classify(persona: dict) -> str:
    profile = persona.get("profile", {})
    role_zh = (profile.get("role_zh") or "") + (profile.get("role_en") or "")
    text = role_zh + " " + persona.get("role", "")
    if any(k in text for k in ("教授", "讲师", "辅导员", "导师", "医生", "Professor", "Faculty")):
        return "faculty"
    if any(k in text for k in ("保卫", "食堂", "图书馆管理员", "保洁", "宿管", "守门人", "处长", "主厨", "Security", "Logistics")):
        return "logistics"
    if any(k in text for k in ("博", "研", "PhD", "Doctor", "research", "Research")):
        return "grad"
    if any(k in text for k in ("大一", "大二", "大三", "大四", "undergrad", "Yr1", "Yr2", "Yr3", "Yr4")):
        return "undergrad"
    return "other"


# ---------------------------------------------------------------------------
# Tag derivation
# ---------------------------------------------------------------------------

def load_scene_tags() -> dict[str, list[str]]:
    if not SCENES_PATH.exists():
        return {}
    scenes = json.loads(SCENES_PATH.read_text(encoding="utf-8"))
    return {r["uid"]: list(r.get("tag", [])) for r in scenes.get("rooms", [])}


def derive_tags(drives: dict[str, float], end_uid: str | None, scene_tags: dict[str, list[str]]) -> list[str]:
    tags: list[str] = []
    # From the destination room's scene tags first (concrete context).
    for t in scene_tags.get(end_uid or "", []):
        if t not in tags:
            tags.append(t)
    # Then from the strongest drives.
    for k in sorted(DRIVE_TO_TAGS, key=lambda k: drives.get(k, 0.0), reverse=True):
        if drives.get(k, 0.0) >= DRIVE_TAG_THRESHOLD:
            for t in DRIVE_TO_TAGS[k]:
                if t not in tags:
                    tags.append(t)
    if not tags:
        tags = ["daily life"]
    return tags[:MAX_TAGS]


# ---------------------------------------------------------------------------
# Build base event records
# ---------------------------------------------------------------------------

def build_event(raw: dict, scene_tags: dict[str, list[str]]) -> dict:
    ct = raw.get("cause_tags", {})
    start_m = LOCATION_MAP.get(raw["start"], {"uid": None, "weak": True})
    end_m = LOCATION_MAP.get(raw["end"], {"uid": None, "weak": True})
    role = raw.get("role", "student")
    slots = int(raw.get("slots", 0))
    drives = {k: round(float(ct.get(k, 0)) / 100.0, 4) for k in DRIVE_KEYS}
    ocean = {k: round(float(ct.get(k, 0)) / 100.0, 4) for k in OCEAN_KEYS}
    return {
        "id": raw["id"],
        "description_zh": "",   # filled by bake step
        "description_en": "",
        "tags": derive_tags(drives, end_m["uid"], scene_tags),
        "role": role,
        "eligible_archetypes": ROLE_TO_ARCHETYPES.get(role, ["other"]),
        "slots": slots,
        "duration_minutes": slots * SLOT_MINUTES,
        "start_name": raw["start"],
        "end_name": raw["end"],
        "start_uid": start_m["uid"],
        "end_uid": end_m["uid"],
        "weak_location": bool(start_m["weak"] or end_m["weak"]),
        "mbti": ct.get("mbti"),
        "ocean": ocean,
        "drives": drives,
    }


def _top_drives(drives: dict[str, float], n: int = 4) -> dict[str, float]:
    return dict(sorted(drives.items(), key=lambda kv: kv[1], reverse=True)[:n])


def _templated_desc(ev: dict) -> tuple[str, str]:
    return (
        f"{ev['role']} 趁空档从{ev['start_name']}前往{ev['end_name']}，约{ev['duration_minutes']}分钟。",
        f"{ev['role']} takes a ~{ev['duration_minutes']}-min trip from {ev['start_name']} to {ev['end_name']}.",
    )


# ---------------------------------------------------------------------------
# LLM description bake
# ---------------------------------------------------------------------------

async def bake_descriptions(events: list[dict], concurrency: int = 5) -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from app.llm.adapter import build_llm_adapter

    adapter = build_llm_adapter()
    sem = asyncio.Semaphore(concurrency)
    n_llm = 0

    async def one(ev: dict) -> None:
        nonlocal n_llm
        async with sem:
            payload = {
                "role": ev["role"],
                "start_name": ev["start_name"],
                "end_name": ev["end_name"],
                "duration_minutes": ev["duration_minutes"],
                "tags": ev["tags"],
                "drives": _top_drives(ev["drives"]),
            }
            try:
                d = await adapter.describe_insert_event(payload)
                ev["description_zh"] = d.get("description_zh", "").strip()
                ev["description_en"] = d.get("description_en", "").strip()
                if ev["description_zh"]:
                    n_llm += 1
                else:
                    ev["description_zh"], ev["description_en"] = _templated_desc(ev)
            except Exception as exc:
                print(f"  !! {ev['id']} describe failed ({exc}); using template", file=sys.stderr)
                ev["description_zh"], ev["description_en"] = _templated_desc(ev)

    await asyncio.gather(*(one(e) for e in events))
    return n_llm


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true", help="skip LLM, use templated descriptions")
    ap.add_argument("--concurrency", type=int, default=5)
    args = ap.parse_args()

    if not RAW_PATH.exists():
        print(f"!! raw events JSON missing: {RAW_PATH}", file=sys.stderr)
        return 1

    scene_tags = load_scene_tags()
    raw = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    events = [build_event(e, scene_tags) for e in raw.get("events", [])]

    if args.no_llm:
        for ev in events:
            ev["description_zh"], ev["description_en"] = _templated_desc(ev)
        n_llm = 0
    else:
        n_llm = asyncio.run(bake_descriptions(events, concurrency=args.concurrency))

    unresolved = [e["id"] for e in events if not (e["start_uid"] and e["end_uid"])]
    weak = [e["id"] for e in events if e["weak_location"]]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "meta": {
            "source": RAW_PATH.name,
            "count": len(events),
            "slot_minutes": SLOT_MINUTES,
            "descriptions_from_llm": n_llm,
            "location_map": {k: v["uid"] for k, v in LOCATION_MAP.items()},
            "role_to_archetypes": ROLE_TO_ARCHETYPES,
            "tag_sources": "destination room scene tags + dominant drives (>=0.6)",
            "scoring": "0.6*cosine(OCEAN5) + 0.3*cosine(drive_proxy) + 0.1*mbti_bonus; role-gated.",
            "drive_proxy_doc": {
                "stress": "neuroticism",
                "curiosity": "openness",
                "procrastination": "1 - conscientiousness",
                "budget": "0.5 (placeholder; use sim money later)",
                "loneliness": "1 - extraversion",
                "weather_sensitivity": "0.25 + 0.5*neuroticism",
                "health_awareness": "conscientiousness",
                "club_engagement": "0.8 if fav_tags has social/leisure else extraversion",
                "research_interest": "1.0 if grad/faculty else 0.4",
                "romantic_interest": "0.5 (placeholder)",
            },
        },
        "events": events,
    }
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {len(events)} events -> {OUT_PATH.relative_to(ROOT)}")
    print(f"descriptions from LLM: {n_llm} (rest templated)")
    print(f"weak-location events: {len(weak)} ({weak[:5]}...)")
    print(f"unresolved events: {len(unresolved)}")
    if events:
        s = events[0]
        print(f"sample {s['id']}: tags={s['tags']} | {s['description_zh']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
