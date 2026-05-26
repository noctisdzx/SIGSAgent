"""NPCAgent aggregator.

Each NPC owns a perception view, a memory bundle, a decision pipeline,
and a behavior executor. The sim loop calls `perceive_decide_act(world)`
once per tick.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

from app.agents.behavior.action_specs import ActionSpecLibrary
from app.agents.behavior.executor import BehaviorExecutor
from app.agents.decision.goap_planner import GoapPlanner
from app.agents.decision.slot_filler import SlotFiller
from app.agents.memory.compressor import MemoryCompressor
from app.agents.memory.long_term import LongTermItem, LongTermMemory
from app.agents.memory.memory_graph import MemoryGraph, Triplet

# Social activity markers (substring match on activity_text) that trigger
# the LLM-driven dialog pipeline when at least one other NPC is co-located.
SOCIAL_HINTS = (
    "chat", "social", "聊", "搭话", "串门", "聚", "讨论", "约",
    "discussion", "group_discussion", "approach", "talk",
)
from app.agents.memory.retriever import MemoryRetriever
from app.agents.memory.short_term import ShortTermItem, ShortTermMemory
from app.agents.perception.perceiver import Perceiver, PerceptionSnapshot
from app.agents.schedule.builder import schedule_item_to_stm
from app.agents.schedule.fragments import FragmentLibrary
from app.agents.schedule.template import ScheduleTemplate, TemplateBlock
from app.agents.schedule.timeline import DailyTimeline, SLOT_MINUTES, SLOTS_PER_DAY, Slot, SlotKind
from app.events.bus import event_bus
from app.llm.adapter import LLMAdapter

if TYPE_CHECKING:
    from app.world.scene_graph import SceneGraph
    from app.world.world_state import WorldState


log = logging.getLogger("sigs.agent")


WEEKDAY_NAMES = [
    "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday",
]


@dataclass
class PersonaConfig:
    id: str
    name: str
    role: str
    personality: dict[str, float]
    preferences: dict[str, Any]
    relations: dict[str, Any]
    initial_location_uid: str
    schedule_template_id: str
    profile: dict[str, Any] | None = None

    @classmethod
    def from_schema(cls, p: Any) -> "PersonaConfig":
        if isinstance(p, dict):
            return cls(
                id=p["id"], name=p["name"], role=p["role"],
                personality=dict(p.get("personality", {})),
                preferences=dict(p.get("preferences", {})),
                relations=dict(p.get("relations", {})),
                initial_location_uid=p["initial_location_uid"],
                schedule_template_id=p["schedule_template_id"],
                profile=dict(p.get("profile", {})) if p.get("profile") else None,
            )
        return cls(
            id=p.id, name=p.name, role=p.role,
            personality=dict(p.personality),
            preferences=dict(p.preferences),
            relations=dict(p.relations),
            initial_location_uid=p.initial_location_uid,
            schedule_template_id=p.schedule_template_id,
            profile=dict(getattr(p, "profile", {}) or {}) or None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "personality": dict(self.personality),
            "preferences": dict(self.preferences),
            "relations": dict(self.relations),
            "initial_location_uid": self.initial_location_uid,
            "schedule_template_id": self.schedule_template_id,
            "profile": dict(self.profile) if self.profile else {},
        }


class NPCAgent:
    """Orchestrates perception, memory, schedule, decision, behavior for one NPC."""

    # Class-level lookup so an agent can find its dialog partner without each
    # NPCAgent carrying a reference to every other NPCAgent. main.py populates
    # this once all agents are constructed.
    _registry: dict[str, "NPCAgent"] = {}

    @classmethod
    def set_registry(cls, agents: dict[str, "NPCAgent"]) -> None:
        cls._registry = dict(agents)

    def __init__(
        self,
        persona: PersonaConfig,
        scene: "SceneGraph",
        world: "WorldState",
        llm: LLMAdapter,
        action_lib: ActionSpecLibrary,
        fragment_lib: FragmentLibrary,
        template: ScheduleTemplate | None,
        memory_seed: dict | None = None,
        behavior_executor: BehaviorExecutor | None = None,
    ) -> None:
        self.persona = persona
        self.scene = scene
        self.world = world
        self.llm = llm

        # Memory bundle
        self.stm = ShortTermMemory(capacity=30)
        self.ltm = LongTermMemory(capacity=15)
        self.mem_graph = MemoryGraph()
        self.retriever = MemoryRetriever(self.stm, self.ltm)
        self.compressor = MemoryCompressor(self.stm, self.ltm, llm)

        # Schedule
        self.template: ScheduleTemplate | None = template
        self.fragment_lib = fragment_lib
        self.timeline: DailyTimeline = DailyTimeline(world.sim_time.date())
        self._timeline_day: date = world.sim_time.date()
        self._apply_template_to_timeline()

        # Decision
        self.slot_filler = SlotFiller(fragment_lib, llm)
        self.goap_planner = GoapPlanner(action_lib.to_goap_actions())

        # Behavior + perception
        self.behavior_executor = behavior_executor or BehaviorExecutor(action_lib)
        self.perceiver = Perceiver(scene)

        if memory_seed:
            self._seed_memory(memory_seed)

    # ------------------------------------------------------------------
    #                  seeding helpers
    # ------------------------------------------------------------------

    def _seed_memory(self, seed: Any) -> None:
        """Seed STM / mem_graph from a `memory_seed[npc_id]` entry."""
        # The seed may be a pydantic model or a plain dict.
        memories = []
        triplets = []
        if seed is None:
            return
        if hasattr(seed, "memories"):
            memories = list(seed.memories or [])
            triplets = list(seed.triplets or [])
        elif isinstance(seed, dict):
            memories = list(seed.get("memories", []))
            triplets = list(seed.get("triplets", []))

        now = self.world.sim_time
        for i, m in enumerate(memories):
            text = getattr(m, "text", None) if not isinstance(m, dict) else m.get("text")
            if text is None:
                continue
            item = ShortTermItem(
                id=f"seed_{self.persona.id}_{i}_{uuid.uuid4().hex[:6]}",
                text=text,
                ts=now,
                source="seed",
                meta={"tone": getattr(m, "tone", None) if not isinstance(m, dict) else m.get("tone")},
            )
            self.stm.add(item)

        for i, t in enumerate(triplets):
            if isinstance(t, dict):
                subj, pred, obj = t.get("subject"), t.get("predicate"), t.get("object")
            else:
                subj, pred, obj = getattr(t, "subject", None), getattr(t, "predicate", None), getattr(t, "object", None)
            if not (subj and pred and obj):
                continue
            self.mem_graph.add(Triplet(
                id=f"seed_tri_{self.persona.id}_{i}",
                subject=subj, predicate=pred, obj=obj,
                ts=now,
            ))

        # Also lift any narrative scaffolding into LTM so retrieval has long-term context.
        if memories:
            self.ltm.add(LongTermItem(
                id=f"ltm_seed_{self.persona.id}",
                text="背景记忆：" + " | ".join(
                    (m.text if not isinstance(m, dict) else m.get("text", ""))[:40]
                    for m in memories[:3]
                ),
                ts=now,
                source_ids=[],
                degraded=False,
                meta={"seed": True},
            ))

    # ------------------------------------------------------------------
    #                  schedule helpers
    # ------------------------------------------------------------------

    def _weekday_name(self) -> str:
        return WEEKDAY_NAMES[self.world.sim_time.weekday()]

    def _ensure_timeline_for_today(self) -> None:
        today = self.world.sim_time.date()
        if today == self._timeline_day:
            return
        self.timeline = DailyTimeline(today)
        self._timeline_day = today
        self._apply_template_to_timeline()

    def _apply_template_to_timeline(self) -> None:
        if self.template is None:
            return
        blocks = self.template.blocks_for(self._weekday_name())
        for b in blocks:
            try:
                a_h, a_m = (int(x) for x in b.start.split(":"))
                e_h, e_m = (int(x) for x in b.end.split(":"))
            except (ValueError, AttributeError):
                continue
            from_idx = (a_h * 60 + a_m) // SLOT_MINUTES
            to_idx = (e_h * 60 + e_m) // SLOT_MINUTES
            from_idx = max(0, min(SLOTS_PER_DAY, from_idx))
            to_idx = max(from_idx, min(SLOTS_PER_DAY, to_idx))
            if to_idx <= from_idx:
                continue
            self.timeline.set_template(
                from_idx, to_idx,
                activity=b.activity,
                location_uid=b.location_uid,
                source_id=f"tpl:{self.template.id}:{b.start}-{b.end}",
                target_state=getattr(b, "target_state", None) or {},
            )

    def _current_slot(self) -> Slot:
        t = self.world.sim_time
        idx = (t.hour * 60 + t.minute) // SLOT_MINUTES
        idx = max(0, min(SLOTS_PER_DAY - 1, idx))
        return self.timeline.slots[idx]

    # ------------------------------------------------------------------
    #                  main tick
    # ------------------------------------------------------------------

    async def perceive_decide_act(self, world: "WorldState", scene: "SceneGraph") -> None:
        try:
            self._ensure_timeline_for_today()

            # 1) Perceive (side effect captured below in the decision event).
            snap: PerceptionSnapshot = self.perceiver.perceive(self.persona.id, world)
            visible_agents = sorted({
                a
                for room in (snap.children + snap.siblings + snap.adjacent_fallback)
                for a in room.agents
            } - {self.persona.id})

            # 2) Pick / fill current slot
            slot = self._current_slot()
            if slot.kind == SlotKind.EMPTY:
                await self._fill_current_gap()
                slot = self._current_slot()

            activity_text = slot.activity or "idle"

            # 3) STM entry for current slot
            if slot.kind != SlotKind.EMPTY:
                stm_item = schedule_item_to_stm(slot, self.persona.id, now=world.sim_time)
                if self.stm.add(stm_item):
                    try:
                        await self.compressor.maybe_compress(now=world.sim_time)
                    except Exception as exc:
                        log.warning("compression failed for %s: %s", self.persona.id, exc)

            # 4) Retrieve memories
            memories = self.retriever.retrieve(query=activity_text, top_k=5)

            # 5) Plan with GOAP
            agent_state = world.agents.get(self.persona.id)
            init_state: dict[str, Any] = {}
            if agent_state is not None:
                init_state = {
                    "agent.location_uid": agent_state.location_uid,
                    "agent.energy": agent_state.energy,
                    "agent.hunger": agent_state.hunger,
                    "agent.money": agent_state.money,
                    "agent.mood": agent_state.mood,
                }

            goal: dict[str, Any] = {}
            if slot.location_uid:
                goal["agent.location_uid"] = slot.location_uid
            # Template-authored goal (may carry comparator strings like ">=3").
            # Overrides the bare location goal so a richer goal wins when present.
            tpl_goal = getattr(slot, "target_state", None) or {}
            if tpl_goal:
                goal.update(tpl_goal)

            plan = None
            try:
                if goal:
                    plan = self.goap_planner.plan(init_state, goal)
            except Exception as exc:
                log.debug("planner failure for %s: %s", self.persona.id, exc)
                plan = None

            chosen_step = None
            chosen_params: dict[str, Any] = {}
            if plan:
                chosen_step = plan[0]
                if chosen_step.action_id == "move":
                    chosen_params = {"target_uid": slot.location_uid}
            else:
                # No-plan fallback: move if needed, else idle.
                if slot.location_uid and agent_state and agent_state.location_uid != slot.location_uid:
                    from app.agents.decision.goap_planner import PlanStep
                    chosen_step = PlanStep(action_id="move", label="move (fallback)",
                                            cost=1, duration_minutes=SLOT_MINUTES)
                    chosen_params = {"target_uid": slot.location_uid}
                else:
                    from app.agents.decision.goap_planner import PlanStep
                    chosen_step = PlanStep(action_id="idle", label="idle (fallback)",
                                            cost=1, duration_minutes=SLOT_MINUTES)

            # 6) Emit decision event
            await event_bus.publish({
                "type": "agent_decision",
                "ts_sim": world.sim_time.isoformat(),
                "agent_id": self.persona.id,
                "payload": {
                    "activity": activity_text,
                    "slot_kind": slot.kind.value,
                    "location_uid": slot.location_uid,
                    "plan": [
                        {"action_id": s.action_id, "label": s.label, "cost": s.cost}
                        for s in (plan or [])
                    ],
                    "step": (
                        {"action_id": chosen_step.action_id,
                         "label": chosen_step.label,
                         "params": chosen_params}
                        if chosen_step else None
                    ),
                    "memories": [
                        {"text": m.text, "tier": m.tier, "score": m.score}
                        for m in memories
                    ],
                    "visible_agents": visible_agents,
                    "here_uid": snap.here_uid,
                },
            })

            # 6b) If this is a social-style activity AND someone is in the same
            #     room, run one LLM-driven dialog turn before/around the GOAP
            #     step. Writes to both NPCs' STM + memory_graph and broadcasts
            #     a WS `dialog` event so the UI can render it.
            try:
                await self._maybe_have_dialog(slot, snap, visible_agents, world)
            except Exception as exc:
                log.warning("dialog pipeline failed for %s: %s", self.persona.id, exc)

            # 7) Execute step + write a result-flavoured STM so future decisions
            #    can see what just happened (success/failure + reason + state).
            if chosen_step is not None:
                # snapshot state BEFORE execution so we can show the delta
                pre_state = dict(init_state)
                pre_loc = pre_state.get("agent.location_uid")

                result = await self.behavior_executor.execute(
                    self.persona.id, chosen_step.action_id, chosen_params, world,
                )

                post_agent = world.agents.get(self.persona.id)
                post_loc = post_agent.location_uid if post_agent else None

                # Build the result STM (one per executed step, tagged sim_time).
                hhmm = world.sim_time.strftime("%H:%M")
                if result.ok:
                    if chosen_step.action_id == "move" and pre_loc and post_loc and pre_loc != post_loc:
                        text = f"[{hhmm}] OK move {pre_loc}→{post_loc}（{activity_text}）"
                        text_en = f"[{hhmm}] OK move {pre_loc}->{post_loc} ({activity_text})"
                    else:
                        text = f"[{hhmm}] OK {chosen_step.action_id}（{activity_text}）"
                        text_en = f"[{hhmm}] OK {chosen_step.action_id} ({activity_text})"
                else:
                    text = (
                        f"[{hhmm}] FAIL {chosen_step.action_id}"
                        f"({chosen_params}) — {result.note or 'no detail'}"
                    )
                    text_en = (
                        f"[{hhmm}] FAIL {chosen_step.action_id}"
                        f"({chosen_params}) - {result.note or 'no detail'}"
                    )
                result_stm = ShortTermItem(
                    id=f"stm_act_{uuid.uuid4().hex[:8]}",
                    text=text,
                    text_en=text_en,
                    ts=world.sim_time,
                    source=f"behavior:{chosen_step.action_id}",
                    meta={
                        "agent_id": self.persona.id,
                        "action_id": chosen_step.action_id,
                        "params": dict(chosen_params),
                        "ok": bool(result.ok),
                        "note": result.note,
                        "pre_state": pre_state,
                        "post_state": {
                            "agent.location_uid": post_loc,
                            "agent.energy": getattr(post_agent, "energy", None),
                            "agent.hunger": getattr(post_agent, "hunger", None),
                            "agent.mood": getattr(post_agent, "mood", None),
                        },
                        "activity": activity_text,
                        "slot_location_uid": slot.location_uid,
                    },
                )
                if self.stm.add(result_stm):
                    try:
                        await self.compressor.maybe_compress(now=world.sim_time)
                    except Exception as exc:
                        log.warning("compression failed for %s: %s", self.persona.id, exc)

                await event_bus.publish({
                    "type": "behavior",
                    "ts_sim": world.sim_time.isoformat(),
                    "agent_id": self.persona.id,
                    "payload": {
                        **result.to_dict(),
                        "pre_state": pre_state,
                        "post_state": result_stm.meta["post_state"],
                        "activity": activity_text,
                    },
                })

        except Exception as exc:  # never crash the loop
            log.exception("agent %s tick failed: %s", self.persona.id, exc)
            await event_bus.publish({
                "type": "agent_error",
                "ts_sim": self.world.sim_time.isoformat(),
                "agent_id": self.persona.id,
                "payload": {"error": repr(exc)},
            })

    # ------------------------------------------------------------------

    async def _fill_current_gap(self) -> None:
        t = self.world.sim_time
        cur_idx = (t.hour * 60 + t.minute) // SLOT_MINUTES
        # find contiguous EMPTY span enclosing cur_idx
        lo, hi = cur_idx, cur_idx + 1
        while lo > 0 and self.timeline.slots[lo - 1].kind == SlotKind.EMPTY:
            lo -= 1
        while hi < SLOTS_PER_DAY and self.timeline.slots[hi].kind == SlotKind.EMPTY:
            hi += 1
        gap_minutes = (hi - lo) * SLOT_MINUTES

        # gather decision context from perception + recent memory + neighbour slot
        agent_state = self.world.agents.get(self.persona.id)
        here_uid = agent_state.location_uid if agent_state else None
        try:
            snap = self.perceiver.perceive(self.persona.id, self.world)
            visible_agents = sorted({
                a
                for room in (snap.children + snap.siblings + snap.adjacent_fallback)
                for a in room.agents
            } - {self.persona.id})
            visible_items: list[str] = sorted({
                item
                for room in (snap.children + snap.siblings + snap.adjacent_fallback)
                for item in (room.items or [])
            })
        except Exception:
            snap = None
            visible_agents = []
            visible_items = []

        last_activity = None
        if lo - 1 >= 0:
            last_activity = self.timeline.slots[lo - 1].activity

        ctx = {
            "sim_time": self.world.sim_time.isoformat(timespec="minutes"),
            "weekday": self._weekday_name(),
            "here_uid": here_uid,
            "visible_agents": visible_agents,
            "visible_items": visible_items[:10],
            "last_activity": last_activity,
        }
        # query terms make the retriever surface relevant memories.
        query_parts = [last_activity or "", "free time"] + visible_agents[:3]
        query = " ".join(p for p in query_parts if p)

        try:
            choice = await self.slot_filler.fill(
                gap_minutes=gap_minutes,
                persona=self.persona.to_dict(),
                memories=self.retriever.retrieve(query=query or "free time", top_k=5),
                context=ctx,
            )
        except Exception as exc:
            log.debug("slot fill failed for %s: %s", self.persona.id, exc)
            choice = None

        if choice is None:
            return

        frag = choice.fragment
        loc = (frag.preferred_location_uids[0] if frag.preferred_location_uids
               else (self.world.agents[self.persona.id].location_uid
                     if self.persona.id in self.world.agents else None))
        # only fill the slots covered by the fragment's nominal duration
        slot_span = max(1, frag.duration_minutes // SLOT_MINUTES)
        end_idx = min(SLOTS_PER_DAY, cur_idx + slot_span)
        self.timeline.set_fragment(
            cur_idx, end_idx,
            activity=frag.label,
            location_uid=loc,
            fragment_id=frag.id,
        )

    # ------------------------------------------------------------------
    #                  dialog pipeline
    # ------------------------------------------------------------------

    def _is_social_activity(self, activity: str | None) -> bool:
        if not activity:
            return False
        low = activity.lower()
        return any(h in low for h in SOCIAL_HINTS)

    async def _maybe_have_dialog(
        self,
        slot: Slot,
        snap: PerceptionSnapshot,
        visible_agents: list[str],
        world: "WorldState",
    ) -> None:
        """If this tick is a social-style slot AND someone is in the same room,
        ask the LLM for one short dialog and persist both sides.

        Only fires when a real co-located agent exists (snap.here_uid agents),
        so the `talk` precondition (target.location_uid == agent.location_uid)
        is guaranteed to hold.
        """
        if not self._is_social_activity(slot.activity):
            return
        if not visible_agents:
            return

        # The here_uid room from perception is authoritative for co-location.
        here_room = next(
            (r for r in (snap.children + snap.siblings + snap.adjacent_fallback)
             if r.uid == snap.here_uid),
            None,
        )
        if here_room is None:
            # Look at WorldState directly as a fallback.
            colocated = sorted({
                aid for aid, st in world.agents.items()
                if aid != self.persona.id and st.location_uid == snap.here_uid
            })
        else:
            colocated = sorted(set(here_room.agents) - {self.persona.id})
        if not colocated:
            return

        target_id = colocated[0]
        listener = self._registry.get(target_id)
        if listener is None:
            return

        situation = {
            "sim_time": world.sim_time.isoformat(timespec="minutes"),
            "weekday": self._weekday_name(),
            "here_uid": snap.here_uid,
            "here_name": snap.here_name,
            "current_activity": slot.activity,
        }
        speaker_dict = self.persona.to_dict()
        listener_dict = listener.persona.to_dict()
        speaker_mems = [m.text for m in self.retriever.retrieve(
            query=f"{listener.persona.name} {slot.activity or ''}", top_k=3,
        )]

        try:
            dialog = await self.llm.generate_dialog(
                speaker=speaker_dict,
                listener=listener_dict,
                speaker_memories=speaker_mems,
                situation=situation,
            )
        except Exception as exc:
            log.warning("generate_dialog failed for %s->%s: %s",
                        self.persona.id, target_id, exc)
            return
        log.info("dialog %s -> %s : %s (%s)",
                 self.persona.id, target_id,
                 dialog.get("speaker_line", "")[:30], dialog.get("topic"))

        hhmm = world.sim_time.strftime("%H:%M")
        topic = dialog.get("topic", "杂谈")
        topic_en = dialog.get("topic_en", "chat")
        tone = dialog.get("tone", "neutral")
        speaker_line = dialog.get("speaker_line", "")
        listener_line = dialog.get("listener_line", "")
        speaker_line_en = dialog.get("speaker_line_en", speaker_line)
        listener_line_en = dialog.get("listener_line_en", listener_line)
        speaker_name = self.persona.name
        listener_name = listener.persona.name
        speaker_name_en = getattr(self.persona, "name_en", None) or speaker_name
        listener_name_en = getattr(listener.persona, "name_en", None) or listener_name

        # Run the GOAP `talk` action so the world records it + applies effects.
        try:
            await self.behavior_executor.execute(
                self.persona.id, "talk", {"target_agent_id": target_id}, world,
            )
        except Exception as exc:
            log.debug("talk action exec failed: %s", exc)

        # Build paired STMs (bilingual).
        speaker_stm = ShortTermItem(
            id=f"stm_dlg_{uuid.uuid4().hex[:8]}",
            text=f"[{hhmm}] 我对{listener_name}说：{speaker_line}（TA答：{listener_line}）",
            text_en=f"[{hhmm}] I said to {listener_name_en}: \"{speaker_line_en}\" (reply: \"{listener_line_en}\")",
            ts=world.sim_time,
            source=f"dialog:{target_id}",
            meta={
                "agent_id": self.persona.id,
                "role": "speaker",
                "partner_id": target_id,
                "partner_name": listener_name,
                "partner_name_en": listener_name_en,
                "topic": topic,
                "topic_en": topic_en,
                "tone": tone,
                "here_uid": snap.here_uid,
                "line": speaker_line,
                "line_en": speaker_line_en,
                "reply": listener_line,
                "reply_en": listener_line_en,
            },
        )
        listener_stm = ShortTermItem(
            id=f"stm_dlg_{uuid.uuid4().hex[:8]}",
            text=f"[{hhmm}] {speaker_name}对我说：{speaker_line}（我答：{listener_line}）",
            text_en=f"[{hhmm}] {speaker_name_en} said to me: \"{speaker_line_en}\" (I replied: \"{listener_line_en}\")",
            ts=world.sim_time,
            source=f"dialog:{self.persona.id}",
            meta={
                "agent_id": target_id,
                "role": "listener",
                "partner_id": self.persona.id,
                "partner_name": speaker_name,
                "partner_name_en": speaker_name_en,
                "topic": topic,
                "topic_en": topic_en,
                "tone": tone,
                "here_uid": snap.here_uid,
                "line": speaker_line,
                "line_en": speaker_line_en,
                "reply": listener_line,
                "reply_en": listener_line_en,
            },
        )
        if self.stm.add(speaker_stm):
            try:
                await self.compressor.maybe_compress(now=world.sim_time)
            except Exception:
                pass
        if listener.stm.add(listener_stm):
            try:
                await listener.compressor.maybe_compress(now=world.sim_time)
            except Exception:
                pass

        # Memory-graph triplets for both sides (narrative ledger).
        triplet_speaker = Triplet(
            id=f"trp_dlg_{uuid.uuid4().hex[:8]}",
            subject=self.persona.id,
            predicate=f"said_to({topic})",
            obj=target_id,
            ts=world.sim_time,
            location_uid=snap.here_uid,
            tone=tone,
            meta={"line": speaker_line, "reply": listener_line},
        )
        self.mem_graph.add(triplet_speaker)
        listener.mem_graph.add(Triplet(
            id=f"trp_dlg_{uuid.uuid4().hex[:8]}",
            subject=target_id,
            predicate=f"heard_from({topic})",
            obj=self.persona.id,
            ts=world.sim_time,
            location_uid=snap.here_uid,
            tone=tone,
            meta={"line": speaker_line, "reply": listener_line},
        ))

        # Broadcast a dedicated WS event so the UI can render dialog bubbles.
        await event_bus.publish({
            "type": "dialog",
            "ts_sim": world.sim_time.isoformat(),
            "agent_id": self.persona.id,
            "payload": {
                "speaker_id": self.persona.id,
                "speaker_name": speaker_name,
                "speaker_name_en": speaker_name_en,
                "listener_id": target_id,
                "listener_name": listener_name,
                "listener_name_en": listener_name_en,
                "here_uid": snap.here_uid,
                "topic": topic,
                "topic_en": topic_en,
                "tone": tone,
                "speaker_line": speaker_line,
                "speaker_line_en": speaker_line_en,
                "listener_line": listener_line,
                "listener_line_en": listener_line_en,
            },
        })

    # ------------------------------------------------------------------
    #                  introspection helpers (for REST)
    # ------------------------------------------------------------------

    def memory_view(self) -> dict[str, Any]:
        return {
            "short_term": [
                {
                    "id": it.id, "text": it.text,
                    "text_en": getattr(it, "text_en", None),
                    "ts": it.ts.isoformat(),
                    "source": it.source, "hit_count": it.hit_count, "meta": it.meta,
                }
                for it in self.stm.all()
            ],
            "long_term": [
                {
                    "id": it.id, "text": it.text,
                    "text_en": getattr(it, "text_en", None),
                    "ts": it.ts.isoformat(),
                    "source_ids": it.source_ids, "hit_count": it.hit_count,
                    "degraded": it.degraded,
                    "meta": getattr(it, "meta", {}),
                }
                for it in self.ltm.all()
            ],
            "graph": [
                {
                    "id": t.id, "subject": t.subject, "predicate": t.predicate,
                    "object": t.obj, "ts": t.ts.isoformat(),
                    "location_uid": t.location_uid, "tone": t.tone, "meta": t.meta,
                }
                for t in self.mem_graph.all()
            ],
        }

    def schedule_view(self, day: str | None = None) -> dict[str, Any]:
        # We currently keep a single in-memory timeline (today). Future:
        # multi-day cache. `day` selects the weekday template if not today.
        if day is None:
            tl = self.timeline
            day_name = tl.day.isoformat()
        else:
            day_name = day
            # Build a transient day from the template alone (no fragment fill).
            try:
                # YYYY-MM-DD?
                from datetime import date as _date
                d = _date.fromisoformat(day)
                weekday = WEEKDAY_NAMES[d.weekday()]
            except ValueError:
                d = self.world.sim_time.date()
                weekday = day.lower()
            tl = DailyTimeline(d)
            if self.template:
                for b in self.template.blocks_for(weekday):
                    try:
                        a_h, a_m = (int(x) for x in b.start.split(":"))
                        e_h, e_m = (int(x) for x in b.end.split(":"))
                    except ValueError:
                        continue
                    from_idx = (a_h * 60 + a_m) // SLOT_MINUTES
                    to_idx = (e_h * 60 + e_m) // SLOT_MINUTES
                    if to_idx <= from_idx:
                        continue
                    tl.set_template(
                        from_idx, to_idx, b.activity, b.location_uid,
                        source_id=f"tpl:{self.template.id}:{b.start}-{b.end}",
                        target_state=getattr(b, "target_state", None) or {},
                    )
            day_name = d.isoformat()

        return {
            "day": day_name,
            "slots": [
                {
                    "index": s.index,
                    "start": s.start.isoformat(),
                    "end": s.end.isoformat(),
                    "kind": s.kind.value,
                    "activity": s.activity,
                    "location_uid": s.location_uid,
                    "source_id": s.source_id,
                }
                for s in tl.slots
                if s.kind != SlotKind.EMPTY
            ],
        }


def template_from_schema(tpl_schema: Any) -> ScheduleTemplate:
    """Convert a pydantic `ScheduleTemplateSchema` into a `ScheduleTemplate`.

    The pydantic block may carry extra fields (e.g. `narrative_zh`) that the
    plain dataclass `TemplateBlock` cannot accept; we only keep the four
    runtime-relevant fields.
    """
    week: dict[str, list[TemplateBlock]] = {}
    for day, blocks in tpl_schema.week.items():
        out: list[TemplateBlock] = []
        for b in blocks:
            out.append(TemplateBlock(
                start=b.start,
                end=b.end,
                activity=b.activity,
                location_uid=b.location_uid,
                target_state=dict(getattr(b, "target_state", None) or {}),
                narrative_zh=getattr(b, "narrative_zh", None),
            ))
        week[day] = out
    return ScheduleTemplate(
        id=tpl_schema.id,
        description=getattr(tpl_schema, "description", ""),
        week=week,
    )
