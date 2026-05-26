"""Placeholder perception test."""

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
