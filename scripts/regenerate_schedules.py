"""Regenerate every NPC's weekly schedule template.

- Every weekday (Mon..Sun) is distinct (no Mon=Tue=...).
- Every block carries a `target_state` field used by the GOAP planner as A* goal.
- Action set is FROZEN (move/interact/talk/phone_call/find/idle); target_state
  keys are restricted to: agent.location_uid / agent.energy / agent.mood /
  agent.retry_count / agent.knows.*  with optional comparator string values
  like ">=3".

Run from repo root:
    python scripts/regenerate_schedules.py
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
PERSONAS_DIR = ROOT / "data" / "personas"
TEMPLATES_DIR = ROOT / "data" / "schedule_templates"
SCENES_PATH = ROOT / "data" / "scenes" / "guoyi_rooms_v2.json"


# ---------------------------------------------------------------------------
# Canonical room UIDs (from data/scenes/guoyi_rooms_v2.json). Anything outside
# this set is invalid.
# ---------------------------------------------------------------------------

DORM = "438038e3"
DINING = "9a49343c"
HALAL = "6943e822"
KITCHEN = "a7934434"
CLASSROOM = "4d7a7e81"
LAB = "3877431b"
LECTURE = "cb0199d8"
LIBRARY = "64a9bc35"
DISCUSSION_LAB = "99883bc6"       # Discussion Area (lab floor)
DISCUSSION_DORM = "da2afe02"      # Discussion Area (dorm floor; isolated)
DISCUSSION_LIB = "9a4098e7"       # Discussion Area (library floor; isolated)
CAFE_LIB = "4ef146d8"
CAFE_DOWN = "a62839dd"
GARDEN_LOW = "66cb10e7"
GARDEN_ROOF = "7a281fd7"
CLUB = "8dc3960a"

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


# ---------------------------------------------------------------------------
# Archetype classification
# ---------------------------------------------------------------------------

def classify(persona: dict) -> str:
    """Return one of: undergrad / grad / faculty / logistics / other."""
    profile = persona.get("profile", {})
    role_zh = (profile.get("role_zh") or "") + (profile.get("role_en") or "")
    role = persona.get("role", "")
    text = role_zh + " " + role

    # Order matters: faculty/logistics keywords first to avoid undergrad fallthrough.
    if any(k in text for k in ("教授", "讲师", "辅导员", "导师", "医生", "Professor", "Faculty")):
        return "faculty"
    if any(k in text for k in ("保卫", "食堂", "图书馆管理员", "保洁", "宿管", "守门人", "处长", "主厨", "Security", "Logistics")):
        return "logistics"
    if any(k in text for k in ("博一", "博二", "博三", "博四", "博士", "Doctor", "PhD")) \
       or any(k in text for k in ("研一", "研二", "研三", "research", "Research")) \
       or any(k in role_zh for k in ("研一·", "研二·", "研三·")):
        return "grad"
    if any(k in text for k in ("大一", "大二", "大三", "大四", "undergrad", "Yr1", "Yr2", "Yr3", "Yr4")):
        return "undergrad"
    return "other"


# ---------------------------------------------------------------------------
# target_state auto-derivation
# ---------------------------------------------------------------------------

def infer_target_state(activity: str, loc_uid: str) -> dict:
    """Pick the smallest goal capturing the activity's intent.

    Only uses state keys reachable by the 6 frozen actions.
    """
    a = activity.lower()
    # Sleep: must be at dorm AND energy fully recovered.
    if "sleep" in a:
        return {"agent.location_uid": loc_uid, "agent.energy": ">=3"}
    # Phys / outdoor / mood-up activities.
    if any(k in a for k in ("jog", "walk", "exercise", "patrol", "fitness")):
        return {"agent.location_uid": loc_uid, "agent.mood": ">=2"}
    # Social activities.
    if any(k in a for k in ("social", "chat", "hangout", "dating", "club")):
        return {"agent.location_uid": loc_uid, "agent.mood": ">=2"}
    # Phone-call-shaped activity (rare in templates; reachable via retry_count).
    if "phone_call" in a:
        return {"agent.retry_count": ">=1"}
    # Leisure / free time / media: slight mood boost.
    if any(k in a for k in ("free_time", "leisure", "media", "rest_break")):
        return {"agent.location_uid": loc_uid, "agent.mood": ">=1"}
    # Default: just be at the right place.
    return {"agent.location_uid": loc_uid}


# ---------------------------------------------------------------------------
# Archetype skeletons (filled in by subsequent script-edit steps).
# Each value: dict[weekday -> list of (start, end, activity, loc_uid, narrative_zh)].
# ---------------------------------------------------------------------------

SKELETONS: dict[str, dict[str, list[tuple[str, str, str, str, str]]]] = {
    "undergrad": {
        "monday": [
            ("07:00", "07:30", "wake_up", DORM, "起床洗漱"),
            ("07:30", "08:00", "have_breakfast", DINING, "食堂早饭"),
            ("08:00", "10:00", "attend_class", CLASSROOM, "周一早课·必修"),
            ("10:00", "10:30", "coffee_break", CAFE_LIB, "课间补咖啡"),
            ("10:30", "12:00", "self_study", LIBRARY, "图书馆继续作业"),
            ("12:00", "13:00", "have_lunch", DINING, "和同学一起午饭"),
            ("13:00", "14:00", "midday_rest", DORM, "宿舍小憩"),
            ("14:00", "16:00", "attend_lecture", LECTURE, "周一下午公选课"),
            ("16:00", "17:30", "self_study", LIBRARY, "图书馆做题"),
            ("17:30", "18:30", "have_dinner", DINING, "食堂晚饭"),
            ("18:30", "20:00", "free_time", DORM, "宿舍打游戏放松"),
            ("20:00", "22:00", "self_study", LIBRARY, "晚自习"),
            ("22:30", "23:30", "leisure_media", DORM, "刷手机看剧"),
            ("23:30", "23:59", "sleep", DORM, "准备入睡"),
        ],
        "tuesday": [
            ("07:30", "08:00", "wake_up", DORM, "起床洗漱"),
            ("08:00", "08:30", "have_breakfast", DINING, "食堂早饭"),
            ("09:00", "12:00", "lab_work", LAB, "周二上午实验课"),
            ("12:00", "12:45", "have_lunch", DINING, "实验后赶饭"),
            ("12:45", "14:00", "midday_rest", DORM, "宿舍午休"),
            ("14:00", "16:30", "lab_work", LAB, "继续做实验·写报告"),
            ("16:30", "18:00", "jog_or_walk", GARDEN_ROOF, "操场跑步放松"),
            ("18:00", "19:00", "have_dinner", DINING, "晚饭"),
            ("19:00", "21:00", "club_activity", CLUB, "周二社团例会"),
            ("21:00", "22:30", "free_time", DORM, "回宿舍洗澡看视频"),
            ("23:00", "23:59", "sleep", DORM, "睡觉"),
        ],
        "wednesday": [
            ("07:00", "07:30", "wake_up", DORM, "起床洗漱"),
            ("07:30", "08:00", "have_breakfast", DINING, "早饭"),
            ("08:00", "09:30", "attend_class", CLASSROOM, "周三早课"),
            ("09:30", "11:30", "self_study", LIBRARY, "图书馆复习"),
            ("11:30", "12:00", "coffee_break", CAFE_LIB, "图书馆里咖啡"),
            ("12:00", "12:45", "have_lunch", DINING, "午饭"),
            ("12:45", "13:45", "midday_rest", DORM, "短暂午休"),
            ("14:00", "16:00", "group_discussion", DISCUSSION_LAB, "小组讨论项目"),
            ("16:00", "17:30", "read_for_fun", CAFE_LIB, "咖啡厅闲读"),
            ("17:30", "18:30", "have_dinner", DINING, "晚饭"),
            ("19:00", "21:30", "self_study", LIBRARY, "图书馆自习"),
            ("21:30", "23:00", "social_chat", CAFE_DOWN, "和朋友聊天"),
            ("23:30", "23:59", "sleep", DORM, "睡觉"),
        ],
        "thursday": [
            ("07:30", "08:00", "wake_up", DORM, "起床"),
            ("08:00", "08:30", "have_breakfast", DINING, "早饭"),
            ("08:30", "11:30", "attend_lecture", LECTURE, "周四上午选修课"),
            ("11:30", "12:30", "have_lunch", DINING, "午饭"),
            ("12:30", "13:30", "midday_rest", DORM, "宿舍午休"),
            ("13:30", "16:00", "self_study", LIBRARY, "图书馆任务清单"),
            ("16:00", "17:30", "exercise", GARDEN_ROOF, "操场撸铁/跑步"),
            ("17:30", "18:30", "have_dinner", DINING, "晚饭"),
            ("18:30", "21:00", "club_activity", CLUB, "社团排练"),
            ("21:00", "22:30", "free_time", DORM, "宿舍刷剧"),
            ("23:00", "23:59", "sleep", DORM, "睡觉"),
        ],
        "friday": [
            ("07:00", "07:30", "wake_up", DORM, "起床洗漱"),
            ("07:30", "08:00", "have_breakfast", DINING, "早饭"),
            ("08:00", "10:00", "attend_class", CLASSROOM, "周五早课"),
            ("10:00", "12:00", "self_study", LIBRARY, "图书馆收尾本周作业"),
            ("12:00", "13:00", "have_lunch", DINING, "午饭"),
            ("13:00", "14:00", "midday_rest", DORM, "宿舍午休"),
            ("14:00", "16:00", "attend_class", CLASSROOM, "周五下午课"),
            ("16:00", "17:30", "coffee_break", CAFE_LIB, "周五下午茶"),
            ("18:00", "20:00", "social_chat", DINING, "周五聚餐"),
            ("20:00", "22:30", "free_time", CLUB, "夜场社团活动"),
            ("23:00", "23:59", "sleep", DORM, "睡觉"),
        ],
        "saturday": [
            ("09:00", "09:30", "wake_up", DORM, "周末晚起"),
            ("09:30", "10:30", "have_breakfast", CAFE_LIB, "咖啡厅早午餐"),
            ("10:30", "12:00", "read_for_fun", CAFE_LIB, "看课外书"),
            ("12:00", "13:00", "have_lunch", DINING, "午饭"),
            ("13:00", "15:00", "midday_rest", DORM, "宿舍午睡"),
            ("15:00", "17:30", "social_chat", CAFE_DOWN, "和朋友约咖啡"),
            ("17:30", "19:00", "have_dinner", DINING, "晚饭"),
            ("19:00", "22:00", "free_time", CLUB, "周末娱乐"),
            ("22:00", "23:00", "leisure_media", DORM, "回宿舍刷剧"),
            ("23:30", "23:59", "sleep", DORM, "睡觉"),
        ],
        "sunday": [
            ("08:30", "09:00", "wake_up", DORM, "起床"),
            ("09:00", "09:30", "have_breakfast", DINING, "早饭"),
            ("09:30", "12:00", "self_study", LIBRARY, "补一周作业"),
            ("12:00", "12:45", "have_lunch", DINING, "午饭"),
            ("12:45", "14:00", "midday_rest", DORM, "午休"),
            ("14:00", "16:30", "self_study", LIBRARY, "继续作业"),
            ("16:30", "17:30", "jog_or_walk", GARDEN_ROOF, "操场散步"),
            ("17:30", "18:30", "have_dinner", DINING, "晚饭"),
            ("18:30", "21:00", "free_time", DORM, "宿舍整理 + 准备下周"),
            ("22:00", "23:00", "leisure_media", DORM, "看会儿剧"),
            ("23:00", "23:59", "sleep", DORM, "早睡"),
        ],
    },
    "grad": {
        "monday": [
            ("08:00", "08:30", "wake_up", DORM, "起床"),
            ("08:30", "09:00", "have_breakfast", DINING, "早饭"),
            ("09:00", "12:00", "lab_work", LAB, "实验室·读 paper"),
            ("12:00", "12:45", "have_lunch", DINING, "午饭"),
            ("12:45", "13:30", "midday_rest", DORM, "宿舍短午休"),
            ("13:30", "17:30", "lab_work", LAB, "下午实验/写代码"),
            ("17:30", "18:30", "have_dinner", DINING, "晚饭"),
            ("19:00", "21:30", "lab_work", LAB, "晚间继续实验"),
            ("21:30", "22:30", "free_time", DORM, "宿舍刷剧"),
            ("23:00", "23:59", "sleep", DORM, "睡觉"),
        ],
        "tuesday": [
            ("08:00", "08:30", "wake_up", DORM, "起床"),
            ("08:30", "09:00", "have_breakfast", DINING, "早饭"),
            ("09:00", "11:00", "group_discussion", DISCUSSION_LAB, "周二组会"),
            ("11:00", "12:00", "lab_work", LAB, "整理组会反馈"),
            ("12:00", "13:00", "have_lunch", DINING, "午饭"),
            ("13:00", "14:00", "midday_rest", DORM, "午休"),
            ("14:00", "17:30", "lab_work", LAB, "实验"),
            ("17:30", "18:30", "have_dinner", DINING, "晚饭"),
            ("19:00", "21:00", "self_study", LIBRARY, "看相关文献"),
            ("21:00", "22:30", "coffee_break", CAFE_LIB, "图书馆咖啡"),
            ("23:00", "23:59", "sleep", DORM, "睡觉"),
        ],
        "wednesday": [
            ("08:30", "09:00", "wake_up", DORM, "起床"),
            ("09:00", "09:30", "have_breakfast", DINING, "早饭"),
            ("09:30", "12:00", "lab_work", LAB, "做实验"),
            ("12:00", "13:00", "have_lunch", DINING, "午饭"),
            ("13:00", "13:45", "midday_rest", DORM, "短午休"),
            ("14:00", "16:00", "attend_lecture", LECTURE, "周三专题课"),
            ("16:00", "17:30", "lab_work", LAB, "继续实验"),
            ("17:30", "18:30", "have_dinner", DINING, "晚饭"),
            ("19:00", "21:30", "lab_work", LAB, "推进 paper"),
            ("21:30", "22:30", "social_chat", DISCUSSION_LAB, "和师弟师妹聊"),
            ("23:00", "23:59", "sleep", DORM, "睡觉"),
        ],
        "thursday": [
            ("08:00", "08:30", "wake_up", DORM, "起床"),
            ("08:30", "09:00", "have_breakfast", DINING, "早饭"),
            ("09:00", "12:00", "lab_work", LAB, "上午实验"),
            ("12:00", "13:00", "have_lunch", DINING, "午饭"),
            ("13:00", "14:00", "midday_rest", DORM, "午休"),
            ("14:00", "17:00", "group_discussion", DISCUSSION_LAB, "课题讨论"),
            ("17:00", "18:00", "exercise", GARDEN_ROOF, "操场快走"),
            ("18:00", "19:00", "have_dinner", DINING, "晚饭"),
            ("19:00", "22:00", "lab_work", LAB, "夜间实验"),
            ("23:00", "23:59", "sleep", DORM, "睡觉"),
        ],
        "friday": [
            ("08:30", "09:00", "wake_up", DORM, "起床"),
            ("09:00", "09:30", "have_breakfast", DINING, "早饭"),
            ("09:30", "12:00", "lab_work", LAB, "周五早实验"),
            ("12:00", "13:00", "have_lunch", DINING, "午饭"),
            ("13:00", "14:00", "midday_rest", DORM, "午休"),
            ("14:00", "17:00", "lab_work", LAB, "周五尾声"),
            ("17:00", "18:30", "have_dinner", DINING, "和组内同学聚餐"),
            ("18:30", "21:00", "free_time", CLUB, "周末前放松"),
            ("21:30", "22:30", "leisure_media", DORM, "宿舍刷剧"),
            ("23:00", "23:59", "sleep", DORM, "睡觉"),
        ],
        "saturday": [
            ("09:30", "10:00", "wake_up", DORM, "周六晚起"),
            ("10:00", "10:30", "have_breakfast", CAFE_LIB, "咖啡厅早午餐"),
            ("10:30", "12:00", "read_for_fun", CAFE_LIB, "看课外书"),
            ("12:00", "13:00", "have_lunch", DINING, "午饭"),
            ("13:00", "14:30", "midday_rest", DORM, "宿舍午睡"),
            ("14:30", "17:30", "lab_work", LAB, "推 paper（自愿）"),
            ("17:30", "18:30", "have_dinner", DINING, "晚饭"),
            ("18:30", "20:30", "social_chat", CAFE_DOWN, "和老友咖啡"),
            ("20:30", "22:30", "leisure_media", DORM, "宿舍看剧"),
            ("23:30", "23:59", "sleep", DORM, "睡觉"),
        ],
        "sunday": [
            ("09:00", "09:30", "wake_up", DORM, "起床"),
            ("09:30", "10:00", "have_breakfast", DINING, "早饭"),
            ("10:00", "12:00", "self_study", LIBRARY, "整理本周笔记"),
            ("12:00", "13:00", "have_lunch", DINING, "午饭"),
            ("13:00", "14:30", "midday_rest", DORM, "午休"),
            ("14:30", "17:00", "lab_work", LAB, "准备下周组会"),
            ("17:00", "18:00", "jog_or_walk", GARDEN_ROOF, "操场散步"),
            ("18:00", "19:00", "have_dinner", DINING, "晚饭"),
            ("19:00", "21:00", "free_time", DORM, "宿舍整理"),
            ("22:30", "23:30", "leisure_media", DORM, "看剧"),
            ("23:30", "23:59", "sleep", DORM, "睡觉"),
        ],
    },
    "faculty": {
        "monday": [
            ("07:00", "07:30", "wake_up", DORM, "起床"),
            ("07:30", "08:00", "have_breakfast", DINING, "早饭"),
            ("08:00", "10:00", "give_lecture", LECTURE, "周一早课·讲座"),
            ("10:00", "11:00", "office_hours", DISCUSSION_LAB, "答疑"),
            ("11:00", "12:00", "read_for_fun", LIBRARY, "看 paper"),
            ("12:00", "13:00", "have_lunch", DINING, "午饭"),
            ("13:00", "14:00", "midday_rest", DORM, "午休"),
            ("14:00", "16:00", "give_lecture", CLASSROOM, "下午专业课"),
            ("16:00", "17:30", "lab_work", LAB, "指导实验"),
            ("17:30", "18:30", "have_dinner", DINING, "晚饭"),
            ("19:00", "21:00", "self_study", LIBRARY, "准备明天讲义"),
            ("22:30", "23:30", "leisure_media", DORM, "看书"),
            ("23:30", "23:59", "sleep", DORM, "睡觉"),
        ],
        "tuesday": [
            ("07:00", "07:30", "wake_up", DORM, "起床"),
            ("07:30", "08:00", "have_breakfast", DINING, "早饭"),
            ("08:30", "10:30", "group_discussion", DISCUSSION_LAB, "组会"),
            ("10:30", "12:00", "office_hours", DISCUSSION_LAB, "学生 1v1"),
            ("12:00", "13:00", "have_lunch", DINING, "午饭"),
            ("13:00", "14:00", "midday_rest", DORM, "午休"),
            ("14:00", "16:30", "give_lecture", LECTURE, "周二专题讲座"),
            ("16:30", "17:30", "exercise", GARDEN_ROOF, "操场快走"),
            ("17:30", "18:30", "have_dinner", DINING, "晚饭"),
            ("19:00", "21:30", "self_study", LIBRARY, "审稿/写 paper"),
            ("23:00", "23:59", "sleep", DORM, "睡觉"),
        ],
        "wednesday": [
            ("07:30", "08:00", "wake_up", DORM, "起床"),
            ("08:00", "08:30", "have_breakfast", DINING, "早饭"),
            ("08:30", "11:30", "give_lecture", CLASSROOM, "周三整上午课"),
            ("11:30", "12:30", "have_lunch", DINING, "午饭"),
            ("12:30", "13:30", "midday_rest", DORM, "午休"),
            ("13:30", "16:00", "office_hours", DISCUSSION_LAB, "下午答疑"),
            ("16:00", "17:30", "coffee_break", CAFE_LIB, "图书馆咖啡 + 思考"),
            ("17:30", "18:30", "have_dinner", DINING, "晚饭"),
            ("19:00", "21:00", "lab_work", LAB, "指导研究生"),
            ("22:00", "23:00", "leisure_media", DORM, "看书"),
            ("23:30", "23:59", "sleep", DORM, "睡觉"),
        ],
        "thursday": [
            ("07:00", "07:30", "wake_up", DORM, "起床"),
            ("07:30", "08:00", "have_breakfast", DINING, "早饭"),
            ("08:00", "10:00", "give_lecture", LECTURE, "周四早课"),
            ("10:00", "12:00", "self_study", LIBRARY, "图书馆改 paper"),
            ("12:00", "13:00", "have_lunch", DINING, "午饭"),
            ("13:00", "14:00", "midday_rest", DORM, "午休"),
            ("14:00", "16:00", "group_discussion", DISCUSSION_LAB, "项目会议"),
            ("16:00", "17:30", "office_hours", DISCUSSION_LAB, "学生答疑"),
            ("17:30", "18:30", "have_dinner", DINING, "晚饭"),
            ("19:00", "21:00", "self_study", LIBRARY, "审稿"),
            ("23:00", "23:59", "sleep", DORM, "睡觉"),
        ],
        "friday": [
            ("07:00", "07:30", "wake_up", DORM, "起床"),
            ("07:30", "08:00", "have_breakfast", DINING, "早饭"),
            ("08:00", "10:00", "give_lecture", CLASSROOM, "周五早课"),
            ("10:00", "12:00", "office_hours", DISCUSSION_LAB, "周五答疑日"),
            ("12:00", "13:00", "have_lunch", DINING, "午饭"),
            ("13:00", "14:00", "midday_rest", DORM, "午休"),
            ("14:00", "16:30", "group_discussion", DISCUSSION_LAB, "周报会"),
            ("16:30", "18:00", "coffee_break", CAFE_DOWN, "周五咖啡时间"),
            ("18:00", "19:00", "have_dinner", DINING, "晚饭"),
            ("19:00", "21:00", "social_chat", CAFE_DOWN, "和同事聊学术八卦"),
            ("23:00", "23:59", "sleep", DORM, "睡觉"),
        ],
        "saturday": [
            ("08:30", "09:00", "wake_up", DORM, "晚起"),
            ("09:00", "09:30", "have_breakfast", CAFE_LIB, "咖啡厅早午餐"),
            ("09:30", "12:00", "read_for_fun", LIBRARY, "图书馆看专著"),
            ("12:00", "13:00", "have_lunch", DINING, "午饭"),
            ("13:00", "14:30", "midday_rest", DORM, "午休"),
            ("14:30", "17:00", "self_study", LIBRARY, "继续 paper"),
            ("17:00", "18:30", "jog_or_walk", GARDEN_ROOF, "操场散步"),
            ("18:30", "19:30", "have_dinner", DINING, "晚饭"),
            ("19:30", "22:00", "free_time", DORM, "家庭时间"),
            ("23:00", "23:59", "sleep", DORM, "睡觉"),
        ],
        "sunday": [
            ("08:00", "08:30", "wake_up", DORM, "起床"),
            ("08:30", "09:00", "have_breakfast", DINING, "早饭"),
            ("09:00", "12:00", "self_study", LIBRARY, "准备下周讲义"),
            ("12:00", "13:00", "have_lunch", DINING, "午饭"),
            ("13:00", "14:00", "midday_rest", DORM, "午休"),
            ("14:00", "17:00", "self_study", LIBRARY, "审稿/写报告"),
            ("17:00", "18:00", "jog_or_walk", GARDEN_ROOF, "操场快走"),
            ("18:00", "19:00", "have_dinner", DINING, "晚饭"),
            ("19:00", "21:30", "leisure_media", DORM, "看新闻"),
            ("23:00", "23:59", "sleep", DORM, "早睡"),
        ],
    },
    "logistics": {
        "monday": [
            ("06:00", "06:30", "wake_up", DORM, "早起"),
            ("06:30", "07:00", "have_breakfast", DINING, "早饭"),
            ("07:00", "11:00", "patrol", GARDEN_LOW, "上午巡查/值班"),
            ("11:00", "12:30", "have_lunch", KITCHEN, "后厨吃饭"),
            ("12:30", "13:30", "midday_rest", DORM, "午休"),
            ("13:30", "17:30", "patrol", GARDEN_LOW, "下午继续值班"),
            ("17:30", "18:30", "have_dinner", KITCHEN, "晚饭"),
            ("18:30", "21:00", "patrol", GARDEN_LOW, "夜间巡查"),
            ("21:30", "22:30", "leisure_media", DORM, "宿舍看电视"),
            ("23:00", "23:59", "sleep", DORM, "睡觉"),
        ],
        "tuesday": [
            ("06:00", "06:30", "wake_up", DORM, "早起"),
            ("06:30", "07:00", "have_breakfast", DINING, "早饭"),
            ("07:00", "11:30", "patrol", GARDEN_ROOF, "周二屋顶花园检查"),
            ("11:30", "12:30", "have_lunch", KITCHEN, "午饭"),
            ("12:30", "13:30", "midday_rest", DORM, "午休"),
            ("13:30", "17:00", "patrol", DORM, "宿舍楼下午巡查"),
            ("17:00", "18:00", "have_dinner", KITCHEN, "晚饭"),
            ("18:00", "21:30", "patrol", DORM, "夜间宿舍值守"),
            ("22:00", "23:00", "leisure_media", DORM, "看新闻"),
            ("23:00", "23:59", "sleep", DORM, "睡觉"),
        ],
        "wednesday": [
            ("06:00", "06:30", "wake_up", DORM, "早起"),
            ("06:30", "07:00", "have_breakfast", DINING, "早饭"),
            ("07:00", "11:30", "patrol", LIBRARY, "周三图书馆区巡查"),
            ("11:30", "12:30", "have_lunch", KITCHEN, "午饭"),
            ("12:30", "13:30", "midday_rest", DORM, "午休"),
            ("13:30", "17:30", "patrol", LECTURE, "周三下午教学楼"),
            ("17:30", "18:30", "have_dinner", KITCHEN, "晚饭"),
            ("19:00", "21:00", "patrol", CLUB, "晚间社团区巡查"),
            ("22:00", "23:00", "leisure_media", DORM, "宿舍看电视"),
            ("23:30", "23:59", "sleep", DORM, "睡觉"),
        ],
        "thursday": [
            ("06:00", "06:30", "wake_up", DORM, "早起"),
            ("06:30", "07:00", "have_breakfast", DINING, "早饭"),
            ("07:00", "11:00", "patrol", LAB, "周四实验楼检查"),
            ("11:00", "12:00", "have_lunch", KITCHEN, "午饭"),
            ("12:00", "13:00", "midday_rest", DORM, "午休"),
            ("13:00", "17:30", "patrol", LAB, "下午继续"),
            ("17:30", "18:30", "have_dinner", KITCHEN, "晚饭"),
            ("18:30", "21:00", "patrol", GARDEN_LOW, "夜间花园巡查"),
            ("21:00", "22:30", "social_chat", KITCHEN, "和同事聊聊"),
            ("23:00", "23:59", "sleep", DORM, "睡觉"),
        ],
        "friday": [
            ("06:00", "06:30", "wake_up", DORM, "早起"),
            ("06:30", "07:00", "have_breakfast", DINING, "早饭"),
            ("07:00", "11:30", "patrol", CLASSROOM, "周五教学楼"),
            ("11:30", "12:30", "have_lunch", KITCHEN, "午饭"),
            ("12:30", "13:30", "midday_rest", DORM, "午休"),
            ("13:30", "17:30", "patrol", LIBRARY, "下午图书馆"),
            ("17:30", "18:30", "have_dinner", KITCHEN, "晚饭"),
            ("18:30", "22:00", "patrol", CLUB, "周五夜社团区"),
            ("22:30", "23:30", "leisure_media", DORM, "宿舍放松"),
            ("23:30", "23:59", "sleep", DORM, "睡觉"),
        ],
        "saturday": [
            ("07:00", "07:30", "wake_up", DORM, "起床"),
            ("07:30", "08:00", "have_breakfast", DINING, "早饭"),
            ("08:00", "12:00", "patrol", GARDEN_LOW, "周末花园巡查"),
            ("12:00", "13:00", "have_lunch", KITCHEN, "午饭"),
            ("13:00", "14:30", "midday_rest", DORM, "午休"),
            ("14:30", "17:30", "patrol", DORM, "宿舍区周末检查"),
            ("17:30", "18:30", "have_dinner", KITCHEN, "晚饭"),
            ("18:30", "21:00", "social_chat", KITCHEN, "周末同事聚"),
            ("21:00", "22:30", "leisure_media", DORM, "电视"),
            ("23:30", "23:59", "sleep", DORM, "睡觉"),
        ],
        "sunday": [
            ("07:00", "07:30", "wake_up", DORM, "起床"),
            ("07:30", "08:00", "have_breakfast", DINING, "早饭"),
            ("08:00", "11:30", "patrol", GARDEN_ROOF, "周日屋顶巡查"),
            ("11:30", "12:30", "have_lunch", KITCHEN, "午饭"),
            ("12:30", "14:00", "midday_rest", DORM, "长午休"),
            ("14:00", "17:00", "patrol", GARDEN_LOW, "下午低层花园"),
            ("17:00", "18:00", "have_dinner", KITCHEN, "晚饭"),
            ("18:00", "20:30", "free_time", DORM, "宿舍休息"),
            ("21:00", "22:30", "leisure_media", DORM, "电视"),
            ("23:00", "23:59", "sleep", DORM, "早睡"),
        ],
    },
    "other": {
        "monday": [
            ("07:30", "08:00", "wake_up", DORM, "起床"),
            ("08:00", "08:30", "have_breakfast", DINING, "早饭"),
            ("08:30", "11:30", "self_study", LIBRARY, "图书馆做事"),
            ("11:30", "12:30", "have_lunch", DINING, "午饭"),
            ("12:30", "13:30", "midday_rest", DORM, "午休"),
            ("13:30", "17:00", "self_study", LIBRARY, "下午继续"),
            ("17:00", "18:00", "have_dinner", DINING, "晚饭"),
            ("18:30", "21:00", "free_time", CLUB, "活动"),
            ("21:30", "22:30", "leisure_media", DORM, "刷手机"),
            ("23:00", "23:59", "sleep", DORM, "睡觉"),
        ],
        "tuesday": [
            ("07:30", "08:00", "wake_up", DORM, "起床"),
            ("08:00", "08:30", "have_breakfast", DINING, "早饭"),
            ("08:30", "11:30", "self_study", LIBRARY, "图书馆"),
            ("11:30", "12:30", "have_lunch", DINING, "午饭"),
            ("12:30", "13:30", "midday_rest", DORM, "午休"),
            ("14:00", "17:00", "social_chat", CAFE_LIB, "周二咖啡聊天"),
            ("17:00", "18:00", "have_dinner", DINING, "晚饭"),
            ("18:30", "21:00", "free_time", DORM, "宿舍"),
            ("23:00", "23:59", "sleep", DORM, "睡觉"),
        ],
        "wednesday": [
            ("07:30", "08:00", "wake_up", DORM, "起床"),
            ("08:00", "08:30", "have_breakfast", DINING, "早饭"),
            ("08:30", "11:30", "self_study", LIBRARY, "图书馆"),
            ("11:30", "12:30", "have_lunch", DINING, "午饭"),
            ("12:30", "13:30", "midday_rest", DORM, "午休"),
            ("13:30", "16:00", "group_discussion", DISCUSSION_LAB, "讨论"),
            ("16:00", "17:30", "coffee_break", CAFE_LIB, "咖啡"),
            ("17:30", "18:30", "have_dinner", DINING, "晚饭"),
            ("19:00", "21:30", "self_study", LIBRARY, "晚自习"),
            ("23:00", "23:59", "sleep", DORM, "睡觉"),
        ],
        "thursday": [
            ("07:30", "08:00", "wake_up", DORM, "起床"),
            ("08:00", "08:30", "have_breakfast", DINING, "早饭"),
            ("08:30", "11:30", "self_study", LIBRARY, "图书馆"),
            ("11:30", "12:30", "have_lunch", DINING, "午饭"),
            ("12:30", "13:30", "midday_rest", DORM, "午休"),
            ("14:00", "17:00", "self_study", LIBRARY, "继续"),
            ("17:00", "18:30", "exercise", GARDEN_ROOF, "操场"),
            ("18:30", "19:30", "have_dinner", DINING, "晚饭"),
            ("20:00", "22:00", "club_activity", CLUB, "社团"),
            ("23:00", "23:59", "sleep", DORM, "睡觉"),
        ],
        "friday": [
            ("07:30", "08:00", "wake_up", DORM, "起床"),
            ("08:00", "08:30", "have_breakfast", DINING, "早饭"),
            ("08:30", "11:30", "self_study", LIBRARY, "图书馆"),
            ("11:30", "12:30", "have_lunch", DINING, "午饭"),
            ("12:30", "13:30", "midday_rest", DORM, "午休"),
            ("13:30", "16:30", "self_study", LIBRARY, "周五收尾"),
            ("17:00", "18:30", "have_dinner", DINING, "周五聚餐"),
            ("19:00", "22:00", "free_time", CLUB, "周末前夜"),
            ("23:00", "23:59", "sleep", DORM, "睡觉"),
        ],
        "saturday": [
            ("09:00", "09:30", "wake_up", DORM, "晚起"),
            ("09:30", "10:30", "have_breakfast", CAFE_LIB, "早午餐"),
            ("10:30", "12:00", "read_for_fun", CAFE_LIB, "看书"),
            ("12:00", "13:00", "have_lunch", DINING, "午饭"),
            ("13:00", "14:30", "midday_rest", DORM, "午睡"),
            ("14:30", "17:00", "social_chat", CAFE_DOWN, "约人咖啡"),
            ("17:30", "18:30", "have_dinner", DINING, "晚饭"),
            ("19:00", "22:00", "free_time", CLUB, "周末娱乐"),
            ("23:30", "23:59", "sleep", DORM, "睡觉"),
        ],
        "sunday": [
            ("08:30", "09:00", "wake_up", DORM, "起床"),
            ("09:00", "09:30", "have_breakfast", DINING, "早饭"),
            ("09:30", "12:00", "self_study", LIBRARY, "整理一周"),
            ("12:00", "13:00", "have_lunch", DINING, "午饭"),
            ("13:00", "14:00", "midday_rest", DORM, "午休"),
            ("14:00", "16:30", "self_study", LIBRARY, "继续"),
            ("16:30", "17:30", "jog_or_walk", GARDEN_ROOF, "操场散步"),
            ("17:30", "18:30", "have_dinner", DINING, "晚饭"),
            ("19:00", "21:30", "free_time", DORM, "宿舍准备下周"),
            ("23:00", "23:59", "sleep", DORM, "早睡"),
        ],
    },
}


# ---------------------------------------------------------------------------
# Per-NPC mutation: small deterministic jitter so two NPCs of same archetype
# don't have identical schedules.
# ---------------------------------------------------------------------------

def _shift(hh_mm: str, minutes: int) -> str:
    """Shift `HH:MM` by `minutes` (can be negative). Clamps to [00:00, 23:59]."""
    h, m = map(int, hh_mm.split(":"))
    total = max(0, min(23 * 60 + 59, h * 60 + m + minutes))
    return f"{total // 60:02d}:{total % 60:02d}"


def _swap_meal_uid(uid: str, halal: bool) -> str:
    """Some NPCs prefer halal restaurant for meals."""
    if halal and uid == DINING:
        return HALAL
    return uid


def mutate_day(blocks: list[tuple[str, str, str, str, str]],
               seed: int, halal: bool) -> list[tuple[str, str, str, str, str]]:
    """Apply per-day mutation:

    - One day-wide jitter (in {-10,-5,0,+5,+10} minutes) is applied to every
      block's `start`/`end`, preserving relative ordering and never introducing
      overlap.
    - Halal-preferring NPCs swap the main dining hall to the halal restaurant.
    """
    rng = random.Random(seed)
    day_jitter = rng.choice([-10, -5, 0, 0, 0, 5, 5, 10])
    out: list[tuple[str, str, str, str, str]] = []
    for s, e, act, loc, narr in blocks:
        new_s = _shift(s, day_jitter)
        new_e = _shift(e, day_jitter)
        new_loc = _swap_meal_uid(loc, halal)
        out.append((new_s, new_e, act, new_loc, narr))
    out.sort(key=lambda b: b[0])
    return out


# ---------------------------------------------------------------------------
# Building one persona's template JSON
# ---------------------------------------------------------------------------

def build_template(persona: dict) -> dict:
    npc_id = persona["id"]
    arche = classify(persona)
    skel = SKELETONS.get(arche) or SKELETONS["other"]
    if not skel:
        raise RuntimeError(f"No skeleton for archetype {arche!r} (npc {npc_id})")

    halal = any("halal" in str(v).lower() or "清真" in str(v) or "穆斯林" in str(v)
                for v in persona.get("profile", {}).values())
    seed = hash(npc_id) & 0xFFFFFFFF
    rng = random.Random(seed)

    week: dict[str, list[dict]] = {}
    for d in WEEKDAYS:
        day_skel = skel.get(d, [])
        # Per-day seed so each day mutates independently but still deterministically.
        day_seed = (seed + ord(d[0]) * 1009) & 0xFFFFFFFF
        mutated = mutate_day(day_skel, day_seed, halal)
        blocks = []
        for s, e, act, loc, narr in mutated:
            blocks.append({
                "start": s,
                "end": e,
                "activity": act,
                "location_uid": loc,
                "narrative_zh": narr,
                "target_state": infer_target_state(act, loc),
            })
        week[d] = blocks

    # Slight per-NPC favorite-cafe swap (deterministic), so two NPCs same archetype differ a bit
    if rng.random() < 0.5:
        for d in WEEKDAYS:
            for b in week[d]:
                if b["activity"] == "coffee_break" and b["location_uid"] == CAFE_LIB:
                    b["location_uid"] = CAFE_DOWN
                    b["target_state"] = infer_target_state(b["activity"], CAFE_DOWN)

    return {
        "id": npc_id,
        "description": f"{persona.get('name', npc_id)} 的周课表（archetype={arche}，自动生成、每天差异化、含 target_state）。",
        "archetype": arche,
        "week": week,
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

VALID_TARGET_KEYS = {
    "agent.location_uid", "agent.energy", "agent.mood",
    "agent.retry_count",
}


def validate(template: dict, valid_uids: set[str]) -> list[str]:
    """Return list of error strings (empty = clean)."""
    errs: list[str] = []
    week = template.get("week", {})
    for d in WEEKDAYS:
        if d not in week:
            errs.append(f"missing weekday {d}")
            continue
        blocks = week[d]
        if not blocks:
            errs.append(f"{d}: empty block list")
            continue
        for i, b in enumerate(blocks):
            for k in ("start", "end", "activity", "location_uid", "target_state"):
                if k not in b:
                    errs.append(f"{d}[{i}]: missing {k}")
            if b.get("location_uid") not in valid_uids:
                errs.append(f"{d}[{i}]: bad uid {b.get('location_uid')!r}")
            for tk in (b.get("target_state") or {}):
                if not (tk in VALID_TARGET_KEYS or tk.startswith("agent.knows.")):
                    errs.append(f"{d}[{i}]: bad target_state key {tk!r}")
    return errs


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    if not PERSONAS_DIR.exists():
        print(f"!! Personas dir missing: {PERSONAS_DIR}", file=sys.stderr)
        return 1
    if not SCENES_PATH.exists():
        print(f"!! Scenes JSON missing: {SCENES_PATH}", file=sys.stderr)
        return 1

    scenes = json.loads(SCENES_PATH.read_text(encoding="utf-8"))
    valid_uids = {r["uid"] for r in scenes.get("rooms", [])}
    print(f"valid room uids: {len(valid_uids)}")

    persona_files = sorted(PERSONAS_DIR.glob("*.json"))
    print(f"persona files: {len(persona_files)}")

    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

    arche_counts: dict[str, int] = {}
    total_blocks = 0
    total_ts = 0
    n_written = 0
    errors_total = 0

    for pf in persona_files:
        persona = json.loads(pf.read_text(encoding="utf-8"))
        npc_id = persona["id"]

        arche = classify(persona)
        arche_counts[arche] = arche_counts.get(arche, 0) + 1

        tmpl = build_template(persona)
        errs = validate(tmpl, valid_uids)
        if errs:
            errors_total += len(errs)
            print(f"  !! {npc_id} has {len(errs)} errors: {errs[:3]}", file=sys.stderr)

        out_path = TEMPLATES_DIR / f"{npc_id}.json"
        out_path.write_text(
            json.dumps(tmpl, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        n_written += 1

        for d in WEEKDAYS:
            for b in tmpl["week"][d]:
                total_blocks += 1
                if "target_state" in b:
                    total_ts += 1

    print()
    print(f"wrote {n_written} template files")
    print(f"archetype counts: {arche_counts}")
    print(f"total blocks: {total_blocks}")
    print(f"with target_state: {total_ts}")
    print(f"validation errors: {errors_total}")
    return 0 if errors_total == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
