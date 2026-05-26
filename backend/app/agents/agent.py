"""NPCAgent aggregator.

Each NPC owns a perception view, a memory bundle, a decision pipeline,
and a behavior executor. The sim loop calls `perceive_decide_act(world)`
once per tick.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.world.scene_graph import SceneGraph
    from app.world.world_state import WorldState


@dataclass
class PersonaConfig:
    id: str
    name: str
    role: str
    personality: dict[str, float]
    preferences: dict[str, Any]
    relations: dict[str, Any]
    initial_location_uid: str
    schedule_template_id: str


class NPCAgent:
    def __init__(self, persona: PersonaConfig) -> None:
        self.persona = persona
        # Subsystems are wired by the sim loop / DI container to avoid cycles.
        self.memory: Any | None = None
        self.schedule: Any | None = None
        self.decision: Any | None = None
        self.behavior: Any | None = None
        self.perception: Any | None = None

    async def perceive_decide_act(self, world: "WorldState", scene: "SceneGraph") -> None:
        """One tick: perceive → decide → act → write memory."""
        raise NotImplementedError
