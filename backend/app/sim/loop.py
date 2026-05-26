"""Per-tick orchestration: advance sim time, then each agent perceives→decides→acts."""

from __future__ import annotations

from app.events.bus import event_bus
from app.world.scene_graph import SceneGraph
from app.world.world_state import WorldState
from .clock import TickClock


class SimLoop:
    def __init__(self, world: WorldState, scene: SceneGraph) -> None:
        self.world = world
        self.scene = scene
        self.agents: dict = {}
        self.clock = TickClock(on_tick=self._tick)

    def register_agent(self, agent_id: str, agent) -> None:
        self.agents[agent_id] = agent

    async def _tick(self, idx: int) -> None:
        self.world.sim_time = self.world.sim_time + self.clock.sim_tick_delta

        for aid, agent in self.agents.items():
            try:
                await agent.perceive_decide_act(self.world, self.scene)
            except NotImplementedError:
                continue
            except Exception as exc:  # log + keep ticking
                await event_bus.publish({
                    "type": "agent_error",
                    "ts_sim": self.world.sim_time.isoformat(),
                    "agent_id": aid,
                    "payload": {"error": repr(exc)},
                })

        await event_bus.publish({
            "type": "tick",
            "ts_sim": self.world.sim_time.isoformat(),
            "payload": {"index": idx, "n_agents": len(self.agents)},
        })

    async def start(self) -> None:
        await self.clock.start()

    async def stop(self) -> None:
        await self.clock.stop()

    async def step(self) -> None:
        await self.clock.step()
