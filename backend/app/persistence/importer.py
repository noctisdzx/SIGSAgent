"""Restore a previously exported run so the simulation can continue.

The inverse of :func:`app.persistence.exporter.build_export`: given an export
document, repopulate the live :class:`WorldState` (agent positions + stats +
items + ``sim_time``), each ``NPCAgent``'s memory (STM / LTM / memory graph),
the shared behaviour history, and the :class:`SimLoop`'s cumulative heat map +
day summaries. This is what powers the "load save / continue simulation"
button (``POST /api/import`` and ``POST /api/import/by-name/{name}``).

The sim must be paused while this runs — the REST layer stops the loop first
— because restore mutates shared structures (world, memory, heat) that a live
tick would otherwise race against.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

log = logging.getLogger("sigs.importer")


def _parse_ts(raw: Any) -> datetime:
    if isinstance(raw, datetime):
        return raw
    try:
        return datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return datetime.utcnow()


def _restore_world(world: Any, world_doc: dict[str, Any]) -> dict[str, int]:
    """Re-seed sim_time + every agent's room/stats + item placements."""
    from app.world.world_state import AgentState, ItemState

    restored = {"agents": 0, "items": 0}
    if not isinstance(world_doc, dict):
        return restored

    st = world_doc.get("sim_time")
    if st:
        try:
            world.sim_time = datetime.fromisoformat(str(st))
        except (TypeError, ValueError):
            log.warning("import: bad world sim_time %r", st)

    for aid, a in (world_doc.get("agents") or {}).items():
        if not isinstance(a, dict):
            continue
        loc = a.get("location_uid")
        if not loc:
            continue
        existing = world.agents.get(aid)
        if existing is None:
            existing = AgentState(id=str(aid), location_uid=str(loc))
            world.agents[str(aid)] = existing
        existing.location_uid = str(loc)
        for fld in ("energy", "hunger", "money", "mood", "holding"):
            if fld in a:
                setattr(existing, fld, a[fld])
        if isinstance(a.get("extra"), dict):
            existing.extra = dict(a["extra"])
        restored["agents"] += 1

    for iid, it in (world_doc.get("items") or {}).items():
        if not isinstance(it, dict):
            continue
        loc = it.get("location_uid")
        if not loc:
            continue
        existing = world.items.get(iid)
        if existing is None:
            existing = ItemState(id=str(iid), location_uid=str(loc))
            world.items[str(iid)] = existing
        existing.location_uid = str(loc)
        if "status" in it:
            existing.status = it["status"]
        if isinstance(it.get("extra"), dict):
            existing.extra = dict(it["extra"])
        restored["items"] += 1

    return restored


def _restore_memory(agent: Any, mem: dict[str, Any]) -> dict[str, int]:
    """Reload STM / LTM / memory-graph for one agent from its export entry."""
    from app.agents.memory.long_term import LongTermItem
    from app.agents.memory.memory_graph import Triplet
    from app.agents.memory.short_term import ShortTermItem

    counts = {"stm": 0, "ltm": 0, "graph": 0}
    if not isinstance(mem, dict):
        return counts

    stm_items: list[ShortTermItem] = []
    for d in mem.get("short_term") or []:
        if not isinstance(d, dict):
            continue
        stm_items.append(ShortTermItem(
            id=str(d.get("id", "")),
            text=str(d.get("text", "")),
            ts=_parse_ts(d.get("ts")),
            source=str(d.get("source", "")),
            hit_count=int(d.get("hit_count", 0) or 0),
            meta=dict(d.get("meta") or {}),
            text_en=d.get("text_en"),
        ))
    if stm_items and hasattr(agent, "stm"):
        agent.stm.load(stm_items)
        counts["stm"] = len(stm_items)

    ltm_items: list[LongTermItem] = []
    for d in mem.get("long_term") or []:
        if not isinstance(d, dict):
            continue
        ltm_items.append(LongTermItem(
            id=str(d.get("id", "")),
            text=str(d.get("text", "")),
            ts=_parse_ts(d.get("ts")),
            source_ids=list(d.get("source_ids") or []),
            hit_count=int(d.get("hit_count", 0) or 0),
            degraded=bool(d.get("degraded", False)),
            text_en=d.get("text_en"),
            meta=dict(d.get("meta") or {}),
        ))
    if ltm_items and hasattr(agent, "ltm"):
        agent.ltm.load(ltm_items)
        counts["ltm"] = len(ltm_items)

    triplets: list[Triplet] = []
    for d in mem.get("graph") or []:
        if not isinstance(d, dict):
            continue
        triplets.append(Triplet(
            id=str(d.get("id", "")),
            subject=str(d.get("subject", "")),
            predicate=str(d.get("predicate", "")),
            obj=str(d.get("object", d.get("obj", ""))),
            ts=_parse_ts(d.get("ts")),
            location_uid=d.get("location_uid"),
            tone=d.get("tone"),
            meta=dict(d.get("meta") or {}),
        ))
    if triplets and hasattr(agent, "mem_graph"):
        agent.mem_graph.load(triplets)
        counts["graph"] = len(triplets)

    return counts


