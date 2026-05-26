"""Global, mutable WorldState — the single source of truth.

All action `effects` produced by `agents/behavior/executor.py` write here,
and all perception reads here. The frontend gets snapshots via REST and
deltas via WebSocket.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class AgentState:
    id: str
    location_uid: str
    energy: int = 3
    hunger: int = 0
    money: int = 5
    mood: int = 0
    holding: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ItemState:
    id: str
    location_uid: str
    status: str = "idle"
    extra: dict[str, Any] = field(default_factory=dict)


class WorldState:
    def __init__(self) -> None:
        self.agents: dict[str, AgentState] = {}
        self.items: dict[str, ItemState] = {}
        self.sim_time: datetime = datetime(2026, 5, 26, 7, 0)

    # ----- mutation -----

    def add_agent(self, agent: AgentState) -> None:
        self.agents[agent.id] = agent

    def add_item(self, item: ItemState) -> None:
        self.items[item.id] = item

    def move_agent(self, agent_id: str, to_uid: str) -> None:
        self.agents[agent_id].location_uid = to_uid

    # ----- queries -----

    def agents_in(self, location_uid: str) -> list[AgentState]:
        return [a for a in self.agents.values() if a.location_uid == location_uid]

    def items_in(self, location_uid: str) -> list[ItemState]:
        return [i for i in self.items.values() if i.location_uid == location_uid]

    # ----- export -----

    def snapshot(self) -> dict[str, Any]:
        return {
            "sim_time": self.sim_time.isoformat(),
            "agents": {aid: a.__dict__ for aid, a in self.agents.items()},
            "items": {iid: i.__dict__ for iid, i in self.items.items()},
        }
