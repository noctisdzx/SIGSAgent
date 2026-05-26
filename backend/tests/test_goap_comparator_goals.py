"""GOAP comparator-string goals (>=, <=, >, <, ==, !=).

These tests verify the planner correctly interprets the comparator syntax
emitted by schedule-template `target_state` fields (e.g. `"agent.energy": ">=3"`)
without needing eval, and that the heuristic still steers A* toward numeric goals.
"""

from __future__ import annotations

from pathlib import Path

from app.agents.behavior.action_specs import ActionSpecLibrary
from app.agents.decision.goap_planner import GoapPlanner


REPO_ROOT = Path(__file__).resolve().parents[2]
ACTIONS_JSON = REPO_ROOT / "data" / "actions" / "actions.json"


def _lib() -> ActionSpecLibrary:
    return ActionSpecLibrary.from_json(ACTIONS_JSON)


# ---- parser unit tests ---------------------------------------------------

def test_parse_spec_plain_literal_is_eq():
    assert GoapPlanner._parse_spec("foo") == ("==", "foo")
    assert GoapPlanner._parse_spec(3) == ("==", 3)
    assert GoapPlanner._parse_spec(True) == ("==", True)


def test_parse_spec_two_char_ops():
    assert GoapPlanner._parse_spec(">=3") == (">=", 3)
    assert GoapPlanner._parse_spec("<=5") == ("<=", 5)
    assert GoapPlanner._parse_spec("==done") == ("==", "done")
    assert GoapPlanner._parse_spec("!=banned") == ("!=", "banned")


def test_parse_spec_single_char_ops():
    assert GoapPlanner._parse_spec(">5") == (">", 5)
    assert GoapPlanner._parse_spec("<2") == ("<", 2)


def test_matches_string_vs_string():
    assert GoapPlanner._matches("room1", "room1")
    assert not GoapPlanner._matches("room1", "room2")
    assert GoapPlanner._matches("room1", "!=room2")


def test_matches_numeric_comparator():
    assert GoapPlanner._matches(3, ">=3")
    assert GoapPlanner._matches(4, ">=3")
    assert not GoapPlanner._matches(2, ">=3")
    assert GoapPlanner._matches(1, "<=3")
    assert not GoapPlanner._matches(5, "<=3")
    assert GoapPlanner._matches(3, ">2")
    assert not GoapPlanner._matches(2, ">2")


def test_matches_numeric_from_string_state():
    # Numeric state stored as string also coerces.
    assert GoapPlanner._matches("3", ">=3")
    assert not GoapPlanner._matches("apple", ">=3")


# ---- end-to-end plans with comparator goals -------------------------------

def test_plan_energy_geq_two_via_idle():
    planner = GoapPlanner.from_action_lib(_lib())
    initial = {"location_uid": "dorm", "energy": 0}
    # mirrors a schedule block: {"agent.location_uid": "dorm", "agent.energy": ">=2"}
    # (we drop the agent.* prefix here because actions.json uses bare keys)
    goal = {"location_uid": "dorm", "energy": ">=2"}
    plan = planner.plan(initial, goal)
    assert plan is not None and len(plan) >= 2
    assert all(step.action_id == "idle" for step in plan)


def test_plan_energy_geq_satisfied_immediately():
    planner = GoapPlanner.from_action_lib(_lib())
    initial = {"location_uid": "lib", "energy": 5}
    goal = {"location_uid": "lib", "energy": ">=2"}
    plan = planner.plan(initial, goal)
    assert plan == []  # goal already met -> empty plan


def test_plan_combines_move_and_energy_comparator():
    planner = GoapPlanner.from_action_lib(_lib(), params={"target_uid": "lib"})
    initial = {"location_uid": "dorm", "energy": 1}
    goal = {"location_uid": "lib", "energy": ">=2"}
    plan = planner.plan(initial, goal)
    assert plan is not None
    ids = [s.action_id for s in plan]
    assert "move" in ids
    assert ids.count("idle") >= 1


def test_satisfies_mixed_keys_eq_and_comparator():
    state = {"location_uid": "lib", "energy": 4, "mood": 3}
    assert GoapPlanner._satisfies(state, {"location_uid": "lib", "energy": ">=3"})
    assert not GoapPlanner._satisfies(state, {"location_uid": "lib", "mood": ">=10"})
    assert GoapPlanner._satisfies(state, {"location_uid": "lib", "mood": "<=10"})


def test_default_heuristic_zero_when_all_matched():
    state = {"location_uid": "lib", "energy": 5}
    goal = {"location_uid": "lib", "energy": ">=3"}
    assert GoapPlanner._default_heuristic(state, goal) == 0


def test_default_heuristic_positive_when_unmet():
    state = {"location_uid": "dorm", "energy": 0}
    goal = {"location_uid": "lib", "energy": ">=3"}
    # 1 for location mismatch + 1 (unmet) + delta hint 3 for energy
    score = GoapPlanner._default_heuristic(state, goal)
    assert score >= 2
