"""Full-run data export.

Gathers *everything* a run produced — per-NPC memory (STM / LTM / memory graph),
behaviour history, the live world snapshot, day-summary narratives, the
cumulative heat map and the relation graph — into one JSON document, and writes
it to ``runtime/exports/export_YYYYMMDD_HHMMSS.json``.

This is intentionally a point-in-time dump (memory is otherwise in-RAM only and
would be lost on shutdown), driven by the "Save data" button / the graceful
"Stop service" flow.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("sigs.exporter")

# Per-agent behaviour rows to include. Generous but bounded so a long run
# doesn't produce an unmanageable file.
_HISTORY_LIMIT = 2000


async def _agent_history(state: Any, agent_id: str, agent: Any) -> list[dict[str, Any]]:
    db = getattr(state, "db", None)
    if db is not None:
        try:
            rows = await db.query_behavior(agent_id, limit=_HISTORY_LIMIT)
            if rows:
                return rows
        except Exception as exc:  # noqa: BLE001
            log.debug("export: db history failed for %s: %s", agent_id, exc)
    # Fall back to the in-memory executor history.
    ex = getattr(agent, "behavior_executor", None)
    if ex is not None:
        try:
            return [r.to_dict() for r in ex.history_for(agent_id, limit=_HISTORY_LIMIT)]
        except Exception:  # noqa: BLE001
            return []
    return []


async def build_export(state: Any) -> dict[str, Any]:
    """Assemble the full-run export document from ``app.state``."""
    world = getattr(state, "world", None)
    sim = getattr(state, "sim", None)
    agents: dict[str, Any] = getattr(state, "agents", {}) or {}

    world_snapshot = world.snapshot() if world is not None else {}
    sim_time = world_snapshot.get("sim_time") if isinstance(world_snapshot, dict) else None

    agents_out: list[dict[str, Any]] = []
    for aid, agent in agents.items():
        entry: dict[str, Any] = {"id": aid}
        try:
            entry["persona"] = agent.persona.to_dict()
        except Exception:  # noqa: BLE001
            entry["persona"] = {"id": aid}
        try:
            entry["memory"] = agent.memory_view()
        except Exception as exc:  # noqa: BLE001
            log.debug("export: memory_view failed for %s: %s", aid, exc)
            entry["memory"] = {"short_term": [], "long_term": [], "graph": []}
        entry["behavior_history"] = await _agent_history(state, aid, agent)
        agents_out.append(entry)

    # Relations (seed graph + any runtime tone, from the config registry).
    relations: list[dict[str, Any]] = []
    try:
        from app.config.registry import get_registry

        reg = get_registry()
        if reg.relations and getattr(reg.relations, "edges", None):
            for e in reg.relations.edges:
                relations.append(e.model_dump() if hasattr(e, "model_dump") else dict(e))
    except Exception as exc:  # noqa: BLE001
        log.debug("export: relations failed: %s", exc)

    day_summaries = list(getattr(sim, "day_summaries", []) or []) if sim else []
    heatmap = sim.heatmap_view() if sim and hasattr(sim, "heatmap_view") else {}

    return {
        "kind": "sigsagent_export",
        "version": 1,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "sim_time": sim_time,
        "n_agents": len(agents_out),
        "world": world_snapshot,
        "agents": agents_out,
        "day_summaries": day_summaries,
        "heatmap": heatmap,
        "relations": relations,
    }


def write_export(runtime_dir: Path, data: dict[str, Any]) -> Path:
    """Write the export doc to runtime/exports/ and return the file path."""
    out_dir = Path(runtime_dir) / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"export_{stamp}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("wrote full-run export -> %s (%d agents)", path, data.get("n_agents", 0))
    return path