def _restore_behavior(agent: Any, agent_id: str, rows: list[dict[str, Any]]) -> int:
    """Reload an agent's behaviour history into the shared executor (in-memory).

    Only repopulates the runtime history list used by day-summaries / the UI;
    rows already persisted in ``memory.db`` are left untouched.
    """
    from app.agents.behavior.executor import ExecutedAction

    ex = getattr(agent, "behavior_executor", None)
    if ex is None or not isinstance(rows, list) or not agent_id:
        return 0
    recs: list[ExecutedAction] = []
    for d in rows:
        if not isinstance(d, dict):
            continue
        params = d.get("params")
        if not isinstance(params, dict):
            params = {"_raw": params} if params is not None else {}
        recs.append(ExecutedAction(
            ts=_parse_ts(d.get("ts")),
            agent_id=str(d.get("agent_id", agent_id)),
            action_id=str(d.get("action_id", "")),
            params=params,
            ok=bool(d.get("ok", True)),
            note=str(d.get("note", "")),
        ))
    recs.sort(key=lambda r: r.ts)
    ex.history[str(agent_id)] = recs
    return len(recs)


async def apply_import(state: Any, data: dict[str, Any]) -> dict[str, Any]:
    """Restore the run described by ``data`` into the live ``app.state``.

    Returns a small summary of what was restored. The caller (REST layer) is
    responsible for having paused the sim loop first.
    """
    world = getattr(state, "world", None)
    sim = getattr(state, "sim", None)
    agents: dict[str, Any] = getattr(state, "agents", {}) or {}

    world_restored = (
        _restore_world(world, data.get("world") or {})
        if world is not None else {"agents": 0, "items": 0}
    )

    mem_agents = 0
    missing_agents: list[str] = []
    stm_total = ltm_total = graph_total = behavior_total = 0
    for entry in data.get("agents") or []:
        if not isinstance(entry, dict):
            continue
        aid = str(entry.get("id", ""))
        agent = agents.get(aid)
        if agent is None:
            if aid:
                missing_agents.append(aid)
            continue
        c = _restore_memory(agent, entry.get("memory") or {})
        stm_total += c["stm"]
        ltm_total += c["ltm"]
        graph_total += c["graph"]
        behavior_total += _restore_behavior(agent, aid, entry.get("behavior_history") or [])
        mem_agents += 1

    heat_restored = False
    if sim is not None and hasattr(sim, "load_state"):
        hm = data.get("heatmap")
        ds = data.get("day_summaries")
        sim.load_state(
            heatmap=hm if isinstance(hm, dict) else None,
            day_summaries=ds if isinstance(ds, list) else None,
        )
        heat_restored = isinstance(hm, dict)

    summary = {
        "exported_at": data.get("exported_at"),
        "sim_time": world.sim_time.isoformat() if world is not None else None,
        "world_agents": world_restored["agents"],
        "world_items": world_restored["items"],
        "memory_agents": mem_agents,
        "missing_agents": len(missing_agents),
        "stm_items": stm_total,
        "ltm_items": ltm_total,
        "graph_triplets": graph_total,
        "behavior_rows": behavior_total,
        "heatmap_restored": heat_restored,
        "day_summaries": len(data.get("day_summaries") or []),
    }
    log.info("import applied: %s", summary)
    if missing_agents:
        log.warning(
            "import: %d exported agents not present in this run (skipped): %s%s",
            len(missing_agents), missing_agents[:5],
            " …" if len(missing_agents) > 5 else "",
        )
    return summary
