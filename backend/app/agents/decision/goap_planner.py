"""GOAP planner — A* over the action library.

Mirrors the JS reference in `goap_worldstate_actions_bilingual.html`
(see the `PLANNER` IIFE starting at line ~1583): an A* search where
each action's `pre` is a predicate over WorldState and `eff` is a
state transformer; `h` is the count of unmet goal predicates plus
soft hints.

Inputs:
- `actions`: list of `ActionSpec` (compiled callables).
- `initial_state`: dict (the perception-restricted view of WorldState).
- `goal`: dict of required key/value pairs.

Output: an ordered list of `PlanStep`.

Use `GoapPlanner.from_action_lib(lib, params={...})` to lift the JSON
DSL in `data/actions/actions.json` into compiled `ActionSpec`s. The
`params` dict supplies values for tokens like `target_uid`.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from .goap_dsl import compile_predicate, compile_transformer

if TYPE_CHECKING:  # pragma: no cover
    from app.agents.behavior.action_specs import ActionSpecLibrary


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
    def __init__(
        self,
        actions: list[ActionSpec],
        heuristic: Callable[[State, State], int] | None = None,
    ) -> None:
        self.actions = actions
        self.heuristic = heuristic or self._default_heuristic

    # ----- factory -----

    @classmethod
    def from_action_lib(
        cls,
        lib: "ActionSpecLibrary",
        params: dict[str, Any] | None = None,
    ) -> "GoapPlanner":
        """Compile every action in `lib` into a callable `ActionSpec`.

        `params` provides values for token-typed RHS fragments (e.g.
        `target_uid`); unbound tokens behave as opaque string literals so the
        planner can still expand `move(target_uid)` against an unknown target.
        """
        params = params or {}
        actions: list[ActionSpec] = []
        for doc in lib.all():
            pre = compile_predicate(doc.preconditions, params)
            eff = compile_transformer(doc.effects, params)
            actions.append(
                ActionSpec(
                    id=doc.id,
                    label=doc.label,
                    cost=doc.cost,
                    duration_minutes=doc.duration_minutes,
                    pre=pre,
                    eff=eff,
                )
            )
        return cls(actions)

    # ----- planning -----

    def plan(
        self,
        initial: State,
        goal: State,
        max_iters: int = 2000,
    ) -> list[PlanStep] | None:
        start_key = self._key(initial)
        open_heap: list[tuple[int, int, int, State, list[PlanStep]]] = []
        counter = 0
        h0 = self.heuristic(initial, goal)
        heapq.heappush(open_heap, (h0, 0, counter, initial, []))
        closed: dict[str, int] = {start_key: 0}

        while open_heap and max_iters > 0:
            max_iters -= 1
            _f, g, _c, state, plan = heapq.heappop(open_heap)
            if self._satisfies(state, goal):
                return plan

            for act in self.actions:
                try:
                    if not act.pre(state):
                        continue
                    new_state = act.eff(state)
                except Exception:
                    # A misbehaving DSL row should not crash the planner.
                    continue
                new_g = g + act.cost
                k = self._key(new_state)
                if k in closed and closed[k] <= new_g:
                    continue
                closed[k] = new_g
                new_plan = plan + [
                    PlanStep(
                        action_id=act.id,
                        label=act.label,
                        cost=act.cost,
                        duration_minutes=act.duration_minutes,
                    )
                ]
                counter += 1
                heapq.heappush(
                    open_heap,
                    (
                        new_g + self.heuristic(new_state, goal),
                        new_g,
                        counter,
                        new_state,
                        new_plan,
                    ),
                )
        return None

    # ----- helpers -----

    @staticmethod
    def _satisfies(state: State, goal: State) -> bool:
        return all(state.get(k) == v for k, v in goal.items())

    @staticmethod
    def _default_heuristic(state: State, goal: State) -> int:
        """Unmet-goal count plus a soft hint: numeric goals contribute their
        absolute delta when both sides are numeric, capped at 5 each.
        """
        score = 0
        for k, v in goal.items():
            sv = state.get(k)
            if sv == v:
                continue
            score += 1
            if isinstance(v, (int, float)) and isinstance(sv, (int, float)):
                score += min(5, int(abs(v - sv)))
        return score

    @staticmethod
    def _key(state: State) -> str:
        return "|".join(f"{k}={state[k]}" for k in sorted(state.keys()))
