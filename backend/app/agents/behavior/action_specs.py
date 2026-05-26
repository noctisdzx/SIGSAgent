"""Loads `data/actions/actions.json` and exposes a queryable library.

The JSON `preconditions` / `effects` are stored as string mini-DSL
(e.g. `"agent.energy": ">= 1"`); a tiny resolver compiles them into
callables for both the GOAP planner and the runtime executor.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.agents.decision.goap_planner import ActionSpec as GoapActionSpec


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
        return cls.from_list(raw.get("actions", []))

    @classmethod
    def from_list(cls, items: list[dict[str, Any]]) -> "ActionSpecLibrary":
        specs: list[ActionSpecDoc] = []
        for a in items:
            specs.append(ActionSpecDoc(
                id=a["id"],
                label=a.get("label", a["id"]),
                cost=int(a.get("cost", 1)),
                duration_minutes=int(a.get("duration_minutes", 5)),
                params=list(a.get("params", [])),
                preconditions=dict(a.get("preconditions", {})),
                effects=dict(a.get("effects", {})),
                concurrent_with=list(a.get("concurrent_with", [])),
                stochastic=a.get("stochastic"),
            ))
        return cls(specs)

    def get(self, action_id: str) -> ActionSpecDoc:
        return self._by_id[action_id]

    def has(self, action_id: str) -> bool:
        return action_id in self._by_id

    def all(self) -> list[ActionSpecDoc]:
        return list(self._by_id.values())

    # ------------------------------------------------------------------
    #   Compile string DSL preconditions/effects into GOAP callables.
    # ------------------------------------------------------------------

    def to_goap_actions(self) -> list[GoapActionSpec]:
        """Return GOAP-friendly ActionSpec[] usable by `GoapPlanner.plan()`.

        Planner states are plain dicts shaped like the keys we use in our
        DSL (`agent.location_uid`, `agent.energy`, ...). Because the GOAP
        search is performed on a per-agent symbolic projection of the world,
        we treat `target.*` / `item.*` paths as opaque keys; goals targeted
        at the executing agent need only `agent.*` keys.
        """
        out: list[GoapActionSpec] = []
        for doc in self._by_id.values():
            out.append(GoapActionSpec(
                id=doc.id,
                label=doc.label,
                cost=doc.cost,
                duration_minutes=doc.duration_minutes,
                pre=_compile_pre(doc.preconditions),
                eff=_compile_eff(doc.effects),
            ))
        return out


# ---------- DSL → callable compilers (mini-state, planner only) ----------

_TRUE = {"true", "yes", "on"}
_FALSE = {"false", "no", "off"}


def _coerce(token: str) -> Any:
    s = token.strip()
    if s.lower() in _TRUE:
        return True
    if s.lower() in _FALSE:
        return False
    if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
        return s[1:-1]
    try:
        if "." in s:
            return float(s)
        return int(s)
    except ValueError:
        return s  # treat bare ident as opaque symbol


def _resolve_rhs(token: str, state: dict[str, Any]) -> Any:
    if token in state:
        return state[token]
    return _coerce(token)


def _compile_pre(preconds: dict[str, str]):
    def pre(state: dict[str, Any]) -> bool:
        for path, expr in preconds.items():
            expr = (expr or "").strip()
            if not expr:
                continue
            for op in (">=", "<=", "==", "!=", ">", "<", "="):
                if expr.startswith(op):
                    rhs = expr[len(op):].strip()
                    break
            else:
                return False
            cur = state.get(path)
            rhs_val = _resolve_rhs(rhs, state)
            if op in ("=", "=="):
                if cur != rhs_val:
                    return False
            elif op == "!=":
                if cur == rhs_val:
                    return False
            else:
                try:
                    a = float(cur) if cur is not None else 0.0
                    b = float(rhs_val)
                except (TypeError, ValueError):
                    return False
                if op == ">" and not a > b:
                    return False
                if op == "<" and not a < b:
                    return False
                if op == ">=" and not a >= b:
                    return False
                if op == "<=" and not a <= b:
                    return False
        return True
    return pre


def _compile_eff(effects: dict[str, str]):
    def eff(state: dict[str, Any]) -> dict[str, Any]:
        new = dict(state)
        for path, expr in effects.items():
            expr = (expr or "").strip()
            if not expr:
                continue
            for op in ("+=", "-=", "*=", "/=", "="):
                if expr.startswith(op):
                    rhs = expr[len(op):].strip()
                    break
            else:
                continue
            value = _resolve_rhs(rhs, new)
            if op == "=":
                new[path] = value
                continue
            try:
                a = float(new.get(path) or 0)
                b = float(value)
            except (TypeError, ValueError):
                continue
            if op == "+=":
                a += b
            elif op == "-=":
                a -= b
            elif op == "*=":
                a *= b
            elif op == "/=" and b:
                a /= b
            new[path] = int(a) if a == int(a) else a
        return new
    return eff
