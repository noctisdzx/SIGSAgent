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
from app.llm.adapter import (  # noqa: E402
    LLMAdapter,
    MockLLMAdapter,
    build_narrate_day_messages,
    parse_narrate_day_response,
)
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
                         "content": "你是一个记忆压缩器。把多条短期记忆压缩成一段中文摘要"
                                    "（保留时间、地点、人物、情绪关键点），"
                                    "再额外给出一段对应的英文摘要。"
                                    "严格 JSON 输出: {\"zh\":\"…\", \"en\":\"…\"}。"},
                        {"role": "user", "content": "\n".join(f"- {t}" for t in texts)},
                    ],
                    temperature=0.3,
                    max_tokens=800,
                    response_format={"type": "json_object"},
                )
                raw = resp["choices"][0]["message"]["content"].strip()
                # Pack as a special two-line string the compressor will split.
                import json as _json
                try:
                    data = _json.loads(raw)
                    zh = str(data.get("zh", "")).strip()
                    en = str(data.get("en", "")).strip()
                    if zh or en:
                        return f"{zh}\u241F{en}"  # unit-separator joins zh + en
                except Exception:
                    pass
                return raw
            except Exception:
                return await self._mock.summarize_memories(texts)

        async def choose_fragment(self, gap_minutes, persona, memories, candidates, context=None):
            try:
                ctx = context or {}
                ctx_line = (
                    f"sim_time={ctx.get('sim_time','?')} room={ctx.get('here_uid','?')} "
                    f"visible_agents={ctx.get('visible_agents', [])} "
                    f"last_activity={ctx.get('last_activity','?')}"
                )
                # Build the candidate id allow-list so we can recover from
                # noisy LLM output (returns text around the id, or wraps it
                # in quotes / brackets).
                valid_ids = [c.get("id") for c in candidates if c.get("id")]
                resp = await client.chat(
                    messages=[
                        {"role": "system",
                         "content": "你为一个校园NPC选择填补空闲时间的活动。"
                                    "返回 JSON: {\"id\":\"<候选id>\", \"rationale\":\"<≤30字>\"}。"
                                    "id 必须严格出现在候选列表中。"
                                    "如果当前房间有其他NPC且候选含social标签，请优先选社交向片段。"},
                        {"role": "user", "content":
                            f"persona={persona.get('name')} prefs={persona.get('preferences')}\n"
                            f"context={ctx_line}\n"
                            f"memories={memories}\n"
                            f"candidates={candidates}\n"
                            f"gap_minutes={gap_minutes}"},
                    ],
                    temperature=0.4,
                    max_tokens=300,
                    response_format={"type": "json_object"},
                )
                content = resp["choices"][0]["message"]["content"].strip()
                import json as _json
                try:
                    data = _json.loads(content)
                    pick = str(data.get("id", "")).strip()
                    rationale = str(data.get("rationale", "")).strip() or "llm pick"
                except Exception:
                    pick = content
                    rationale = "llm pick"
                if pick not in valid_ids:
                    # final mile salvage: find any valid id present in the text.
                    pick = next((v for v in valid_ids if v in content), "") or pick
                if pick not in valid_ids:
                    raise ValueError(f"choose_fragment: invalid id {pick!r}")
                return pick, rationale
            except Exception:
                return await self._mock.choose_fragment(
                    gap_minutes, persona, memories, candidates, context=context,
                )

        async def extract_triplets(self, agent_id, events):
            try:
                resp = await client.chat(
                    messages=[
                        {"role": "system",
                         "content": "把每个事件抽成 {subject,predicate,object}, 严格 JSON 数组返回。"},
                        {"role": "user", "content": f"agent={agent_id} events={events}"},
                    ],
                    temperature=0.0,
                    max_tokens=900,
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

        async def generate_dialog(self, speaker, listener, speaker_memories, situation):
            """Generate one short bilingual dialog between two NPCs.

            Returns {speaker_line, listener_line, speaker_line_en, listener_line_en,
            topic, topic_en, tone}. Falls back to the mock adapter on any
            network/parse failure.
            """
            try:
                sys_msg = (
                    "你是校园模拟器的对话编剧。"
                    "为两位 NPC 写一轮自然口语化的对话；同时输出中文和英文两个版本。"
                    "严格 JSON 输出: "
                    "{\"speaker_line\":\"<中文>\", \"listener_line\":\"<中文>\", "
                    "\"speaker_line_en\":\"<English>\", \"listener_line_en\":\"<English>\", "
                    "\"topic\":\"<中文 3-7 字>\", \"topic_en\":\"<English 1-4 words>\", "
                    "\"tone\":\"friendly|neutral|tense|playful|curious\"}。"
                    "每条中文 ≤35 汉字，英文 ≤25 words；不要寒暄套话；"
                    "如果说话人最近记忆里有相关线索请自然体现。"
                )
                user_msg = (
                    f"speaker={speaker.get('name')}({speaker.get('role','')}) "
                    f"traits={speaker.get('personality', {})}\n"
                    f"listener={listener.get('name')}({listener.get('role','')})\n"
                    f"sim_time={situation.get('sim_time')} weekday={situation.get('weekday')}\n"
                    f"room={situation.get('here_name')} ({situation.get('here_uid')})\n"
                    f"current_activity={situation.get('current_activity')}\n"
                    f"speaker_memories={speaker_memories}"
                )
                resp = await client.chat(
                    messages=[
                        {"role": "system", "content": sys_msg},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=0.7,
                    max_tokens=800,
                    response_format={"type": "json_object"},
                )
                content = resp["choices"][0]["message"]["content"]
                import json as _json
                data = _json.loads(content)
                return {
                    "speaker_line": str(data.get("speaker_line", "")).strip() or "（无内容）",
                    "listener_line": str(data.get("listener_line", "")).strip() or "（无回应）",
                    "speaker_line_en": str(data.get("speaker_line_en", "")).strip() or "(empty)",
                    "listener_line_en": str(data.get("listener_line_en", "")).strip() or "(no reply)",
                    "topic": str(data.get("topic", "")).strip() or "杂谈",
                    "topic_en": str(data.get("topic_en", "")).strip() or "chat",
                    "tone": str(data.get("tone", "neutral")).strip() or "neutral",
                }
            except Exception:
                return await self._mock.generate_dialog(
                    speaker, listener, speaker_memories, situation,
                )

        async def choose_dialog_target(self, speaker, candidates, situation):
            """Pick WHO (if anyone) the speaker talks to right now.

            Returns ``(target_id | None, rationale)``. **This method must exist
            on the real adapter** — without it the dialog channel's
            ``choose_dialog_target`` call raises AttributeError, gets swallowed,
            and every NPC silently "stays silent" forever (the no-dialog bug).
            Falls back to the mock chooser on any network/parse failure.
            """
            if not candidates:
                return None, "no candidates"
            valid_ids = [c.get("id") for c in candidates if c.get("id")]
            try:
                sys_msg = (
                    "你在为校园模拟里的一位 NPC 决定此刻是否要找人搭话、以及找谁。"
                    "从候选里挑一个最自然的对象；若此刻更适合专注或独处，可选择不说话。"
                    "严格 JSON 输出: {\"id\":\"<候选id 或 null>\", \"rationale\":\"<≤20字>\"}。"
                    "id 必须严格是候选之一，或 null 表示不说话。"
                    "倾向于：很久没说过话(minutes_since_last_talk 大或为 null)、"
                    "与当前活动相关、外向性格更主动。"
                )
                user_msg = (
                    f"speaker={speaker.get('name')}({speaker.get('role','')}) "
                    f"traits={speaker.get('personality', {})}\n"
                    f"sim_time={situation.get('sim_time')} "
                    f"room={situation.get('here_name')} "
                    f"activity={situation.get('current_activity')}\n"
                    f"candidates={candidates}"
                )
                resp = await client.chat(
                    messages=[
                        {"role": "system", "content": sys_msg},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=0.5,
                    max_tokens=200,
                    response_format={"type": "json_object"},
                )
                content = resp["choices"][0]["message"]["content"].strip()
                import json as _json
                data = _json.loads(content)
                tid = data.get("id")
                rationale = str(data.get("rationale", "")).strip() or "llm pick"
                if tid in (None, "", "none", "null", "None"):
                    return None, rationale
                tid = str(tid).strip()
                if tid not in valid_ids:
                    # salvage: an id may be embedded in noisy text
                    tid = next((v for v in valid_ids if v and v in content), "")
                if not tid or tid not in valid_ids:
                    return None, "no valid target"
                return tid, rationale
            except Exception:
                return await self._mock.choose_dialog_target(
                    speaker, candidates, situation,
                )

        async def generate_mutter(self, speaker, situation, memories):
            """Generate one short inner-monologue line (the dialog channel's
            `Mutter` state). Returns {line, line_en, mood}. Falls back to mock
            on any failure (also missing before — would break muttering under a
            real key)."""
            try:
                sys_msg = (
                    "你为一位校园 NPC 写一句简短的内心独白（自言自语）。"
                    "结合当前时间、地点、活动与最近记忆，写得自然、有个性、口语化。"
                    "严格 JSON 输出: {\"line\":\"<中文 ≤30字>\", "
                    "\"line_en\":\"<English ≤20 words>\", \"mood\":\"<一个情绪词>\"}。"
                )
                user_msg = (
                    f"speaker={speaker.get('name')}({speaker.get('role','')}) "
                    f"traits={speaker.get('personality', {})}\n"
                    f"sim_time={situation.get('sim_time')} weekday={situation.get('weekday')} "
                    f"room={situation.get('here_name')} "
                    f"activity={situation.get('current_activity')} "
                    f"body_action={situation.get('body_action')}\n"
                    f"memories={memories}"
                )
                resp = await client.chat(
                    messages=[
                        {"role": "system", "content": sys_msg},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=0.8,
                    max_tokens=200,
                    response_format={"type": "json_object"},
                )
                content = resp["choices"][0]["message"]["content"]
                import json as _json
                data = _json.loads(content)
                return {
                    "line": str(data.get("line", "")).strip() or "……",
                    "line_en": str(data.get("line_en", "")).strip() or "...",
                    "mood": str(data.get("mood", "neutral")).strip() or "neutral",
                }
            except Exception:
                return await self._mock.generate_mutter(speaker, situation, memories)

        async def describe_activity(self, persona, activity, situation):
            """Rewrite a raw fragment/schedule label into a short, in-character,
            scene-aware description for THIS npc. Returns
            {description_zh, description_en}. Falls back to mock on any failure.
            """
            try:
                sys_msg = (
                    "你把一个通用的日程活动标签，改写成这位校园 NPC 此刻“正在做什么”的"
                    "一句具体描述，要贴合其人格特征与所在场景。"
                    "中文 ≤30 字、英文 ≤20 词，现在进行时，自然口语、有画面感；"
                    "不要照抄原始标签，不要出现 id 或系统术语。"
                    "严格 JSON 输出: {\"description_zh\":\"<中文一句>\", "
                    "\"description_en\":\"<English sentence>\"}。"
                )
                user_msg = (
                    f"npc={persona.get('name')}({persona.get('role','')}) "
                    f"traits={persona.get('personality', {})} "
                    f"prefs={persona.get('preferences', {})}\n"
                    f"raw_activity={activity!r}\n"
                    f"place={situation.get('here_name')} ({situation.get('here_uid')})\n"
                    f"time={situation.get('sim_time')} weekday={situation.get('weekday')}"
                )
                resp = await client.chat(
                    messages=[
                        {"role": "system", "content": sys_msg},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=0.6,
                    max_tokens=200,
                    response_format={"type": "json_object"},
                )
                content = resp["choices"][0]["message"]["content"]
                import json as _json
                data = _json.loads(content)
                zh = str(data.get("description_zh", "")).strip()
                en = str(data.get("description_en", "")).strip()
                if not zh:
                    raise ValueError("empty description_zh")
                return {"description_zh": zh, "description_en": en or zh}
            except Exception:
                return await self._mock.describe_activity(persona, activity, situation)

        async def narrate_day(self, day, bullets, stats):
            """Literary short-story recap of a finished sim day.

            Uses the shared `build_narrate_day_messages` so the prompt stays
            in sync with `DeepSeekAdapter.narrate_day`. Returns the full rich
            payload (title / protagonist / supporting / story_zh / story_en /
            tomorrow_*) with a synopsis (`zh`/`en`) auto-derived from the
            story for backward compatibility.
            """
            try:
                messages = build_narrate_day_messages(day, bullets, stats)
                resp = await client.chat(
                    messages=messages,
                    temperature=0.85,
                    max_tokens=8000,
                    response_format={"type": "json_object"},
                )
                content = resp["choices"][0]["message"]["content"]
                import json as _json
                data = _json.loads(content)
                if not isinstance(data, dict):
                    raise ValueError(
                        f"narrate_day: expected object, got {type(data).__name__}"
                    )
                return parse_narrate_day_response(data)
            except Exception as exc:
                log.warning("narrate_day LLM call failed, falling back: %s", exc)
                return await self._mock.narrate_day(day, bullets, stats)

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
    if scene:
        # Seed movable items (chairs, books, mugs…) from each room's furniture
        # so the topology graph has things NPCs can pick up & carry around.
        world.populate_items_from_rooms(scene.all_rooms())
        log.info("Seeded %d movable items from room furniture", len(world.items))

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

    # Insert-event library (optional; produced by scripts/build_insert_events.py).
    insert_event_lib = None
    try:
        from app.agents.schedule.insert_events import InsertEventLibrary
        ie_path = settings.data_dir / "insert_events" / "insert_events.json"
        if ie_path.exists():
            insert_event_lib = InsertEventLibrary.from_json(ie_path)
            log.info("Loaded %d insert events", len(insert_event_lib.all()))
    except Exception as exc:
        log.warning("failed to load insert events: %s", exc)

    behavior_executor = BehaviorExecutor(action_lib, db=db) if action_lib else None

    # 6) Sim loop (started on demand by /api/sim/start, or auto).
    sim = SimLoop(world, scene) if scene else None
    recorder = None
    if sim is not None:
        sim.set_llm(llm)  # so SimLoop can call narrate_day on midnight rollover
        # Playback recorder: tap the event bus + write one frame per tick.
        from app.events.bus import event_bus as _bus
        from app.sim.recorder import Recorder
        recorder = Recorder(settings.runtime_dir / "recordings", enabled=settings.sim_record)
        if settings.sim_record:
            _bus.add_tap(recorder.tap)
            recorder.start_session(meta={
                "sim_start": world.sim_time.isoformat(),
                "n_personas": len(registry.personas),
            })
            sim.set_recorder(recorder)

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
                    insert_event_lib=insert_event_lib,
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
    app.state.recorder = recorder
    # Allow NPCAgents to find each other (used by the dialog pipeline).
    try:
        from app.agents.agent import NPCAgent as _NPCAgent
        _NPCAgent.set_registry(agents)
    except Exception as _exc:
        log.warning("failed to publish NPCAgent registry: %s", _exc)

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
        if recorder is not None:
            recorder.close()
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
