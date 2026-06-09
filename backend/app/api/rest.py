"""REST endpoints for world / agents / config inspection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.config.loader import ConfigLoader
from app.config.registry import get_registry
from app.settings import get_settings

router = APIRouter(prefix="/api", tags=["rest"])


# ============================================================
#                        helpers
# ============================================================

def _world(req: Request):
    w = getattr(req.app.state, "world", None)
    if w is None:
        raise HTTPException(status_code=503, detail="world not initialized")
    return w


def _scene(req: Request):
    s = getattr(req.app.state, "scene", None)
    if s is None:
        raise HTTPException(status_code=503, detail="scene not initialized")
    return s


def _agents(req: Request) -> dict[str, Any]:
    return getattr(req.app.state, "agents", None) or {}


def _sim(req: Request):
    s = getattr(req.app.state, "sim", None)
    if s is None:
        raise HTTPException(status_code=503, detail="sim loop not initialized")
    return s


def _db(req: Request):
    return getattr(req.app.state, "db", None)


def _get_agent(req: Request, agent_id: str):
    agent = _agents(req).get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"unknown agent: {agent_id}")
    return agent


def _persona_summary(persona) -> dict[str, Any]:
    """Build a compact summary used by the agents list view."""
    profile = getattr(persona, "profile", None) or {}
    group = profile.get("group_zh") or profile.get("group_en") or persona.role
    name_en = profile.get("name_en")
    summary_parts: list[str] = []
    for k in ("role_zh", "role_en", "innate_zh", "short_goal_zh", "short_goal_en"):
        v = profile.get(k)
        if v:
            summary_parts.append(v)
        if len(summary_parts) >= 2:
            break
    return {
        "id": persona.id,
        "name": persona.name,
        "name_en": name_en,
        "role": persona.role,
        "group": group,
        "profile_summary": " · ".join(summary_parts) or persona.role,
    }


def _persona_to_dict(persona) -> dict[str, Any]:
    if hasattr(persona, "model_dump"):
        return persona.model_dump()
    if hasattr(persona, "to_dict"):
        return persona.to_dict()
    if isinstance(persona, dict):
        return dict(persona)
    return {}


# ============================================================
#                        health
# ============================================================

@router.get("/health")
async def health(req: Request) -> dict[str, Any]:
    world = getattr(req.app.state, "world", None)
    return {
        "status": "ok",
        "sim_time": (world.sim_time.isoformat() if world else None),
        "n_agents": len(_agents(req)),
        "sim_running": bool(getattr(getattr(req.app.state, "sim", None), "is_running", False)),
    }


# ============================================================
#                        scene / world
# ============================================================

@router.get("/scene/graph")
async def get_scene_graph(req: Request) -> dict[str, Any]:
    scene = _scene(req)
    return scene.to_vis_graph()


def _layout_path() -> Path:
    return get_settings().runtime_dir / "scene_layout.json"


@router.get("/scene/layout")
async def get_scene_layout(req: Request) -> dict[str, Any]:
    """User-saved scene-topology layout: room positions + background map
    transform. Persisted to disk so it survives a service restart."""
    p = _layout_path()
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("rooms", {})
                data.setdefault("map", {})
                data.setdefault("obstacles", {})
                data.setdefault("roomAreas", {})
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"rooms": {}, "map": {}, "obstacles": {}, "roomAreas": {}}


@router.put("/scene/layout")
async def put_scene_layout(req: Request) -> dict[str, Any]:
    """Persist the dragged room positions and background-map transform."""
    try:
        body = await req.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid JSON body: {exc}")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="layout body must be an object")
    rooms = body.get("rooms") if isinstance(body.get("rooms"), dict) else {}
    map_cfg = body.get("map") if isinstance(body.get("map"), dict) else {}
    # Non-walkable terrain painted on the topology canvas: an occupancy grid of
    # blocked cell keys ("cx,cy") that NPC pathfinding routes around.
    obstacles = body.get("obstacles") if isinstance(body.get("obstacles"), dict) else {}
    # Per-room painted footprints: cells that belong to each scene node, used to
    # scatter NPCs across the node's actual area instead of orbiting it.
    room_areas = body.get("roomAreas") if isinstance(body.get("roomAreas"), dict) else {}
    doc = {"rooms": rooms, "map": map_cfg, "obstacles": obstacles, "roomAreas": room_areas}
    p = _layout_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "saved", "rooms": len(rooms)}


def _recordings_dir() -> Path:
    return get_settings().runtime_dir / "recordings"


def _safe_recording_path(name: str) -> Path:
    # Only allow plain rec_*.jsonl basenames (no path traversal).
    if "/" in name or "\\" in name or ".." in name or not name.endswith(".jsonl"):
        raise HTTPException(status_code=400, detail="invalid recording name")
    return _recordings_dir() / name


@router.get("/recordings")
async def list_recordings(req: Request) -> dict[str, Any]:
    """List saved playback recordings (newest first)."""
    d = _recordings_dir()
    cur = getattr(req.app.state, "recorder", None)
    cur_name = cur.path.name if cur and getattr(cur, "path", None) else None
    out: list[dict[str, Any]] = []
    if d.exists():
        for p in sorted(d.glob("rec_*.jsonl"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                with p.open("r", encoding="utf-8") as fh:
                    frames = sum(1 for line in fh if '"kind": "frame"' in line or '"kind":"frame"' in line)
            except OSError:
                frames = 0
            out.append({
                "name": p.name,
                "size": p.stat().st_size,
                "mtime": p.stat().st_mtime,
                "frames": frames,
                "is_current": p.name == cur_name,
            })
    return {"recordings": out, "current": cur_name}


@router.get("/recordings/{name}")
async def get_recording(name: str, req: Request) -> dict[str, Any]:
    """Return a full recording: header + every frame (world snapshot + events)."""
    p = _safe_recording_path(name)
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"recording not found: {name}")
    header: dict[str, Any] = {}
    frames: list[dict[str, Any]] = []
    try:
        with p.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("kind") == "header":
                    header = rec
                elif rec.get("kind") == "frame":
                    frames.append(rec)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"read failed: {exc}")
    return {"name": name, "header": header, "frames": frames}


@router.get("/world")
async def get_world_state(req: Request) -> dict[str, Any]:
    return _world(req).snapshot()


# ============================================================
#                        agents
# ============================================================

@router.get("/agents")
async def list_agents(req: Request) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    registry = get_registry()
    world = getattr(req.app.state, "world", None)
    agents = _agents(req)

    # If we have NPCAgent instances, use them; otherwise fall back to registry personas.
    if agents:
        for aid, agent in agents.items():
            persona = agent.persona
            summary = _persona_summary(persona)
            here = (world.agents[aid].location_uid
                    if world and aid in world.agents else None)
            summary["location_uid"] = here
            out.append(summary)
        return out

    for pid, persona in registry.personas.items():
        summary = _persona_summary(persona)
        here = (world.agents[pid].location_uid
                if world and pid in world.agents else persona.initial_location_uid)
        summary["location_uid"] = here
        out.append(summary)
    return out


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str, req: Request) -> dict[str, Any]:
    agents = _agents(req)
    registry = get_registry()
    world = getattr(req.app.state, "world", None)

    if agent_id in agents:
        agent = agents[agent_id]
        persona_dict = agent.persona.to_dict()
        snap = agent.perceiver.perceive(agent_id, world)
        return {
            **persona_dict,
            "location_uid": (world.agents[agent_id].location_uid
                             if world and agent_id in world.agents else None),
            "perception": snap.to_dict(),
        }

    persona = registry.personas.get(agent_id)
    if persona is None:
        raise HTTPException(status_code=404, detail=f"unknown agent: {agent_id}")
    return {
        **_persona_to_dict(persona),
        "location_uid": (world.agents[agent_id].location_uid
                         if world and agent_id in world.agents else persona.initial_location_uid),
        "perception": None,
    }


@router.get("/agents/{agent_id}/memory")
async def get_agent_memory(agent_id: str, req: Request) -> dict[str, Any]:
    agent = _get_agent(req, agent_id)
    return agent.memory_view()


@router.get("/agents/{agent_id}/schedule")
async def get_agent_schedule(
    agent_id: str, req: Request, day: str | None = None, week: bool = False,
) -> dict[str, Any]:
    agent = _get_agent(req, agent_id)
    return agent.schedule_view(day=day, week=week)


@router.get("/agents/{agent_id}/history")
async def get_agent_history(agent_id: str, req: Request, limit: int = 100) -> list[dict[str, Any]]:
    agent = _get_agent(req, agent_id)
    db = _db(req)
    if db is not None:
        try:
            rows = await db.query_behavior(agent_id, limit=limit)
            if rows:
                return rows
        except Exception:
            pass
    return [r.to_dict() for r in agent.behavior_executor.history_for(agent_id, limit=limit)]


@router.get("/agents/{agent_id}/perception")
async def get_agent_perception(agent_id: str, req: Request) -> dict[str, Any]:
    agent = _get_agent(req, agent_id)
    snap = agent.perceiver.perceive(agent_id, _world(req))
    return snap.to_dict()


# ============================================================
#                  auxiliary datasets
# ============================================================

@router.get("/relations")
async def get_relations() -> dict[str, Any]:
    registry = get_registry()
    if registry.relations is None:
        return {"edges": []}
    return registry.relations.model_dump()


@router.get("/scenes-library")
async def get_scenes_library() -> dict[str, Any]:
    registry = get_registry()
    if registry.scenes_library is None:
        return {"scenes": []}
    return registry.scenes_library.model_dump()


@router.get("/timeline-seed")
async def get_timeline_seed() -> dict[str, Any]:
    registry = get_registry()
    if registry.timeline_seed is None:
        return {"events": []}
    return registry.timeline_seed.model_dump()


# ============================================================
#                        config
# ============================================================

@router.get("/config/personas")
async def list_personas() -> list[dict[str, Any]]:
    registry = get_registry()
    return [_persona_to_dict(p) for p in registry.personas.values()]


@router.get("/config/actions")
async def list_actions() -> list[dict[str, Any]]:
    registry = get_registry()
    if registry.actions is None:
        return []
    return [a.model_dump() for a in registry.actions.actions]


@router.get("/config/fragments")
async def list_fragments() -> list[dict[str, Any]]:
    registry = get_registry()
    if registry.fragments is None:
        return []
    return [f.model_dump() for f in registry.fragments.fragments]


@router.post("/config/reload")
async def reload_config(req: Request) -> dict[str, Any]:
    settings = getattr(req.app.state, "settings", None)
    if settings is None:
        raise HTTPException(status_code=503, detail="settings unavailable")
    loader = ConfigLoader(settings.data_dir)
    registry = get_registry()
    registry.scenes = loader.load_scenes()
    registry.personas = loader.load_personas()
    registry.schedule_templates = loader.load_schedule_templates()
    registry.fragments = loader.load_fragments()
    registry.actions = loader.load_actions()
    registry.relations = loader.load_relations()
    registry.scenes_library = loader.load_scenes_library()
    registry.timeline_seed = loader.load_timeline_seed()
    registry.memory_seed = loader.load_memory_seed()
    return {
        "status": "reloaded",
        "scenes": len(registry.scenes),
        "personas": len(registry.personas),
        "templates": len(registry.schedule_templates),
        "fragments": len(registry.fragments.fragments) if registry.fragments else 0,
        "actions": len(registry.actions.actions) if registry.actions else 0,
        "relations": len(registry.relations.edges) if registry.relations else 0,
        "scenes_library": len(registry.scenes_library.scenes) if registry.scenes_library else 0,
        "timeline_seed": len(registry.timeline_seed.events) if registry.timeline_seed else 0,
    }


# ============================================================
#                       sim control
# ============================================================

@router.post("/sim/start")
async def sim_start(req: Request) -> dict[str, Any]:
    sim = _sim(req)
    await sim.start()
    return {"status": "running", "sim_time": _world(req).sim_time.isoformat()}


@router.post("/sim/pause")
async def sim_pause(req: Request) -> dict[str, Any]:
    sim = _sim(req)
    await sim.stop()
    return {"status": "paused", "sim_time": _world(req).sim_time.isoformat()}


@router.post("/sim/step")
async def sim_step(req: Request) -> dict[str, Any]:
    sim = _sim(req)
    await sim.step()
    return {"status": "stepped", "sim_time": _world(req).sim_time.isoformat()}


@router.get("/sim/status")
async def sim_status(req: Request) -> dict[str, Any]:
    sim = _sim(req)
    world = _world(req)
    pause_reason = getattr(sim, "pause_reason", None)
    return {
        "running": bool(getattr(sim, "is_running", False)),
        "sim_time": world.sim_time.isoformat(),
        "pause_reason": pause_reason,
        "current_day": world.sim_time.date().isoformat(),
    }


@router.get("/sim/day_summaries")
async def get_day_summaries(req: Request, limit: int = 30) -> dict[str, Any]:
    """Return the most recent day-summary narratives (one per simulated day)."""
    sim = _sim(req)
    items = list(getattr(sim, "day_summaries", []) or [])
    return {"summaries": items[-max(1, limit):]}


@router.post("/sim/summarize_now")
async def sim_summarize_now(req: Request) -> dict[str, Any]:
    """Force an omniscient-narrator summary of the *current* simulated day.

    Useful when the player wants a recap mid-day instead of waiting for the
    midnight rollover. Does NOT pause the loop or advance the day; it just
    appends one entry to ``sim.day_summaries`` and publishes a `day_summary`
    WS event so the UI's modal pops.
    """
    sim = _sim(req)
    world = _world(req)
    if sim is None:
        return {"status": "error", "reason": "no sim loop"}
    current_day = world.sim_time.date()
    day_iso = current_day.isoformat()
    # Bypass the once-per-rollover guard for manual triggers.
    sim._last_summarised_day = None  # type: ignore[attr-defined]
    # If a summary for the same day already exists (user is re-summarising),
    # drop the old one so the manual version replaces it instead of duplicating.
    sim.day_summaries = [s for s in (sim.day_summaries or [])
                         if s.get("day") != day_iso]
    try:
        await sim._do_day_summary(current_day)  # type: ignore[attr-defined]
    except Exception as exc:
        return {"status": "error", "reason": repr(exc)}
    last = (sim.day_summaries or [{}])[-1] if sim.day_summaries else {}
    return {
        "status": "ok",
        "day": day_iso,
        "summary": last,
    }


@router.get("/sim/week_summaries")
async def get_week_summaries(req: Request, limit: int = 12) -> dict[str, Any]:
    """Return the most recent weekly per-agent space evaluations."""
    sim = _sim(req)
    items = list(getattr(sim, "week_summaries", []) or [])
    return {"summaries": items[-max(1, limit):]}


@router.post("/sim/summarize_week_now")
async def sim_summarize_week_now(req: Request) -> dict[str, Any]:
    """Force a weekly space evaluation for the week ENDING on the current sim
    day (each agent evaluates the space using their full data). Does NOT pause
    the loop; publishes a `week_summary` WS event."""
    sim = _sim(req)
    world = _world(req)
    if sim is None:
        return {"status": "error", "reason": "no sim loop"}
    week_end = world.sim_time.date()
    try:
        await sim._do_week_summary(week_end)  # type: ignore[attr-defined]
    except Exception as exc:
        return {"status": "error", "reason": repr(exc)}
    last = (sim.week_summaries or [{}])[-1] if sim.week_summaries else {}
    return {"status": "ok", "week": last.get("week", ""), "summary": last}


# ============================================================
#              LLM API key (entry-screen gate)
# ============================================================

@router.get("/llm/status")
async def llm_status(req: Request) -> dict[str, Any]:
    """Whether an LLM key is currently active, plus model / base_url.

    Never returns the key itself. The entry screen uses this to decide whether
    to pre-fill the "use existing key" shortcut.
    """
    llm = getattr(req.app.state, "llm", None)
    if llm is not None and hasattr(llm, "status"):
        return llm.status()
    # Mock-only build (no configurable adapter).
    return {"configured": False, "model": None, "base_url": None}


@router.post("/llm/key")
async def set_llm_key(req: Request) -> dict[str, Any]:
    """Set the DeepSeek / OpenAI-compatible API key for THIS run.

    Body: ``{"api_key": "...", "base_url"?: "...", "model"?: "...",
    "validate"?: true}``. The key is held in memory only (never written to
    disk) and applied to the shared client every agent uses. When
    ``validate`` is true (default) a 1-token probe confirms the key works
    before we accept it — a bad key returns HTTP 400 so the UI can show why.
    """
    llm = getattr(req.app.state, "llm", None)
    if llm is None or not hasattr(llm, "configure"):
        raise HTTPException(
            status_code=409,
            detail="LLM adapter is not runtime-configurable in this build",
        )
    try:
        body = await req.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid JSON body: {exc}")

    api_key = str((body or {}).get("api_key", "")).strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key is required")
    base_url = (body or {}).get("base_url") or None
    model = (body or {}).get("model") or None
    do_validate = bool((body or {}).get("validate", True))

    ok, msg = await llm.try_configure(
        api_key=api_key, base_url=base_url, model=model, validate=do_validate,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=f"API key validation failed: {msg}")

    return {"status": "ok", **llm.status()}


# ============================================================
#              heat map / data export / shutdown
# ============================================================

@router.get("/heatmap")
async def get_heatmap(req: Request) -> dict[str, Any]:
    """Whole-run cumulative heat map (move edges + room dwell).

    Keys match the frontend heat store so the client can load it directly:
    `moves` is keyed by undirected edge "a|b" (a<b), `dwell` by room uid.
    """
    sim = _sim(req)
    if not hasattr(sim, "heatmap_view"):
        return {"ticks": 0, "moves": {}, "dwell": {}, "max_move": 0, "max_dwell": 0}
    return sim.heatmap_view()


def _exports_dir() -> Path:
    return get_settings().runtime_dir / "exports"


def _safe_export_path(name: str) -> Path:
    if "/" in name or "\\" in name or ".." in name or not name.endswith(".json"):
        raise HTTPException(status_code=400, detail="invalid export name")
    return _exports_dir() / name


@router.post("/export")
async def export_run_data(req: Request) -> dict[str, Any]:
    """Full-run dump: every NPC's memory (STM/LTM/graph), behaviour history,
    the world snapshot, day summaries, the cumulative heat map and relations.
    Writes runtime/exports/export_*.json and returns its name (the client can
    then GET /api/exports/{name} to also download it locally)."""
    from app.persistence.exporter import build_export, write_export

    data = await build_export(req.app.state)
    path = write_export(get_settings().runtime_dir, data)
    return {
        "status": "ok",
        "filename": path.name,
        "size": path.stat().st_size,
        "n_agents": data.get("n_agents", 0),
        "sim_time": data.get("sim_time"),
    }


@router.get("/exports")
async def list_exports() -> dict[str, Any]:
    d = _exports_dir()
    out: list[dict[str, Any]] = []
    if d.exists():
        for p in sorted(d.glob("export_*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            out.append({"name": p.name, "size": p.stat().st_size, "mtime": p.stat().st_mtime})
    return {"exports": out}


@router.get("/exports/{name}")
async def download_export(name: str) -> FileResponse:
    """Download a saved export as a JSON attachment."""
    p = _safe_export_path(name)
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"export not found: {name}")
    return FileResponse(
        p, media_type="application/json", filename=name,
    )


def _validate_export_doc(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("kind") != "sigsagent_export":
        raise HTTPException(
            status_code=400,
            detail="not a SIGSAgent export document (expected kind=sigsagent_export)",
        )
    return data


async def _apply_import(req: Request, data: dict[str, Any]) -> dict[str, Any]:
    """Pause the sim (so restore doesn't race a live tick), then restore."""
    from app.persistence.importer import apply_import

    sim = getattr(req.app.state, "sim", None)
    if sim is not None:
        try:
            await sim.stop()
        except Exception:  # noqa: BLE001
            pass
    summary = await apply_import(req.app.state, data)
    return {"status": "ok", "running": False, **summary}


@router.post("/import")
async def import_run_data(req: Request) -> dict[str, Any]:
    """Restore a run from an uploaded export document so the sim can continue.

    Body is the JSON produced by ``POST /api/export`` / the "Save data" button.
    Repopulates world (positions/stats/items + sim_time), every NPC's memory
    (STM/LTM/graph), behaviour history, the cumulative heat map and day
    summaries. The loop is left **paused** — resume via ``POST /api/sim/start``.
    """
    try:
        data = await req.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid JSON body: {exc}")
    _validate_export_doc(data)
    return await _apply_import(req, data)


@router.post("/import/by-name/{name}")
async def import_run_by_name(name: str, req: Request) -> dict[str, Any]:
    """Restore a run from a server-side export file (one listed by GET /exports).

    Lighter than uploading: the client just names a file already kept in
    ``runtime/exports/``. Same restore + leave-paused semantics as /import.
    """
    import json as _json

    p = _safe_export_path(name)
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"export not found: {name}")
    try:
        data = _json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"failed to read export {name}: {exc}")
    _validate_export_doc(data)
    out = await _apply_import(req, data)
    out["source"] = name
    return out


