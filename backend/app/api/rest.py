"""REST endpoints for world / agents / config inspection.

Placeholders return shape-only payloads so the frontend can be developed
against a stable contract before the simulation core is implemented.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api", tags=["rest"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------- Scene / World ----------

@router.get("/scene/graph")
async def get_scene_graph() -> dict[str, Any]:
    """Return rooms + adjacent edges for the topology view."""
    raise HTTPException(status_code=501, detail="Not implemented: scene_graph.load()")


@router.get("/world")
async def get_world_state() -> dict[str, Any]:
    """Snapshot of the live WorldState (agents + items positions/status)."""
    raise HTTPException(status_code=501, detail="Not implemented: world_state.snapshot()")


# ---------- Agents ----------

@router.get("/agents")
async def list_agents() -> list[dict[str, Any]]:
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str) -> dict[str, Any]:
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/agents/{agent_id}/memory")
async def get_agent_memory(agent_id: str) -> dict[str, Any]:
    """Returns {short_term: [...], long_term: [...], graph: {...}}."""
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/agents/{agent_id}/schedule")
async def get_agent_schedule(agent_id: str, day: str | None = None) -> dict[str, Any]:
    """5min timeline with template items + filled fragments."""
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/agents/{agent_id}/history")
async def get_agent_history(agent_id: str, limit: int = 100) -> list[dict[str, Any]]:
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/agents/{agent_id}/perception")
async def get_agent_perception(agent_id: str) -> dict[str, Any]:
    raise HTTPException(status_code=501, detail="Not implemented")


# ---------- Config ----------

@router.get("/config/personas")
async def list_personas() -> list[dict[str, Any]]:
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/config/actions")
async def list_actions() -> list[dict[str, Any]]:
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/config/fragments")
async def list_fragments() -> list[dict[str, Any]]:
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/config/reload")
async def reload_config() -> dict[str, str]:
    """Hot-reload data/ json files via config.loader."""
    raise HTTPException(status_code=501, detail="Not implemented")


# ---------- Sim control ----------

@router.post("/sim/start")
async def sim_start() -> dict[str, str]:
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/sim/pause")
async def sim_pause() -> dict[str, str]:
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/sim/step")
async def sim_step() -> dict[str, str]:
    raise HTTPException(status_code=501, detail="Not implemented")
