"""Verify the mini-DSL effect / precondition evaluator on a real action."""

from pathlib import Path

import pytest

from app.agents.behavior.action_specs import ActionSpecLibrary
from app.agents.behavior.executor import BehaviorExecutor
from app.world.scene_graph import SceneGraph
from app.world.world_state import AgentState, WorldState


SCENE_JSON = Path(__file__).resolve().parents[2] / "data" / "scenes" / "guoyi_rooms_v2.json"
ACTIONS_JSON = Path(__file__).resolve().parents[2] / "data" / "actions" / "actions.json"


@pytest.mark.skipif(not SCENE_JSON.exists() or not ACTIONS_JSON.exists(),
                    reason="seed data missing")
def test_apply_action_move_updates_location():
    scene = SceneGraph.from_json(SCENE_JSON)
    world = WorldState()
    rooms = list(scene.all_rooms())
    here, there = rooms[0].uid, rooms[1].uid
    world.add_agent(AgentState(id="npc_test", location_uid=here, energy=3))

    lib = ActionSpecLibrary.from_json(ACTIONS_JSON)
    move_spec = lib.get("move")

    ok, _ = world.check_preconditions("npc_test", move_spec.preconditions,
                                       {"target_uid": there})
    assert ok

    ok, _ = world.apply_action("npc_test", move_spec, {"target_uid": there})
    assert ok
    assert world.agents["npc_test"].location_uid == there
    assert world.agents["npc_test"].energy == 2


@pytest.mark.asyncio
async def test_executor_records_history():
    world = WorldState()
    world.add_agent(AgentState(id="npc_test", location_uid="A", energy=3))

    lib = ActionSpecLibrary.from_list([
        {"id": "move", "label": "move", "cost": 2, "duration_minutes": 5,
         "params": ["target_uid"],
         "preconditions": {"agent.location_uid": "!= target_uid"},
         "effects": {"agent.location_uid": "= target_uid"}},
    ])
    ex = BehaviorExecutor(lib)

    record = await ex.execute("npc_test", "move", {"target_uid": "B"}, world)
    assert record.ok
    assert world.agents["npc_test"].location_uid == "B"
    assert ex.history_for("npc_test")[-1].action_id == "move"


@pytest.mark.asyncio
async def test_executor_blocks_on_failed_precondition():
    world = WorldState()
    world.add_agent(AgentState(id="npc_test", location_uid="A", energy=0))

    lib = ActionSpecLibrary.from_list([
        {"id": "move", "label": "move", "cost": 2, "duration_minutes": 5,
         "params": ["target_uid"],
         "preconditions": {
             "agent.location_uid": "!= target_uid",
             "agent.energy": ">= 1",
         },
         "effects": {
             "agent.location_uid": "= target_uid",
             "agent.energy": "-= 1",
         }},
    ])
    ex = BehaviorExecutor(lib)
    record = await ex.execute("npc_test", "move", {"target_uid": "B"}, world)
    assert not record.ok
    assert "precondition failed" in record.note
    assert world.agents["npc_test"].location_uid == "A"


def test_populate_from_personas():
    world = WorldState()
    personas = {
        "a": {"id": "a", "initial_location_uid": "X"},
        "b": {"id": "b", "initial_location_uid": "Y"},
    }
    world.populate_from_personas(personas)
    assert world.agents["a"].location_uid == "X"
    assert world.agents["b"].location_uid == "Y"
