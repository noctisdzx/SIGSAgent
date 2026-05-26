"""Smoke test: load the scene graph and exercise children / siblings queries."""

from pathlib import Path

import pytest

from app.world.scene_graph import SceneGraph


SCENE_JSON = Path(__file__).resolve().parents[2] / "data" / "scenes" / "guoyi_rooms_v2.json"


@pytest.mark.skipif(not SCENE_JSON.exists(), reason="scene json not initialized yet")
def test_load_scene_graph():
    g = SceneGraph.from_json(SCENE_JSON)
    rooms = list(g.all_rooms())
    assert rooms, "scene file should contain rooms"
    sample = rooms[0]
    assert isinstance(g.adjacent(sample.uid), list)
    assert isinstance(g.children(sample.uid), list)
    assert isinstance(g.siblings(sample.uid), list)
