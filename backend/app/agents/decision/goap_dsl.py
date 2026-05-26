"""Tiny safe parser for the action-spec mini-DSL used in
`data/actions/actions.json`.

Preconditions look like:

    "agent.location_uid": "!= target_uid"
    "agent.energy":       ">= 1"
    "item.location_uid":  "== agent.location_uid"

Effects look like:

    "agent.location_uid": "= target_uid"
    "agent.energy":       "-= 1"

Path tokens:
    `agent.<field>`  → executor's own state, key `<field>` in the GOAP state dict
    `target.<field>` → target agent's state, key `target.<field>`
    `item.<field>`   → item state, key `item.<field>`

A right-hand value is one of:
    - a numeric literal (int or float)
    - a quoted string (double or single quotes)
    - the bare token `true` / `false` / `null`
    - a parameter name from the action spec (e.g. `target_uid`) — resolved
      against the planner's `params` dict at compile time
    - another path token (e.g. `agent.location_uid`)

We deliberately use a small hand-written parser to stay eval-free and
exception-clean.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

State = dict[str, Any]


# Recognized comparison / assignment ops. Order matters for prefix matching:
# longer first so `==` doesn't get parsed as `=`.
_COMPARISONS = ("==", "!=", ">=", "<=", ">", "<")
_ASSIGNMENTS = ("+=", "-=", "=")
# `==` outranks `=` for preconditions; for effects we accept `=` as assignment.
_PRE_OPS = ("==", "!=", ">=", "<=", ">", "<", "=")
_EFF_OPS = ("+=", "-=", "=")


@dataclass
class _Path:
    """A path like `agent.energy` or `target.location_uid`."""

    root: str  # 'agent' | 'target' | 'item'
    field: str

    def key(self) -> str:
        # `agent.*` keys are stored bare in the state (e.g. "energy").
        # `target.*` and `item.*` get the full qualified key.
        if self.root == "agent":
            return self.field
        return f"{self.root}.{self.field}"


_PATH_RE = re.compile(r"^(agent|target|item)\.([A-Za-z_][\w\.]*)$")


def _parse_path(token: str) -> _Path | None:
    m = _PATH_RE.match(token.strip())
    if not m:
        return None
    return _Path(root=m.group(1), field=m.group(2))


def _split_op(s: str, ops: tuple[str, ...]) -> tuple[str, str]:
    """Strip leading op from `s`. Returns (op, remainder). Raises if no op."""
    s = s.strip()
    for op in ops:
        if s.startswith(op):
            return op, s[len(op) :].strip()
    raise ValueError(f"no recognized op in {s!r} (allowed: {ops})")


def _coerce_literal(token: str) -> Any:
    """Best-effort literal coercion: int → float → bool/null → string."""
    t = token.strip()
    if not t:
        return ""
    # Quoted string
    if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
        return t[1:-1]
    low = t.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("null", "none"):
        return None
    try:
        return int(t)
    except ValueError:
        pass
    try:
        return float(t)
    except ValueError:
        pass
    return t  # plain string token


def _resolve_rhs(
    rhs: str,
    state: State,
    params: dict[str, Any],
) -> Any:
    """Resolve a right-hand-side token against state + params at runtime."""
    rhs = rhs.strip()
    if not rhs:
        return ""
    # Path on the right (e.g. "agent.location_uid" inside an `==`).
    p = _parse_path(rhs)
    if p is not None:
        return state.get(p.key())
    # Param token.
    if rhs in params:
        return params[rhs]
    return _coerce_literal(rhs)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def compile_precondition(
    lhs: str,
    expr: str,
    params: dict[str, Any],
) -> Callable[[State], bool]:
    """Compile one `"agent.energy": ">= 1"` into a `state -> bool` callable.

    The `params` dict is captured so a precondition like
    `"agent.location_uid": "!= target_uid"` resolves `target_uid` at plan time.
    """
    op, rhs = _split_op(expr, _PRE_OPS)
    path = _parse_path(lhs)
    if path is None:
        raise ValueError(f"precondition lhs is not a path: {lhs!r}")

    def check(state: State) -> bool:
        left = state.get(path.key())
        right = _resolve_rhs(rhs, state, params)
        return _apply_compare(op, left, right)

    return check


def compile_effect(
    lhs: str,
    expr: str,
    params: dict[str, Any],
) -> Callable[[State], State]:
    """Compile one `"agent.energy": "-= 1"` into a `state -> state` callable.

    The transformer returns a NEW dict; the original is not mutated, which is
    important for A* search where we keep parent states alive in the open set.
    """
    op, rhs = _split_op(expr, _EFF_OPS)
    path = _parse_path(lhs)
    if path is None:
        raise ValueError(f"effect lhs is not a path: {lhs!r}")
    key = path.key()

    def transform(state: State) -> State:
        right = _resolve_rhs(rhs, state, params)
        new_state = dict(state)
        if op == "=":
            new_state[key] = right
        elif op == "+=":
            new_state[key] = _safe_add(state.get(key, 0), right)
        elif op == "-=":
            new_state[key] = _safe_add(state.get(key, 0), _safe_neg(right))
        else:  # pragma: no cover
            raise ValueError(f"unknown effect op {op!r}")
        return new_state

    return transform


def compile_predicate(
    preconditions: dict[str, str],
    params: dict[str, Any],
) -> Callable[[State], bool]:
    """AND of all individual precondition checks."""
    checks = [compile_precondition(k, v, params) for k, v in preconditions.items()]
    if not checks:
        return lambda s: True

    def all_ok(state: State) -> bool:
        return all(c(state) for c in checks)

    return all_ok


def compile_transformer(
    effects: dict[str, str],
    params: dict[str, Any],
) -> Callable[[State], State]:
    """Sequential application of all effects."""
    transforms = [compile_effect(k, v, params) for k, v in effects.items()]
    if not transforms:
        return lambda s: dict(s)

    def apply_all(state: State) -> State:
        out = state
        for t in transforms:
            out = t(out)
        return out

    return apply_all


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _apply_compare(op: str, left: Any, right: Any) -> bool:
    if op == "==" or op == "=":
        return left == right
    if op == "!=":
        return left != right
    # numeric comparators — be tolerant: if either side isn't numeric, return False
    try:
        l = float(left) if not isinstance(left, bool) and left is not None else None
        r = float(right) if not isinstance(right, bool) and right is not None else None
    except (TypeError, ValueError):
        return False
    if l is None or r is None:
        return False
    if op == ">=":
        return l >= r
    if op == "<=":
        return l <= r
    if op == ">":
        return l > r
    if op == "<":
        return l < r
    raise ValueError(f"unknown comparison op {op!r}")  # pragma: no cover


def _safe_add(a: Any, b: Any) -> Any:
    try:
        return (a or 0) + (b or 0)
    except TypeError:
        # If the LHS is a string and RHS is numeric, fall through to assign the
        # RHS (rare edge case; effect like `+= 1` on a non-numeric field).
        return b


def _safe_neg(v: Any) -> Any:
    try:
        return -v
    except TypeError:
        return v


__all__ = [
    "State",
    "compile_precondition",
    "compile_effect",
    "compile_predicate",
    "compile_transformer",
]
