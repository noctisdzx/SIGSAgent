"""Runtime behavior executor.

Takes a `PlanStep` (from `GoapPlanner`), looks up its `ActionSpecDoc`,
applies the `effects` to the WorldState, and records the executed step
in the agent's history (consumed by the frontend's BehaviorHistory panel).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.world.world_state import WorldState
from .action_specs import ActionSpecDoc, ActionSpecLibrary


@dataclass
class ExecutedAction:
    ts: datetime
    agent_id: str
    action_id: str
    params: dict[str, Any] = field(default_factory=dict)
    ok: bool = True
    note: str = ""


class BehaviorExecutor:
    def __init__(self, library: ActionSpecLibrary) -> None:
        self.library = library
        self.history: dict[str, list[ExecutedAction]] = {}

    async def execute(
        self,
        agent_id: str,
        action_id: str,
        params: dict[str, Any],
        world: WorldState,
    ) -> ExecutedAction:
        spec = self.library.get(action_id)
        ok, note = self._apply(spec, agent_id, params, world)
        record = ExecutedAction(
            ts=world.sim_time,
            agent_id=agent_id,
            action_id=action_id,
            params=params,
            ok=ok,
            note=note,
        )
        self.history.setdefault(agent_id, []).append(record)
        return record

    def _apply(
        self,
        spec: ActionSpecDoc,
        agent_id: str,
        params: dict[str, Any],
        world: WorldState,
    ) -> tuple[bool, str]:
        # Placeholder: real implementation interprets the mini-DSL in `effects`.
        if spec.id == "move":
            target = params.get("target_uid")
            if target:
                world.move_agent(agent_id, target)
                return True, ""
            return False, "missing target_uid"
        return True, "noop (placeholder)"
