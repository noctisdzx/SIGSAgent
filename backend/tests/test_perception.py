"""Perception tests covering both the simple case and the to_dict serializer."""

from pathlib import Path

import pytest

from app.agents.perception.perceiver import Perceiver
from app.world.scene_graph import SceneGraph
from app.world.world_state import AgentState, WorldState


SCENE_JSON = Path(__file__).resolve().parents[2] / "data" / "scenes" / "guoyi_rooms_v2.json"


@pytest.mark.skipif(not SCENE_JSON.exists(), reason="scene json not initialized yet")
def test_perceive_returns_snapshot():
    scene = SceneGraph.from_json(SCENE_JSON)
    world = WorldState()
    here = next(iter(scene.all_rooms())).uid
    world.add_agent(AgentState(id="alice", location_uid=here))

    snap = Perceiver(scene).perceive("alice", world)
    assert snap.agent_id == "alice"
    assert snap.here_uid == here
    assert isinstance(snap.children, list)
    assert isinstance(snap.siblings, list)


@pytest.mark.skipif(not SCENE_JSON.exists(), reason="scene json not initialized yet")
def test_perceive_to_dict_is_jsonable():
    import json

    scene = SceneGraph.from_json(SCENE_JSON)
    world = WorldState()
    here = "438038e3"  # Dorm Rooms — has many adjacent rooms
    world.add_agent(AgentState(id="alice", location_uid=here))

    snap = Perceiver(scene).perceive("alice", world)
    d = snap.to_dict()
    # Should be JSON-serializable.
    payload = json.dumps(d, ensure_ascii=False)
    assert "alice" in payload
    assert d["here_uid"] == here
    assert d["here_name"] == "Dorm Rooms"
    # Dorm Rooms is on z=8 with lower-floor neighbours → children must be non-empty.
    assert d["children"], "expected at least one child for the Dorm Rooms node"
    for child in d["children"]:
        assert child["uid"]
        assert "agents" in child
        assert "items" in child


def test_perceive_unknown_agent_safe():
    scene = SceneGraph([])
    world = WorldState()
    snap = Perceiver(scene).perceive("nobody", world)
    assert snap.agent_id == "nobody"
    assert snap.here_uid == ""
    assert snap.children == []
