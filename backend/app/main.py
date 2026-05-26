"""FastAPI entrypoint.

Lifespan:
    startup → load all config from data/ → init scene graph + WorldState
            → build NPCAgents → init DB → optionally autostart sim loop
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
from app.agents.agent import NPCAgent, PersonaConfig, template_from_schema  # noqa: E402
from app.agents.behavior.action_specs import ActionSpecLibrary  # noqa: E402
from app.agents.behavior.executor import BehaviorExecutor  # noqa: E402
from app.agents.schedule.fragments import Fragment, FragmentLibrary  # noqa: E402
from app.api import rest_router, ws_router  # noqa: E402
from app.config.loader import ConfigLoader  # noqa: E402
from app.config.registry import get_registry  # noqa: E402
from app.llm.adapter import LLMAdapter, MockLLMAdapter  # noqa: E402
from app.llm.client import OpenAICompatibleClient  # noqa: E402
from app.persistence.db import Database  # noqa: E402
from app.settings import get_settings  # noqa: E402
from app.sim.loop import SimLoop  # noqa: E402
from app.world.scene_graph import SceneGraph  # noqa: E402
from app.world.world_state import WorldState  # noqa: E402


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("sigs.main")


PLACEHOLDER_KEY_PREFIX = "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"


def _make_llm_adapter() -> tuple[LLMAdapter, bool]:
    """Return (adapter, is_real)."""
    s = get_settings()
    key = (s.llm_api_key or "").strip()
    if not key or key.startswith(PLACEHOLDER_KEY_PREFIX[:10]):
        return MockLLMAdapter(), False

    client = OpenAICompatibleClient()

    class _Adapter:
        """Thin LLMAdapter facade backed by an OpenAI-compatible client.

        We keep the real call surface narrow on purpose: only the three
        Protocol methods. Each call falls back to MockLLMAdapter on failure
        (so even if the network goes away mid-run we still degrade gracefully
        rather than throwing).
        """

        def __init__(self) -> None:
            self._mock = MockLLMAdapter()

        async def summarize_memories(self, texts: list[str]) -> str:
            try:
                resp = await client.chat(
                    messages=[
                        {"role": "system",
                         "content": "你是一个简洁的记忆压缩器，把多条短期记忆压成一句中文。"},
                        {"role": "user", "content": "\n".join(f"- {t}" for t in texts)},
                    ],
                    temperature=0.3,
                    max_tokens=200,
                )
                return resp["choices"][0]["message"]["content"].strip()
            except Exception:
                return await self._mock.summarize_memories(texts)

        async def choose_fragment(self, gap_minutes, persona, memories, candidates):
            try:
                resp = await client.chat(
                    messages=[
                        {"role": "system",
                         "content": "你为一个校园NPC选择填补空闲时间的活动。只返回候选id字符串。"},
                        {"role": "user", "content":
                            f"persona={persona.get('name')} prefs={persona.get('preferences')}\n"
                            f"memories={memories}\n"
                            f"candidates={candidates}\n"
                            f"gap_minutes={gap_minutes}"},
                    ],
                    temperature=0.4,
                    max_tokens=60,
                )
                pick = resp["choices"][0]["message"]["content"].strip()
                return pick, "llm pick"
            except Exception:
                return await self._mock.choose_fragment(gap_minutes, persona, memories, candidates)

        async def extract_triplets(self, agent_id, events):
            try:
                resp = await client.chat(
                    messages=[
                        {"role": "system",
                         "content": "把每个事件抽成 {subject,predicate,object}, 严格 JSON 数组返回。"},
                        {"role": "user", "content": f"agent={agent_id} events={events}"},
                    ],
                    temperature=0.0,
                    max_tokens=400,
                    response_format={"type": "json_object"},
                )
                content = resp["choices"][0]["message"]["content"]
                import json as _json
                parsed = _json.loads(content)
                if isinstance(parsed, dict) and "triplets" in parsed:
                    return parsed["triplets"]
                if isinstance(parsed, list):
                    return parsed
                raise ValueError("unexpected shape")
            except Exception:
                return await self._mock.extract_triplets(agent_id, events)

    return _Adapter(), True


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
    registry.relations = loader.load_relations()
    registry.scenes_library = loader.load_scenes_library()
    registry.timeline_seed = loader.load_timeline_seed()
    registry.memory_seed = loader.load_memory_seed()
    log.info(
        "Loaded: %d scenes, %d personas, %d templates, %s fragments, %s actions, "
        "%s relation edges, %s scenes library, %s timeline events",
        len(registry.scenes), len(registry.personas), len(registry.schedule_templates),
        len(registry.fragments.fragments) if registry.fragments else 0,
        len(registry.actions.actions) if registry.actions else 0,
        len(registry.relations.edges) if registry.relations else 0,
        len(registry.scenes_library.scenes) if registry.scenes_library else 0,
        len(registry.timeline_seed.events) if registry.timeline_seed else 0,
    )

    # 2) Scene graph & world state.
    scene: SceneGraph | None = None
    scenes_dir = settings.data_dir / "scenes"
    if scenes_dir.exists():
        for p in scenes_dir.glob("*.json"):
            scene = SceneGraph.from_json(p)
            break
    world = WorldState()
    if registry.personas:
        world.populate_from_personas(registry.personas)

    # 3) Runtime DB.
    db = Database(settings.db_path)
    await db.initialize()

    # 4) LLM adapter (real or mock).
    llm, real = _make_llm_adapter()
    log.info("LLM adapter: %s", "real (OpenAI-compatible)" if real else "MockLLMAdapter")

    # 5) Action / fragment libraries.
    action_lib: ActionSpecLibrary | None = None
    if registry.actions:
        action_lib = ActionSpecLibrary.from_list(
            [a.model_dump() for a in registry.actions.actions]
        )

    fragment_lib: FragmentLibrary | None = None
    if registry.fragments:
        fragments = [Fragment(
            id=f.id, label=f.label, duration_minutes=f.duration_minutes,
            tags=list(f.tags), preferred_location_uids=list(f.preferred_location_uids),
            cost=f.cost, preconditions=dict(f.preconditions),
        ) for f in registry.fragments.fragments]
        fragment_lib = FragmentLibrary(fragments)

    behavior_executor = BehaviorExecutor(action_lib, db=db) if action_lib else None

    # 6) Sim loop (started on demand by /api/sim/start, or auto).
    sim = SimLoop(world, scene) if scene else None

    # 7) Build NPCAgents.
    agents: dict[str, NPCAgent] = {}
    if scene and action_lib and fragment_lib:
        for pid, pschema in registry.personas.items():
            try:
                persona = PersonaConfig.from_schema(pschema)
                tpl_schema = registry.schedule_templates.get(persona.schedule_template_id)
                template = template_from_schema(tpl_schema) if tpl_schema else None
                seed = (registry.memory_seed.per_agent.get(pid)
                        if registry.memory_seed else None)
                agent = NPCAgent(
                    persona=persona,
                    scene=scene,
                    world=world,
                    llm=llm,
                    action_lib=action_lib,
                    fragment_lib=fragment_lib,
                    template=template,
                    memory_seed=seed,
                    behavior_executor=behavior_executor,
                )
                agents[pid] = agent
                if sim:
                    sim.register_agent(pid, agent)
            except Exception as exc:
                log.warning("failed to build agent %s: %s", pid, exc)
        log.info("Constructed %d NPCAgents", len(agents))

    # Attach to app.state for routers/handlers to access.
    app.state.settings = settings
    app.state.scene = scene
    app.state.world = world
    app.state.sim = sim
    app.state.db = db
    app.state.llm = llm
    app.state.action_lib = action_lib
    app.state.fragment_lib = fragment_lib
    app.state.agents = agents

    if sim and settings.sim_autostart:
        await sim.start()
        log.info("Sim loop autostarted")

    print(
        "SIGSAgent ready @ http://127.0.0.1:8000  | docs: /docs | ws: /ws "
        f"| sim_autostart={settings.sim_autostart}",
        flush=True,
    )

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
