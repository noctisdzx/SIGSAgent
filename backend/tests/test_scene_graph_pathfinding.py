"""Multi-hop pathfinding over the scene graph's undirected `adjacent` edges."""

from __future__ import annotations

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


def _graph() -> SceneGraph:
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


def test_shortest_path_multi_hop():
    g = _graph()
    assert g.shortest_path("A", "D") == ["A", "B", "C", "D"]


def test_shortest_path_direct_neighbor():
    g = _graph()
    assert g.shortest_path("A", "B") == ["A", "B"]


def test_shortest_path_same_node():
    g = _graph()
    assert g.shortest_path("A", "A") == ["A"]


def test_shortest_path_disconnected_is_none():
    g = _graph()
    assert g.shortest_path("A", "Z") is None


def test_shortest_path_unknown_endpoint_is_none():
    g = _graph()
    assert g.shortest_path("A", "missing") is None
    assert g.shortest_path("missing", "A") is None


def test_hop_distance():
    g = _graph()
    assert g.hop_distance("A", "D") == 3
    assert g.hop_distance("A", "A") == 0
    assert g.hop_distance("A", "Z") is None


def test_next_hop():
    g = _graph()
    assert g.next_hop("A", "D") == "B"
    assert g.next_hop("A", "E") == "E"
    # Already there / unreachable → no next hop.
    assert g.next_hop("A", "A") is None
    assert g.next_hop("A", "Z") is None
