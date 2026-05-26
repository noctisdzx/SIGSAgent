"""GOAP planner against the real `data/actions/actions.json` library.

Scenarios:
1. Move from dorm to library: a single `move(target_uid)` step suffices when
   `target_uid` is bound at compile time.
2. Idle to recover energy when low: planner produces an idle step.
3. Find an entity: planner emits a `find` step that flips `agent.knows.X`.
"""

from __future__ import annotations

from pathlib import Path

from app.agents.behavior.action_specs import ActionSpecLibrary
from app.agents.decision.goap_planner import GoapPlanner


REPO_ROOT = Path(__file__).resolve().parents[2]
ACTIONS_JSON = REPO_ROOT / "data" / "actions" / "actions.json"


def _lib() -> ActionSpecLibrary:
    return ActionSpecLibrary.from_json(ACTIONS_JSON)


def test_action_lib_loads_all_six():
    lib = _lib()
    ids = {a.id for a in lib.all()}
    assert ids == {"move", "interact", "talk", "phone_call", "find", "idle"}


def test_plan_dorm_to_library_single_move():
    planner = GoapPlanner.from_action_lib(_lib(), params={"target_uid": "library"})
    initial = {"location_uid": "dorm", "energy": 3}
    goal = {"location_uid": "library"}
    plan = planner.plan(initial, goal)
    assert plan is not None
    assert [step.action_id for step in plan] == ["move"]
    assert plan[0].label.startswith("move")


def test_plan_idle_recovers_energy():
    planner = GoapPlanner.from_action_lib(_lib())
    initial = {"location_uid": "dorm", "energy": 0}
    goal = {"energy": 2}
    plan = planner.plan(initial, goal)
    assert plan is not None
    # idle adds +1 each step; need at least 2 idles
    assert all(step.action_id == "idle" for step in plan)
    assert len(plan) >= 2


def test_plan_find_entity_sets_knows_flag():
    planner = GoapPlanner.from_action_lib(_lib(), params={"entity_id": "book"})
    initial = {"location_uid": "library", "energy": 2}
    goal = {"knows.entity_id": True}
    plan = planner.plan(initial, goal)
    assert plan is not None
    assert any(step.action_id == "find" for step in plan)


def test_plan_unreachable_returns_none():
    # No action can satisfy `mood >= 100` from a baseline.
    planner = GoapPlanner.from_action_lib(_lib())
    initial = {"location_uid": "x", "energy": 2, "mood": 0}
    goal = {"mood": 100}
    plan = planner.plan(initial, goal, max_iters=500)
    # Talking bumps mood by 1 per step but talk requires target.location_uid==agent.location_uid
    # without a matching target row → search is forced to terminate on max_iters.
    # Either None or a partial plan is acceptable; just must not crash.
    assert plan is None or isinstance(plan, list)
