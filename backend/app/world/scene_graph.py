"""Scene topology loaded from `data/scenes/*.json`.

`adjacent` is the literal undirected edge list from the data. From that we
derive two perception-friendly views:

- `children(uid)`  — adjacent rooms on a *lower* floor (`position[2]`)
                      *or, if none exist that way, on a higher floor*. Either
                      way "children" means "neighbours not on this floor".
- `siblings(uid)`  — adjacent rooms on the SAME floor.

If both sets are empty (an isolated node, e.g. `9a4098e7`/`da2afe02` in the
guoyi scene), call sites fall back to plain `adjacent()` for perception.
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
    def __init__(self, rooms: list[Room]) -> None:
        self._rooms: dict[str, Room] = {r.uid: r for r in rooms}

    # ----- loading -----

    @classmethod
    def from_json(cls, path: Path) -> "SceneGraph":
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SceneGraph":
        rooms = [
            Room(
                uid=r["uid"],
                index=r["index"],
                name=r["name"],
                tag=list(r.get("tag", [])),
                adjacent=list(r.get("adjacent", [])),
                description=r.get("description", ""),
                position=list(r.get("position", [0, 0, 0])),
                containment=r.get("containment", 0),
                furniture=list(r.get("furniture", [])),
            )
            for r in raw.get("rooms", [])
        ]
        return cls(rooms)

    # ----- queries -----

    def has(self, uid: str) -> bool:
        return uid in self._rooms

    def get(self, uid: str) -> Room:
        return self._rooms[uid]

    def all_rooms(self) -> Iterable[Room]:
        return self._rooms.values()

    def adjacent(self, uid: str) -> list[str]:
        if uid not in self._rooms:
            return []
        return list(self._rooms[uid].adjacent)

    def _floor(self, uid: str) -> float:
        pos = self._rooms[uid].position
        return pos[2] if len(pos) > 2 else 0.0

    def children(self, uid: str) -> list[str]:
        """Adjacent rooms whose floor differs (strictly lower preferred)."""
        if uid not in self._rooms:
            return []
        z = self._floor(uid)
        lower = [a for a in self._rooms[uid].adjacent
                 if a in self._rooms and self._floor(a) < z]
        if lower:
            return lower
        higher = [a for a in self._rooms[uid].adjacent
                  if a in self._rooms and self._floor(a) > z]
        return higher

    def siblings(self, uid: str) -> list[str]:
        """Adjacent rooms on the same floor."""
        if uid not in self._rooms:
            return []
        z = self._floor(uid)
        return [a for a in self._rooms[uid].adjacent
                if a in self._rooms and self._floor(a) == z]

    # ----- navigation (multi-hop over the global topology) -----

    def shortest_path(self, src: str, dst: str) -> list[str] | None:
        """BFS shortest path over the undirected `adjacent` graph.

        Returns the inclusive node path `[src, ..., dst]`. `src == dst` yields
        `[src]`. Returns None when either endpoint is unknown or `dst` is
        unreachable from `src` (disconnected components).

        NPCs are modelled as knowing the full campus topology, so the search
        spans the entire graph; perception only biases *which* destination an
        NPC prefers, not whether it can be reached.
        """
        if src not in self._rooms or dst not in self._rooms:
            return None
        if src == dst:
            return [src]
        # Standard queue BFS with a parent map for path reconstruction.
        from collections import deque
        prev: dict[str, str] = {src: src}
        queue: deque[str] = deque([src])
        while queue:
            cur = queue.popleft()
            for nxt in self._rooms[cur].adjacent:
                if nxt not in self._rooms or nxt in prev:
                    continue
                prev[nxt] = cur
                if nxt == dst:
                    # Reconstruct path from dst back to src.
                    path = [dst]
                    while path[-1] != src:
                        path.append(prev[path[-1]])
                    path.reverse()
                    return path
                queue.append(nxt)
        return None

    def hop_distance(self, src: str, dst: str) -> int | None:
        """Number of edges on the shortest path (0 when src == dst).

        Returns None when unreachable / unknown endpoints.
        """
        path = self.shortest_path(src, dst)
        return None if path is None else len(path) - 1

    def next_hop(self, src: str, dst: str) -> str | None:
        """The next node to step to along the shortest path toward `dst`.

        Returns None when already at `dst`, unreachable, or unknown.
        """
        path = self.shortest_path(src, dst)
        if not path or len(path) < 2:
            return None
        return path[1]

    # ----- export -----

    def to_dict(self) -> dict[str, Any]:
        return {
            "rooms": [r.__dict__ for r in self._rooms.values()],
        }

    def to_vis_graph(self) -> dict[str, Any]:
        """vis-network shaped payload: {nodes, edges, rooms}.

        - `group` is the room's first tag (e.g. "study", "social"), used for
          vis-network color schemes.
        - Edges are deduplicated undirected pairs `(min, max)` across all
          `adjacent` lists, plus a `floor` attribute (matching floor of the
          two endpoints, or `null` when crossing floors).
        """
        nodes: list[dict[str, Any]] = []
        for r in self._rooms.values():
            group = r.tag[0] if r.tag else "misc"
            floor = r.position[2] if len(r.position) > 2 else 0
            nodes.append({
                "id": r.uid,
                "label": r.name,
                "group": group,
                "title": r.description,
                "floor": floor,
                "tags": r.tag,
                "x": r.position[0] if len(r.position) > 0 else 0,
                "y": r.position[1] if len(r.position) > 1 else 0,
            })

        edges_seen: set[tuple[str, str]] = set()
        edges: list[dict[str, Any]] = []
        for r in self._rooms.values():
            for n in r.adjacent:
                if n not in self._rooms:
                    continue
                pair = tuple(sorted((r.uid, n)))
                if pair in edges_seen:
                    continue
                edges_seen.add(pair)
                same_floor = self._floor(r.uid) == self._floor(n)
                edges.append({
                    "from": pair[0],
                    "to": pair[1],
                    "same_floor": same_floor,
                })

        return {
            "nodes": nodes,
            "edges": edges,
            "rooms": [r.__dict__ for r in self._rooms.values()],
        }
