"""Smoke test for the A* GOAP planner: a 2-step plan must be found."""

from app.agents.decision.goap_planner import ActionSpec, GoapPlanner


def test_simple_plan():
    actions = [
        ActionSpec(
            id="get_book", label="get_book", cost=1,
            pre=lambda s: s.get("location") == "library" and not s.get("has_book"),
            eff=lambda s: {**s, "has_book": True},
        ),
        ActionSpec(
            id="move_lib", label="move(library)", cost=2,
            pre=lambda s: s.get("location") != "library",
            eff=lambda s: {**s, "location": "library"},
        ),
    ]
    plan = GoapPlanner(actions).plan(initial={"location": "dorm"}, goal={"has_book": True})
    assert plan is not None
    assert [s.action_id for s in plan] == ["move_lib", "get_book"]
