"""Runtime behavior executor.

Takes a `PlanStep` (from `GoapPlanner`), looks up its `ActionSpecDoc`,
checks preconditions against the WorldState, applies the `effects`, and
records the executed step into the agent's history (in-memory + SQLite).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.world.world_state import WorldState
from .action_specs import ActionSpecDoc, ActionSpecLibrary

log = logging.getLogger("sigs.behavior")


@dataclass
class ExecutedAction:
    ts: datetime
    agent_id: str
    action_id: str
    params: dict[str, Any] = field(default_factory=dict)
    ok: bool = True
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts.isoformat(),
            "agent_id": self.agent_id,
            "action_id": self.action_id,
            "params": dict(self.params),
            "ok": bool(self.ok),
            "note": self.note,
        }


class BehaviorExecutor:
    def __init__(self, library: ActionSpecLibrary, db: Any | None = None) -> None:
        """`db` is an optional `app.persistence.db.Database` for write-through."""
        self.library = library
        self.db = db
        self.history: dict[str, list[ExecutedAction]] = {}

    def set_db(self, db: Any) -> None:
        self.db = db

    async def execute(
        self,
        agent_id: str,
        action_id: str,
        params: dict[str, Any],
        world: WorldState,
    ) -> ExecutedAction:
        if not self.library.has(action_id):
            return self._record(agent_id, action_id, params, False,
                                f"unknown action: {action_id}", world)

        spec = self.library.get(action_id)
        ok, note = self._apply(spec, agent_id, params or {}, world)
        return await self._persist(self._record(agent_id, action_id, params or {}, ok, note, world))

    # ------------------------------------------------------------------

    def _apply(
        self,
        spec: ActionSpecDoc,
        agent_id: str,
        params: dict[str, Any],
        world: WorldState,
    ) -> tuple[bool, str]:
        """Check preconditions, then apply effects via WorldState.apply_action."""
        ok, note = world.check_preconditions(agent_id, spec.preconditions, params)
        if not ok:
            return False, f"precondition failed: {note}"
        return world.apply_action(agent_id, spec, params)

    def _record(self, agent_id: str, action_id: str, params: dict[str, Any],
                ok: bool, note: str, world: WorldState) -> ExecutedAction:
        record = ExecutedAction(
            ts=world.sim_time,
            agent_id=agent_id,
            action_id=action_id,
            params=dict(params),
            ok=ok,
            note=note,
        )
        self.history.setdefault(agent_id, []).append(record)
        return record

    async def _persist(self, record: ExecutedAction) -> ExecutedAction:
        if self.db is None:
            return record
        try:
            await self.db.append_behavior({
                "ts": record.ts.isoformat(),
                "agent_id": record.agent_id,
                "action_id": record.action_id,
                "params": json.dumps(record.params, ensure_ascii=False),
                "ok": 1 if record.ok else 0,
                "note": record.note,
            })
        except Exception as exc:
            log.warning("behavior persistence failed: %s", exc)
        return record

    # ------------------------------------------------------------------

    def history_for(self, agent_id: str, limit: int = 100) -> list[ExecutedAction]:
        items = self.history.get(agent_id, [])
        if limit <= 0:
            return list(items)
        return list(items[-limit:])
