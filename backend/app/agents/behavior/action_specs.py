"""Loads `data/actions/actions.json` and exposes a queryable library.

The JSON `preconditions` / `effects` are stored as string mini-DSL
(e.g. `"agent.energy": ">= 1"`); a tiny resolver compiles them into
callables for both the GOAP planner and the runtime executor.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ActionSpecDoc:
    id: str
    label: str
    cost: int
    duration_minutes: int = 5
    params: list[str] = field(default_factory=list)
    preconditions: dict[str, str] = field(default_factory=dict)
    effects: dict[str, str] = field(default_factory=dict)
    concurrent_with: list[str] = field(default_factory=list)
    stochastic: dict | None = None


class ActionSpecLibrary:
    def __init__(self, actions: list[ActionSpecDoc]) -> None:
        self._by_id: dict[str, ActionSpecDoc] = {a.id: a for a in actions}

    @classmethod
    def from_json(cls, path: Path) -> "ActionSpecLibrary":
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls([ActionSpecDoc(**a) for a in raw.get("actions", [])])

    def get(self, action_id: str) -> ActionSpecDoc:
        return self._by_id[action_id]

    def all(self) -> list[ActionSpecDoc]:
        return list(self._by_id.values())
