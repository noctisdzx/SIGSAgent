"""Smoke test: load the scene graph and exercise children / siblings queries."""

from pathlib import Path

import pytest

from app.world.scene_graph import SceneGraph


SCENE_JSON = Path(__file__).resolve().parents[2] / "data" / "scenes" / "guoyi_rooms_v2.json"


@pytest.mark.skipif(not SCENE_JSON.exists(), reason="scene json not initialized yet")
def test_load_scene_graph():
    g = SceneGraph.from_json(SCENE_JSON)
    rooms = list(g.all_rooms())
    assert len(rooms) == 16, "guoyi_rooms_v2.json contains 16 rooms"
    sample = rooms[0]
    assert isinstance(g.adjacent(sample.uid), list)
    assert isinstance(g.children(sample.uid), list)
    assert isinstance(g.siblings(sample.uid), list)


@pytest.mark.skipif(not SCENE_JSON.exists(), reason="scene json not initialized yet")
def test_to_vis_graph_shape():
    g = SceneGraph.from_json(SCENE_JSON)
    vis = g.to_vis_graph()
    assert "nodes" in vis and "edges" in vis and "rooms" in vis
    assert len(vis["nodes"]) == 16
    assert len(vis["rooms"]) == 16
    # Every node should carry a vis-network friendly group + floor.
    for n in vis["nodes"]:
        assert n["id"]
        assert "group" in n
        assert "floor" in n
    # Edge endpoints must all reference valid rooms.
    room_ids = {r["uid"] for r in vis["rooms"]}
    for e in vis["edges"]:
        assert e["from"] in room_ids and e["to"] in room_ids


@pytest.mark.skipif(not SCENE_JSON.exists(), reason="scene json not initialized yet")
def test_children_siblings_semantics():
    g = SceneGraph.from_json(SCENE_JSON)
    # Dorm Rooms (438038e3) sits on z=8 and connects to many lower-floor rooms
    # → all its `children()` should be on a strictly lower floor.
    dorm = g.get("438038e3")
    z_dorm = dorm.position[2]
    for uid in g.children("438038e3"):
        assert g.get(uid).position[2] != z_dorm
    # Its siblings (if any) all sit at the same floor.
    for uid in g.siblings("438038e3"):
        assert g.get(uid).position[2] == z_dorm


def test_isolated_rooms_return_empty():
    g = SceneGraph([])
    assert g.children("missing") == []
    assert g.siblings("missing") == []
    assert g.adjacent("missing") == []
