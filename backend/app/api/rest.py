"""REST endpoints for world / agents / config inspection."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.config.loader import ConfigLoader
from app.config.registry import get_registry

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
async def get_agent_schedule(agent_id: str, req: Request, day: str | None = None) -> dict[str, Any]:
    agent = _get_agent(req, agent_id)
    return agent.schedule_view(day=day)


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
