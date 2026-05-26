"""FastAPI entrypoint.

Lifespan:
    startup → load all config from data/ → init scene graph + WorldState
            → init DB → optionally autostart sim loop
    shutdown → stop sim loop → close DB
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load repo-root .env (works both when launched from backend/ and from repo root).
for candidate in (Path(__file__).resolve().parents[2] / ".env",
                  Path(__file__).resolve().parents[1] / ".env"):
    if candidate.exists():
        load_dotenv(candidate, override=False)
        break

from app import __version__  # noqa: E402
from app.api import rest_router, ws_router
from app.config.loader import ConfigLoader
from app.config.registry import get_registry
from app.persistence.db import Database
from app.settings import get_settings
from app.sim.loop import SimLoop
from app.world.scene_graph import SceneGraph
from app.world.world_state import WorldState


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("sigs.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    log.info("Booting SIGSAgent backend v%s", __version__)
    log.info("DATA_DIR    = %s", settings.data_dir)
    log.info("RUNTIME_DIR = %s", settings.runtime_dir)

    # 1) Load configs into the registry.
    loader = ConfigLoader(settings.data_dir)
    registry = get_registry()
    registry.scenes = loader.load_scenes()
    registry.personas = loader.load_personas()
    registry.schedule_templates = loader.load_schedule_templates()
    registry.fragments = loader.load_fragments()
    registry.actions = loader.load_actions()
    log.info(
        "Loaded: %d scenes, %d personas, %d templates, %s fragments, %s actions",
        len(registry.scenes), len(registry.personas), len(registry.schedule_templates),
        len(registry.fragments.fragments) if registry.fragments else 0,
        len(registry.actions.actions) if registry.actions else 0,
    )

    # 2) Build scene graph & world state (using the first loaded scene file).
    scene: SceneGraph | None = None
    if registry.scenes:
        first_scene_path = next((settings.data_dir / "scenes").glob("*.json"))
        scene = SceneGraph.from_json(first_scene_path)
    world = WorldState()

    # 3) Init runtime DB.
    db = Database(settings.db_path)
    await db.initialize()

    # 4) Sim loop (started on demand by /api/sim/start, or auto).
    sim = SimLoop(world, scene) if scene else None

    # Attach to app.state for routers/handlers to access.
    app.state.settings = settings
    app.state.scene = scene
    app.state.world = world
    app.state.sim = sim
    app.state.db = db

    if sim and settings.sim_autostart:
        await sim.start()
        log.info("Sim loop autostarted")

    try:
        yield
    finally:
        if sim:
            await sim.stop()
        log.info("Backend shutdown complete")


app = FastAPI(
    title="SIGSAgent Backend",
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rest_router)
app.include_router(ws_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": "SIGSAgent Backend", "version": __version__}
