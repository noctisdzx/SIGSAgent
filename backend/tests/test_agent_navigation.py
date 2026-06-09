"""Stepwise navigation + perception-biased location preference on NPCAgent.

Uses the bare-agent pattern (bypass __init__, attach only what the methods
under test touch) so we don't need a full world/scene/LLM stack.
"""

from __future__ import annotations

from app.agents.agent import NPCAgent
from app.world.scene_graph import SceneGraph


def _room(uid: str, adjacent: list[str]) -> dict:
    return {
        "uid": uid,
        "index": 0,
        "name": uid,
        "tag": [],
        "adjacent": adjacent,
        "description": "",
        "position": [0, 0, 0],
        "containment": 0,
        "furniture": [],
    }


def _scene() -> SceneGraph:
    # A - B - C - D linear, A - E branch, Z isolated.
    return SceneGraph.from_dict({
        "rooms": [
            _room("A", ["B", "E"]),
            _room("B", ["A", "C"]),
            _room("C", ["B", "D"]),
            _room("D", ["C"]),
            _room("E", ["A"]),
            _room("Z", []),
        ]
    })


def _bare_agent() -> NPCAgent:
    a = NPCAgent.__new__(NPCAgent)
    a.scene = _scene()
    return a


def test_next_move_target_steps_one_hop():
    a = _bare_agent()
    # Far destination → return the next hop, not the final room.
    assert a._next_move_target("A", "D") == "B"


def test_next_move_target_disconnected_teleport_fallback():
    a = _bare_agent()
    # Unreachable → fall back to the destination (teleport), never stuck.
    assert a._next_move_target("A", "Z") == "Z"


def test_next_move_target_already_at_dest():
    a = _bare_agent()
    assert a._next_move_target("D", "D") == "D"


def test_next_move_target_handles_missing_current_or_dest():
    a = _bare_agent()
    assert a._next_move_target(None, "D") == "D"
    assert a._next_move_target("A", None) is None


def test_prefer_location_picks_visible_first():
    a = _bare_agent()
    # D is far (3 hops) but visible; C is nearer but not visible → visible wins.
    chosen = a._prefer_location("A", ["C", "D"], visible_uids={"D"})
    assert chosen == "D"


def test_prefer_location_picks_nearest_when_none_visible():
    a = _bare_agent()
    # None visible → nearest by hop distance (B at 1 hop beats D at 3).
    chosen = a._prefer_location("A", ["D", "B"], visible_uids=set())
    assert chosen == "B"


def test_prefer_location_empty_returns_none():
    a = _bare_agent()
    assert a._prefer_location("A", [], visible_uids=set()) is None
