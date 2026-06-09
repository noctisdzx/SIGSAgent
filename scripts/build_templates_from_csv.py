"""Build every NPC's weekly schedule template from the real per-NPC CSV
timetables in `persontimetable/`.

This REPLACES the archetype-skeleton generator (`regenerate_schedules.py`)
as the source of `data/schedule_templates/<npc_id>.json`: instead of a few
hardcoded anchors, each template is derived from the NPC's actual course
timetable (7 days x 48 half-hour cells).

Pipeline
--------
1. Read `<npc>_timetable.csv`. Row 0 carries the major name + time axis;
   rows for 周一..周日 carry one activity string per half-hour cell.
2. Normalise each cell to (activity, location_uid, narrative_zh) via the
   ACTIVITY tables below. Any cell that is NOT a known "life activity" is
   treated as a course -> `attend_class` (the course name is kept as the
   narrative). Empty cells stay EMPTY so the runtime `slot_filler` can fill
   them with fragments.
3. Merge contiguous cells sharing (activity, location_uid) into one block.
4. Lock the pre-dawn hours as `sleep` (so fragments never fire at 03:00).
5. Attach a GOAP `target_state` (restricted key set) and write JSON.

Run from repo root:
    python scripts/build_templates_from_csv.py
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
CSV_DIR = ROOT / "persontimetable" / "persontimetable"
PERSONAS_DIR = ROOT / "data" / "personas"
TEMPLATES_DIR = ROOT / "data" / "schedule_templates"
SCENES_PATH = ROOT / "data" / "scenes" / "guoyi_rooms_v2.json"


# ---------------------------------------------------------------------------
# Canonical room UIDs (from data/scenes/guoyi_rooms_v2.json).
# ---------------------------------------------------------------------------

DORM = "438038e3"
DINING = "9a49343c"
HALAL = "6943e822"
KITCHEN = "a7934434"
CLASSROOM = "4d7a7e81"
LAB = "3877431b"
LECTURE = "cb0199d8"
LIBRARY = "64a9bc35"
DISCUSSION_LAB = "99883bc6"
DISCUSSION_DORM = "da2afe02"
CAFE_LIB = "4ef146d8"
CAFE_DOWN = "a62839dd"
GARDEN_LOW = "66cb10e7"
GARDEN_ROOF = "7a281fd7"
CLUB = "8dc3960a"

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

DAY_TOKENS = {
    "monday": "周一",
    "tuesday": "周二",
    "wednesday": "周三",
    "thursday": "周四",
    "friday": "周五",
    "saturday": "周六",
    "sunday": "周日",
}

SLOT_MINUTES = 30  # CSV half-hour grid


# ---------------------------------------------------------------------------
# Activity normalisation. Keyed by the Chinese portion of the cell (the text
# before " / ", with any "（第X节 PX）" suffix removed). Anything NOT found
# here is assumed to be a course -> attend_class.
# ---------------------------------------------------------------------------

SPECIAL: dict[str, tuple[str, str]] = {
    # sleep / meals
    "睡眠": ("sleep", DORM),
    "午饭": ("have_lunch", DINING),
    "晚饭": ("have_dinner", DINING),
    # lectures / talks
    "学术讲座": ("attend_lecture", LECTURE),
    "职业讲座": ("attend_lecture", LECTURE),
    # lab / studio / hands-on
    "实验室做实验": ("lab_work", LAB),
    "实验课": ("lab_work", LAB),
    "心理实验": ("lab_work", LAB),
    "结构实验": ("lab_work", LAB),
    "电气实验": ("lab_work", LAB),
    "机房编程": ("lab_work", LAB),
    "工作室画图": ("lab_work", LAB),
    "模型制作": ("lab_work", LAB),
    "作品布展": ("lab_work", LAB),
    "通宵赶图": ("lab_work", LAB),
    # self-study
    "图书馆自习": ("self_study", LIBRARY),
    "文献阅读": ("self_study", LIBRARY),
    "空教室刷题": ("self_study", CLASSROOM),
    "课程复盘": ("self_study", LIBRARY),
    "课程预习": ("self_study", LIBRARY),
    "晨间阅读": ("self_study", LIBRARY),
    "报告撰写": ("self_study", LIBRARY),
    "课程项目推进": ("self_study", LIBRARY),
    "作品集工作坊": ("self_study", LIBRARY),
    "宿舍写作业": ("self_study", DORM),
    # discussion / advising
    "小组讨论": ("group_discussion", DISCUSSION_LAB),
    "案例讨论": ("group_discussion", DISCUSSION_LAB),
    "案例研讨": ("group_discussion", DISCUSSION_LAB),
    "设计评图": ("group_discussion", DISCUSSION_LAB),
    "模拟法庭": ("group_discussion", DISCUSSION_LAB),
    "导师谈话": ("group_discussion", DISCUSSION_LAB),
    # clubs / arts practice
    "社团活动": ("club_activity", CLUB),
    "社团例会": ("club_activity", CLUB),
    "舞蹈训练": ("club_activity", CLUB),
    "乐队训练": ("club_activity", CLUB),
    "合唱排练": ("club_activity", CLUB),
    "排练节目": ("club_activity", CLUB),
    "设计素描": ("club_activity", CLUB),
    # walk / outdoor / fitness
    "户外写生": ("walk", GARDEN_LOW),
    "校园慢走": ("walk", GARDEN_LOW),
    "屋顶花园散步": ("walk", GARDEN_ROOF),
    "操场跑步": ("walk", GARDEN_LOW),
    "篮球训练": ("walk", GARDEN_LOW),
    "羽毛球活动": ("walk", GARDEN_LOW),
    "校园摄影": ("walk", GARDEN_LOW),
    # dorm life / chores / errands / leisure
    "宿舍娱乐": ("free_time", DORM),
    "洗衣整理": ("chores", DORM),
    "宿舍打扫": ("chores", DORM),
    "快递取件": ("errand", CAFE_DOWN),
    "超市采购": ("errand", CAFE_DOWN),
    "展览参观": ("leisure", CAFE_DOWN),
    "心理咨询": ("counseling", DISCUSSION_DORM),
}

_PAREN = re.compile(r"（.*?）")


def normalise_cell(cell: str) -> tuple[str, str, str]:
    """Return (activity, location_uid, narrative_zh) for a non-empty cell."""
    base = _PAREN.sub("", cell).strip()
    zh = base.split(" / ")[0].strip()
    if zh in SPECIAL:
        act, loc = SPECIAL[zh]
        return act, loc, zh
    # Unknown -> a course; keep the course name as narrative.
    return "attend_class", CLASSROOM, zh


# ---------------------------------------------------------------------------
# target_state auto-derivation (extended for the new life-activity labels).
# ---------------------------------------------------------------------------

def infer_target_state(activity: str, loc_uid: str) -> dict:
    a = activity.lower()
    if "sleep" in a:
        return {"agent.location_uid": loc_uid, "agent.energy": ">=3"}
    # Outdoor / fitness / walking -> mood boost.
    if any(k in a for k in ("walk", "jog", "exercise", "patrol", "fitness")):
        return {"agent.location_uid": loc_uid, "agent.mood": ">=2"}
    # Social / club / counseling -> mood boost.
    if any(k in a for k in ("club", "social", "chat", "counsel")):
        return {"agent.location_uid": loc_uid, "agent.mood": ">=2"}
    # Light leisure / free time -> slight mood boost.
    if any(k in a for k in ("free_time", "leisure", "media", "rest")):
        return {"agent.location_uid": loc_uid, "agent.mood": ">=1"}
    # chores / errand / study / class / meals -> just be at the right place.
    return {"agent.location_uid": loc_uid}


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def _hhmm(minutes: int) -> str:
    minutes = min(minutes, 23 * 60 + 59)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


# ---------------------------------------------------------------------------
# Build one day's blocks from its 48-cell row.
# ---------------------------------------------------------------------------

def build_day(cells: list[str], halal: bool) -> list[dict]:
    """`cells` are the 48 half-hour activity strings for one weekday."""
    # Step 1: normalise each cell (None for empty).
    norm: list[tuple[str, str, str] | None] = []
    for c in cells:
        c = (c or "").strip()
        if not c:
            norm.append(None)
            continue
        act, loc, narr = normalise_cell(c)
        if halal and loc == DINING:
            loc = HALAL
        norm.append((act, loc, narr))

    # Step 2: merge contiguous cells sharing (activity, location).
    blocks: list[dict] = []
    i = 0
    n = len(norm)
    while i < n:
        if norm[i] is None:
            i += 1
            continue
        act, loc, narr = norm[i]
        j = i
        while j + 1 < n and norm[j + 1] is not None and norm[j + 1][:2] == (act, loc):
            j += 1
        start = _hhmm(i * SLOT_MINUTES)
        end = _hhmm((j + 1) * SLOT_MINUTES)
        blocks.append({
            "start": start,
            "end": end,
            "activity": act,
            "location_uid": loc,
            "narrative_zh": narr,
            "target_state": infer_target_state(act, loc),
        })
        i = j + 1

    # Step 3: lock the pre-dawn hours as sleep so the slot_filler does not
    # fire fragments at 03:00.
    if blocks and blocks[0]["start"] > "00:00":
        if blocks[0]["activity"] == "sleep":
            blocks[0]["start"] = "00:00"
        else:
            blocks.insert(0, {
                "start": "00:00",
                "end": blocks[0]["start"],
                "activity": "sleep",
                "location_uid": DORM,
                "narrative_zh": "凌晨睡眠",
                "target_state": infer_target_state("sleep", DORM),
            })
    return blocks


# ---------------------------------------------------------------------------
# Parse one CSV into {weekday -> [blocks]} plus the major label.
# ---------------------------------------------------------------------------

def parse_csv(path: Path, halal: bool) -> tuple[str, dict[str, list[dict]]]:
    rows = list(csv.reader(path.open(encoding="utf-8-sig")))
    major = (rows[0][0].strip() if rows and rows[0] else "") or ""

    # Find each weekday row by matching its day token in column 1.
    week: dict[str, list[dict]] = {}
    for day_key, token in DAY_TOKENS.items():
        day_row = None
        for r in rows[1:]:
            if len(r) > 1 and token in r[1]:
                day_row = r
                break
        cells = day_row[2:50] if day_row else []
        # Pad to 48 cells.
        cells = (cells + [""] * 48)[:48]
        week[day_key] = build_day(cells, halal)
    return major, week


# ---------------------------------------------------------------------------
# Validation (mirrors regenerate_schedules.validate)
# ---------------------------------------------------------------------------

VALID_TARGET_KEYS = {
    "agent.location_uid", "agent.energy", "agent.mood", "agent.retry_count",
}


def validate(week: dict[str, list[dict]], valid_uids: set[str]) -> list[str]:
    errs: list[str] = []
    for d in WEEKDAYS:
        blocks = week.get(d)
        if blocks is None:
            errs.append(f"missing weekday {d}")
            continue
        if not blocks:
            errs.append(f"{d}: empty block list")
            continue
        prev_end = "00:00"
        for i, b in enumerate(blocks):
            for k in ("start", "end", "activity", "location_uid", "target_state"):
                if k not in b:
                    errs.append(f"{d}[{i}]: missing {k}")
            if b.get("location_uid") not in valid_uids:
                errs.append(f"{d}[{i}]: bad uid {b.get('location_uid')!r}")
            if b["start"] < prev_end:
                errs.append(f"{d}[{i}]: overlap (start {b['start']} < prev_end {prev_end})")
            if b["end"] <= b["start"]:
                errs.append(f"{d}[{i}]: non-positive duration {b['start']}-{b['end']}")
            prev_end = b["end"]
            for tk in (b.get("target_state") or {}):
                if not (tk in VALID_TARGET_KEYS or tk.startswith("agent.knows.")):
                    errs.append(f"{d}[{i}]: bad target_state key {tk!r}")
    return errs


# ---------------------------------------------------------------------------
# Persona lookup (npc id + halal flag)
# ---------------------------------------------------------------------------

def load_persona(npc_id: str) -> dict:
    pf = PERSONAS_DIR / f"{npc_id}.json"
    if pf.exists():
        return json.loads(pf.read_text(encoding="utf-8"))
    return {}


def is_halal(persona: dict) -> bool:
    blob = json.dumps(persona, ensure_ascii=False)
    return any(k in blob for k in ("halal", "Halal", "清真", "穆斯林"))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    if not CSV_DIR.exists():
        print(f"!! CSV dir missing: {CSV_DIR}", file=sys.stderr)
        return 1
    if not SCENES_PATH.exists():
        print(f"!! Scenes JSON missing: {SCENES_PATH}", file=sys.stderr)
        return 1

    scenes = json.loads(SCENES_PATH.read_text(encoding="utf-8"))
    valid_uids = {r["uid"] for r in scenes.get("rooms", [])}
    print(f"valid room uids: {len(valid_uids)}")

    csv_files = sorted(CSV_DIR.glob("*_timetable.csv"))
    print(f"csv files: {len(csv_files)}")

    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

    n_written = 0
    total_blocks = 0
    errors_total = 0

    for cf in csv_files:
        npc_id = cf.name.replace("_timetable.csv", "")
        persona = load_persona(npc_id)
        halal = is_halal(persona)

        major, week = parse_csv(cf, halal)
        errs = validate(week, valid_uids)
        if errs:
            errors_total += len(errs)
            print(f"  !! {npc_id}: {len(errs)} errors: {errs[:3]}", file=sys.stderr)

        name = persona.get("name", npc_id)
        tmpl = {
            "id": npc_id,
            "description": f"{name} 的周课表（专业={major}，由真实课表 CSV 生成、含 target_state；空档交给 slot_filler）。",
            "archetype": "from_csv",
            "major": major,
            "week": week,
        }
        out_path = TEMPLATES_DIR / f"{npc_id}.json"
        out_path.write_text(
            json.dumps(tmpl, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        n_written += 1
        total_blocks += sum(len(week[d]) for d in WEEKDAYS)

    print()
    print(f"wrote {n_written} template files")
    print(f"total blocks: {total_blocks}")
    print(f"validation errors: {errors_total}")
    return 0 if errors_total == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
