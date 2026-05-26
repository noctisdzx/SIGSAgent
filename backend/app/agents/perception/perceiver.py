"""NPC perception over the scene graph.

Spec:
- Visible nodes = `children(current_node)` (NO grandchildren)
                  ∪ `siblings(current_node via adjacent)`.
- For each visible node, expose its agents and items.
- Output is a `PerceptionSnapshot`, the input contract to the decision
  module and the basis for the frontend's PerceptionPanel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.world.scene_graph import SceneGraph
from app.world.world_state import WorldState


@dataclass
class VisibleRoom:
    uid: str
    name: str
    agents: list[str] = field(default_factory=list)
    items: list[str] = field(default_factory=list)


@dataclass
class PerceptionSnapshot:
    agent_id: str
    here_uid: str
    children: list[VisibleRoom] = field(default_factory=list)
    siblings: list[VisibleRoom] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


class Perceiver:
    def __init__(self, scene: SceneGraph) -> None:
        self.scene = scene

    def perceive(self, agent_id: str, world: WorldState) -> PerceptionSnapshot:
        here = world.agents[agent_id].location_uid
        children_uids = self.scene.children(here)
        sibling_uids = self.scene.siblings(here)

        return PerceptionSnapshot(
            agent_id=agent_id,
            here_uid=here,
            children=[self._materialize(uid, world) for uid in children_uids],
            siblings=[self._materialize(uid, world) for uid in sibling_uids],
        )

    def _materialize(self, uid: str, world: WorldState) -> VisibleRoom:
        room = self.scene.get(uid)
        return VisibleRoom(
            uid=uid,
            name=room.name,
            agents=[a.id for a in world.agents_in(uid)],
            items=[i.id for i in world.items_in(uid)],
        )
