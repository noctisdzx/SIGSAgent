"""NPC perception over the scene graph.

Spec:
- Visible nodes = `children(current_node)` (NO grandchildren)
                  ∪ `siblings(current_node via adjacent)`.
- If both sets are empty (isolated rooms in the source data) we fall back to
  raw `adjacent()` so the NPC isn't blind.
- For each visible node, expose its agents and items.
- Output is a `PerceptionSnapshot`, the input contract to the decision
  module and the basis for the frontend's PerceptionPanel.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.world.scene_graph import SceneGraph
from app.world.world_state import WorldState


@dataclass
class VisibleRoom:
    uid: str
    name: str
    tags: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    items: list[str] = field(default_factory=list)


@dataclass
class PerceptionSnapshot:
    agent_id: str
    here_uid: str
    here_name: str = ""
    children: list[VisibleRoom] = field(default_factory=list)
    siblings: list[VisibleRoom] = field(default_factory=list)
    adjacent_fallback: list[VisibleRoom] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "here_uid": self.here_uid,
            "here_name": self.here_name,
            "children": [asdict(r) for r in self.children],
            "siblings": [asdict(r) for r in self.siblings],
            "adjacent_fallback": [asdict(r) for r in self.adjacent_fallback],
            "raw": dict(self.raw),
        }


class Perceiver:
    def __init__(self, scene: SceneGraph) -> None:
        self.scene = scene

    def perceive(self, agent_id: str, world: WorldState) -> PerceptionSnapshot:
        agent = world.agents.get(agent_id)
        if agent is None:
            return PerceptionSnapshot(agent_id=agent_id, here_uid="")
        here = agent.location_uid
        here_name = ""
        if self.scene.has(here):
            here_name = self.scene.get(here).name

        children_uids = self.scene.children(here)
        sibling_uids = self.scene.siblings(here)

        fallback_uids: list[str] = []
        if not children_uids and not sibling_uids:
            fallback_uids = self.scene.adjacent(here)

        return PerceptionSnapshot(
            agent_id=agent_id,
            here_uid=here,
            here_name=here_name,
            children=[self._materialize(uid, world) for uid in children_uids],
            siblings=[self._materialize(uid, world) for uid in sibling_uids],
            adjacent_fallback=[self._materialize(uid, world) for uid in fallback_uids],
        )

    def _materialize(self, uid: str, world: WorldState) -> VisibleRoom:
        if not self.scene.has(uid):
            return VisibleRoom(uid=uid, name="(unknown)")
        room = self.scene.get(uid)
        return VisibleRoom(
            uid=uid,
            name=room.name,
            tags=list(room.tag),
            agents=[a.id for a in world.agents_in(uid)],
            items=[i.id for i in world.items_in(uid)],
        )