@router.post("/service/shutdown")
async def shutdown_service(req: Request) -> dict[str, Any]:
    """Auto-save the full run, then gracefully stop the backend process.

    Saves first (memory is otherwise RAM-only), stops the sim loop, closes the
    recorder + DB, and schedules process exit shortly after the response is
    flushed. The service must be restarted afterwards.
    """
    import asyncio
    import os

    from app.persistence.exporter import build_export, write_export

    state = req.app.state
    export_name: str | None = None
    try:
        data = await build_export(state)
        path = write_export(get_settings().runtime_dir, data)
        export_name = path.name
    except Exception as exc:  # noqa: BLE001
        # Don't block shutdown on a save failure, but report it.
        export_name = f"(save failed: {exc!r})"

    # Best-effort graceful teardown of the moving parts before we exit.
    sim = getattr(state, "sim", None)
    if sim is not None:
        try:
            await sim.stop()
        except Exception:  # noqa: BLE001
            pass
    recorder = getattr(state, "recorder", None)
    if recorder is not None:
        try:
            recorder.close()
        except Exception:  # noqa: BLE001
            pass
    db = getattr(state, "db", None)
    if db is not None:
        try:
            close = getattr(db, "close", None)
            if close is not None:
                res = close()
                if asyncio.iscoroutine(res):
                    await res
        except Exception:  # noqa: BLE001
            pass

    # Exit shortly after this response is sent (cross-platform hard stop; the
    # teardown above already did what the lifespan would).
    def _bye() -> None:
        os._exit(0)

    loop = asyncio.get_event_loop()
    loop.call_later(0.7, _bye)
    return {"status": "shutting_down", "export": export_name}
