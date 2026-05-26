"""Global, mutable WorldState — the single source of truth.

All action `effects` produced by `agents/behavior/executor.py` write here,
and all perception reads here. The frontend gets snapshots via REST and
deltas via WebSocket.

DSL recap (from `data/actions/actions.json`):
    - Path tokens:    `agent.*`, `target.*`, `item.*`
    - Effect ops:     `= <expr>`, `+= n`, `-= n`
    - Precondition ops: `==`, `!=`, `>=`, `<=`, `>`, `<`, `=` (alias of `==`)

`<expr>` is one of:
    - a numeric literal (`5`, `-1`, `0.5`)
    - a boolean literal (`true`, `false`)
    - a string literal (anything quoted, or anything that doesn't parse as
      a number / boolean and is not itself a path token)
    - a param-name token (`target_uid`, `item_id`, etc. — resolved from
      `params`)
    - another path token (e.g. `agent.location_uid`) — resolved from the
      current world state
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


# ============================================================
#                Mini-DSL for preconditions / effects
# ============================================================

_TRUE = {"true", "yes", "on"}
_FALSE = {"false", "no", "off"}


def _try_literal(token: str) -> Any | None:
    """Try to parse a literal; return None when it isn't one."""
    s = token.strip()
    if not s:
        return ""
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
        return None


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
        if agent_id in self.agents:
            self.agents[agent_id].location_uid = to_uid

    def populate_from_personas(self, personas: dict) -> None:
        """Seed AgentStates from the persona registry (Pydantic models or dicts)."""
        for pid, p in personas.items():
            loc = getattr(p, "initial_location_uid", None) or (
                p.get("initial_location_uid") if isinstance(p, dict) else None
            )
            if loc is None:
                continue
            if pid in self.agents:
                self.agents[pid].location_uid = loc
            else:
                self.agents[pid] = AgentState(id=pid, location_uid=loc)

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

    # ============================================================
    #                  DSL evaluation
    # ============================================================

    def _holder(self, path: str, agent_id: str, params: dict[str, Any]):
        """Resolve a `root.attr.attr...` path into (container, leaf_attr).

        Returns (None, None) when the path can't be resolved (e.g. target not
        provided, item missing). Callers must handle the None case.
        """
        parts = path.split(".")
        root = parts[0]
        leaf = parts[-1]
        middle = parts[1:-1]

        if root == "agent":
            obj: Any = self.agents.get(agent_id)
        elif root == "target":
            target_id = params.get("target_agent_id") or params.get("target_uid")
            obj = self.agents.get(target_id) if target_id else None
        elif root == "item":
            item_id = params.get("item_id") or params.get("entity_id")
            obj = self.items.get(item_id) if item_id else None
        else:
            return None, None

        if obj is None:
            return None, None

        # Walk middle attributes, lazily creating dicts inside `.extra`.
        for m in middle:
            obj = _attr_or_extra(obj, m, create=True)
            if obj is None:
                return None, None

        return obj, leaf

    def _read_path(self, path: str, agent_id: str, params: dict[str, Any]) -> Any:
        holder, leaf = self._holder(path, agent_id, params)
        if holder is None:
            return None
        return _attr_or_extra(holder, leaf, create=False)

    def _resolve_value(self, token: str, agent_id: str, params: dict[str, Any]) -> Any:
        """Resolve an RHS token into a concrete value."""
        s = token.strip()
        if not s:
            return ""

        if s in params:
            return params[s]

        lit = _try_literal(s)
        if lit is not None:
            return lit

        if "." in s and s.split(".", 1)[0] in {"agent", "target", "item"}:
            return self._read_path(s, agent_id, params)

        # bare identifier that isn't a param / literal / path → treat as string
        return s

    # ---------- public ----------

    def apply_effect(self, agent_id: str, path: str, op_expr: str,
                     params: dict[str, Any]) -> tuple[bool, str]:
        """Apply ONE effect rule. Returns (ok, note)."""
        op_expr = (op_expr or "").strip()
        if not op_expr:
            return True, "noop"

        # split "op rhs"; recognise 2-char ops first
        for op in ("+=", "-=", "*=", "/=", "="):
            if op_expr.startswith(op):
                rhs = op_expr[len(op):].strip()
                break
        else:
            return False, f"unknown effect op: {op_expr!r}"

        holder, leaf = self._holder(path, agent_id, params)
        if holder is None:
            return False, f"effect target unresolved: {path}"

        value = self._resolve_value(rhs, agent_id, params)

        if op == "=":
            _set(holder, leaf, value)
            return True, ""
        cur = _attr_or_extra(holder, leaf, create=False)
        try:
            num_cur = float(cur) if cur is not None else 0.0
            num_val = float(value)
        except (TypeError, ValueError):
            return False, f"non-numeric arithmetic on {path}: cur={cur!r}, rhs={value!r}"
        if op == "+=":
            new = num_cur + num_val
        elif op == "-=":
            new = num_cur - num_val
        elif op == "*=":
            new = num_cur * num_val
        elif op == "/=":
            new = num_cur / num_val if num_val else num_cur
        # Preserve int-ness when both sides were int-like.
        if isinstance(cur, int) and float(new).is_integer():
            new = int(new)
        _set(holder, leaf, new)
        return True, ""

    def check_precondition(self, agent_id: str, path: str, op_expr: str,
                           params: dict[str, Any]) -> tuple[bool, str]:
        """Evaluate ONE precondition rule. Returns (ok, note)."""
        op_expr = (op_expr or "").strip()
        if not op_expr:
            return True, ""

        for op in (">=", "<=", "==", "!=", ">", "<", "="):
            if op_expr.startswith(op):
                rhs = op_expr[len(op):].strip()
                break
        else:
            return False, f"unknown precondition op: {op_expr!r}"

        cur = self._read_path(path, agent_id, params)
        rhs_val = self._resolve_value(rhs, agent_id, params)

        if op in ("=", "=="):
            return (cur == rhs_val), f"{path}={cur!r} == {rhs_val!r}"
        if op == "!=":
            return (cur != rhs_val), f"{path}={cur!r} != {rhs_val!r}"

        try:
            a = float(cur) if cur is not None else 0.0
            b = float(rhs_val)
        except (TypeError, ValueError):
            return False, f"non-numeric comparison on {path}: {cur!r} {op} {rhs_val!r}"
        cmp = {">": a > b, "<": a < b, ">=": a >= b, "<=": a <= b}[op]
        return cmp, f"{path}={cur!r} {op} {rhs_val!r}"

    def check_preconditions(self, agent_id: str, preconditions: dict[str, str],
                            params: dict[str, Any]) -> tuple[bool, str]:
        for path, expr in preconditions.items():
            ok, note = self.check_precondition(agent_id, path, expr, params)
            if not ok:
                return False, note
        return True, ""

    def apply_action(self, agent_id: str, action_spec: Any,
                     params: dict[str, Any]) -> tuple[bool, str]:
        """Apply all `effects` of an action spec (dataclass or pydantic model).

        Does *not* check preconditions itself — the BehaviorExecutor is
        responsible for that so it can choose to log a `precondition failed`
        record without applying any effects.
        """
        effects: dict[str, str] = getattr(action_spec, "effects", None) or {}
        notes: list[str] = []
        for path, expr in effects.items():
            ok, note = self.apply_effect(agent_id, path, expr, params)
            if note:
                notes.append(note)
            if not ok:
                return False, "; ".join(notes)
        return True, "; ".join(n for n in notes if n)


# ---------- helpers ----------

def _attr_or_extra(obj: Any, name: str, *, create: bool):
    """Read (or create) `obj.<name>` or `obj.extra[<name>]` or `obj[<name>]`."""
    if isinstance(obj, dict):
        if create and name not in obj:
            obj[name] = {}
        return obj.get(name)
    if hasattr(obj, name):
        return getattr(obj, name)
    extra = getattr(obj, "extra", None)
    if isinstance(extra, dict):
        if name in extra:
            return extra[name]
        if create:
            extra[name] = {}
            return extra[name]
    return None


def _set(obj: Any, name: str, value: Any) -> None:
    if isinstance(obj, dict):
        obj[name] = value
        return
    if hasattr(obj, name):
        setattr(obj, name, value)
        return
    extra = getattr(obj, "extra", None)
    if isinstance(extra, dict):
        extra[name] = value
        return
    setattr(obj, name, value)
