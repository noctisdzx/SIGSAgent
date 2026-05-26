"""GOAP planner — A* over the action library.

Mirrors the JS reference in `goap_worldstate_actions_bilingual.html`
(see the `PLANNER` IIFE starting at line ~1583): an A* search where
each action's `pre` is a predicate over WorldState and `eff` is a
state transformer; `h` is the count of unmet goal predicates plus
soft hints.

Inputs:
- `actions`: list of ActionSpec from `data/actions/actions.json`
- `initial_state`: dict (the perception-restricted view of WorldState)
- `goal`: dict of required key/value pairs

Output: an ordered list of `PlanStep`.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Any, Callable


State = dict[str, Any]


@dataclass
class ActionSpec:
    id: str
    label: str
    cost: int
    duration_minutes: int = 5
    pre: Callable[[State], bool] = field(default=lambda s: True)
    eff: Callable[[State], State] = field(default=lambda s: s)


@dataclass
class PlanStep:
    action_id: str
    label: str
    cost: int
    duration_minutes: int


class GoapPlanner:
    def __init__(self, actions: list[ActionSpec], heuristic: Callable[[State, State], int] | None = None) -> None:
        self.actions = actions
        self.heuristic = heuristic or self._default_heuristic

    def plan(self, initial: State, goal: State, max_iters: int = 2000) -> list[PlanStep] | None:
        start_key = self._key(initial)
        open_heap: list[tuple[int, int, int, State, list[PlanStep]]] = []
        counter = 0
        h0 = self.heuristic(initial, goal)
        heapq.heappush(open_heap, (h0, 0, counter, initial, []))
        closed: dict[str, int] = {start_key: 0}

        while open_heap and max_iters > 0:
            max_iters -= 1
            f, g, _, state, plan = heapq.heappop(open_heap)
            if self._satisfies(state, goal):
                return plan

            for act in self.actions:
                if not act.pre(state):
                    continue
                new_state = act.eff(state)
                new_g = g + act.cost
                k = self._key(new_state)
                if k in closed and closed[k] <= new_g:
                    continue
                closed[k] = new_g
                new_plan = plan + [PlanStep(
                    action_id=act.id, label=act.label,
                    cost=act.cost, duration_minutes=act.duration_minutes,
                )]
                counter += 1
                heapq.heappush(open_heap, (
                    new_g + self.heuristic(new_state, goal),
                    new_g, counter, new_state, new_plan,
                ))
        return None

    # ----- helpers -----

    @staticmethod
    def _satisfies(state: State, goal: State) -> bool:
        return all(state.get(k) == v for k, v in goal.items())

    @staticmethod
    def _default_heuristic(state: State, goal: State) -> int:
        return sum(1 for k, v in goal.items() if state.get(k) != v)

    @staticmethod
    def _key(state: State) -> str:
        return "|".join(f"{k}={state[k]}" for k in sorted(state.keys()))
