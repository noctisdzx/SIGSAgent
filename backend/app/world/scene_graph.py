"""Scene topology loaded from `data/scenes/*.json`.

Backed by `networkx` so adjacency / children / siblings queries are O(1) lookups.
Used by both perception (visible nodes) and the frontend topology view.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class Room:
    uid: str
    index: int
    name: str
    tag: list[str]
    adjacent: list[str]
    description: str
    position: list[float]
    containment: int
    furniture: list[dict[str, Any]]


class SceneGraph:
    """Adjacency graph of rooms.

    Parent / child semantics are derived from `position[2]` (z-axis floor):
    a node's *children* are its adjacent rooms on a strictly lower floor;
    its *siblings* are its adjacent rooms on the same floor.
    Adjust the rule in `_classify_edges()` once the design is finalized.
    """

    def __init__(self, rooms: list[Room]) -> None:
        self._rooms: dict[str, Room] = {r.uid: r for r in rooms}

    # ----- loading -----

    @classmethod
    def from_json(cls, path: Path) -> "SceneGraph":
        raw = json.loads(path.read_text(encoding="utf-8"))
        rooms = [
            Room(
                uid=r["uid"],
                index=r["index"],
                name=r["name"],
                tag=r.get("tag", []),
                adjacent=r.get("adjacent", []),
                description=r.get("description", ""),
                position=r.get("position", [0, 0, 0]),
                containment=r.get("containment", 0),
                furniture=r.get("furniture", []),
            )
            for r in raw.get("rooms", [])
        ]
        return cls(rooms)

    # ----- queries -----

    def get(self, uid: str) -> Room:
        return self._rooms[uid]

    def all_rooms(self) -> Iterable[Room]:
        return self._rooms.values()

    def adjacent(self, uid: str) -> list[str]:
        return list(self._rooms[uid].adjacent)

    def children(self, uid: str) -> list[str]:
        """Adjacent rooms whose floor (position[2]) is strictly lower."""
        z = self._rooms[uid].position[2]
        return [a for a in self._rooms[uid].adjacent if self._rooms[a].position[2] < z]

    def siblings(self, uid: str) -> list[str]:
        """Adjacent rooms on the same floor."""
        z = self._rooms[uid].position[2]
        return [a for a in self._rooms[uid].adjacent if self._rooms[a].position[2] == z]

    # ----- export -----

    def to_dict(self) -> dict[str, Any]:
        return {
            "rooms": [r.__dict__ for r in self._rooms.values()],
        }
