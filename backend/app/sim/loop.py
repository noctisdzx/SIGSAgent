"""Per-tick orchestration: advance sim time, then each agent perceives→decides→acts."""

from __future__ import annotations

import logging
from typing import Any

from app.events.bus import event_bus
from app.world.scene_graph import SceneGraph
from app.world.world_state import WorldState
from .clock import TickClock

log = logging.getLogger("sigs.sim")


class SimLoop:
    def __init__(self, world: WorldState, scene: SceneGraph) -> None:
        self.world = world
        self.scene = scene
        self.agents: dict[str, Any] = {}
        self.clock = TickClock(on_tick=self._tick)
        self._running = False
        self._latest_decisions: list[dict[str, Any]] = []

    # ----- registration -----

    def register_agent(self, agent_id: str, agent: Any) -> None:
        self.agents[agent_id] = agent

    def unregister_agent(self, agent_id: str) -> None:
        self.agents.pop(agent_id, None)

    def clear_agents(self) -> None:
        self.agents.clear()

    # ----- tick -----

    async def _tick(self, idx: int) -> None:
        # Snapshot positions BEFORE the tick so we can compute world_delta.
        before = {aid: a.location_uid for aid, a in self.world.agents.items()}

        self.world.sim_time = self.world.sim_time + self.clock.sim_tick_delta

        recent_decisions: list[dict[str, Any]] = []
        for aid, agent in self.agents.items():
            try:
                await agent.perceive_decide_act(self.world, self.scene)
                # Best-effort latest-decision snapshot for the tick payload.
                history = getattr(agent, "behavior_executor", None)
                if history and getattr(history, "history", None):
                    last = history.history.get(aid, [])
                    if last:
                        recent_decisions.append(last[-1].to_dict())
            except NotImplementedError:
                continue
            except Exception as exc:
                log.exception("agent %s tick failed: %s", aid, exc)
                await event_bus.publish({
                    "type": "agent_error",
                    "ts_sim": self.world.sim_time.isoformat(),
                    "agent_id": aid,
                    "payload": {"error": repr(exc)},
                })

        # Compute world_delta: which agents moved this tick.
        moved: list[dict[str, str]] = []
        for aid, a in self.world.agents.items():
            prev = before.get(aid)
            if prev is not None and prev != a.location_uid:
                moved.append({"agent_id": aid, "from": prev, "to": a.location_uid})

        self._latest_decisions = recent_decisions

        await event_bus.publish({
            "type": "tick",
            "ts_sim": self.world.sim_time.isoformat(),
            "payload": {
                "index": idx,
                "n_agents": len(self.agents),
                "world_delta": {"moved": moved},
                "recent_decisions": recent_decisions[:20],
            },
        })

    # ----- control -----

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        await self.clock.start()

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        await self.clock.stop()

    async def step(self) -> None:
        await self.clock.step()

    @property
    def is_running(self) -> bool:
        return self._running
