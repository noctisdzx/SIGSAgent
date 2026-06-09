"""NPCAgent aggregator.

Each NPC owns a perception view, a memory bundle, a decision pipeline,
and a behavior executor. The sim loop calls `perceive_decide_act(world)`
once per tick.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime
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
#
# This must cover BOTH the Chinese fragment labels produced by the slot_filler
# (e.g. "和朋友闲聊", "串门讨论") AND the English `activity` tokens baked into
# the weekly templates (have_lunch, club_activity, ...). The latter is where
# NPCs actually concentrate — canteens at meal time, club rooms, lectures — so
# without them dialogs almost never fire even when a room is packed. The LLM
# target-chooser still gets the final say (it returns null for heads-down/solo
# moments), so listing a gathering activity here only makes dialog *possible*.
SOCIAL_HINTS = (
    # generic / Chinese fragment cues
    "chat", "social", "聊", "搭话", "串门", "聚", "讨论", "约",
    "discussion", "group_discussion", "approach", "talk",
    # English template activities where NPCs gather → conversation is natural
    "lunch", "dinner", "breakfast", "meal", "have_lunch", "have_dinner",
    "club", "club_activity", "walk", "lecture", "attend_lecture",
)

# Minimum sim-minutes before the same pair may converse again. Candidates that
# were spoken to more recently than this are filtered out before the LLM picks
# a dialog target, which deterministically stops back-to-back repeats.
DIALOG_COOLDOWN_MIN = 45

# Dialog channel (Mutter state) tuning. When an NPC has no one to talk to this
# tick, it MAY mutter an inner monologue — gated by a cooldown + probability so
# 60 agents don't each fire an LLM call every tick.
MUTTER_COOLDOWN_MIN = 30
MUTTER_PROBABILITY = 0.3
from app.agents.memory.retriever import MemoryRetriever
from app.agents.memory.short_term import ShortTermItem, ShortTermMemory
from app.agents.perception.perceiver import Perceiver, PerceptionSnapshot
from app.agents.schedule.builder import schedule_item_to_stm
from app.agents.schedule.fragments import FragmentLibrary
from app.agents.schedule.insert_events import InsertEventLibrary, InsertEventSelector
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

WEEKDAY_LABELS = {
    "monday": ("周一", "Mon"),
    "tuesday": ("周二", "Tue"),
    "wednesday": ("周三", "Wed"),
    "thursday": ("周四", "Thu"),
    "friday": ("周五", "Fri"),
    "saturday": ("周六", "Sat"),
    "sunday": ("周日", "Sun"),
}


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
        insert_event_lib: InsertEventLibrary | None = None,
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
        # Per-weekday timelines retained across the week so the UI can show
        # how each day fills in. A weekday is reset to template-only when the
        # sim rolls around to it again (see `_ensure_timeline_for_today`).
        self.week_timelines: dict[str, DailyTimeline] = {
            self._weekday_name(): self.timeline,
        }

        # Decision
        self.slot_filler = SlotFiller(fragment_lib, llm)
        self.insert_event_lib = insert_event_lib
        self.insert_selector = (
            InsertEventSelector(insert_event_lib, llm) if insert_event_lib else None
        )
        self.goap_planner = GoapPlanner(action_lib.to_goap_actions())

        # Behavior + perception
        self.behavior_executor = behavior_executor or BehaviorExecutor(action_lib)
        self.perceiver = Perceiver(scene)

        # Per-partner last-talk sim_time, used to give the dialog-target chooser
        # a "recently spoken with" hint (so it varies the partner / can stay
        # quiet) instead of always re-engaging the same person every tick.
        self._dialog_last: dict[str, datetime] = {}
        # Last time this NPC muttered (inner monologue), for the mutter cooldown.
        self._mutter_last: datetime | None = None
        # Cache of LLM-authored, persona+scene-aware activity descriptions,
        # keyed by (raw_activity_label, here_uid). A fragment slot spans many
        # ticks, so we describe each distinct (activity, place) ONCE and reuse
        # it — the UI then shows this processed line instead of the raw label.
        self._activity_desc_cache: dict[tuple[str, str], dict[str, str]] = {}

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
        # New day → reset THIS weekday's timeline to template-only (replacing
        # last week's fills for the same weekday), keep the other weekdays.
        wd = WEEKDAY_NAMES[today.weekday()]
        self.timeline = DailyTimeline(today)
        self._timeline_day = today
        self._apply_template(self.timeline, wd)
        self.week_timelines[wd] = self.timeline

    def _apply_template(self, tl: DailyTimeline, weekday_name: str) -> None:
        """Mark TEMPLATE slots from the persona's weekly template onto `tl`."""
        if self.template is None:
            return
        for b in self.template.blocks_for(weekday_name):
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
            tl.set_template(
                from_idx, to_idx,
                activity=b.activity,
                location_uid=b.location_uid,
                source_id=f"tpl:{self.template.id}:{b.start}-{b.end}",
                target_state=getattr(b, "target_state", None) or {},
            )

    def _apply_template_to_timeline(self) -> None:
        self._apply_template(self.timeline, self._weekday_name())

    def _template_only_timeline(self, weekday_name: str) -> DailyTimeline:
        """A fresh template-only timeline for `weekday_name` (no fills).

        Used by the weekly schedule view for weekdays the sim has not yet
        reached this week. The date is a placeholder; the UI keys off slot
        indices, not the calendar date.
        """
        tl = DailyTimeline(self.world.sim_time.date())
        self._apply_template(tl, weekday_name)
        return tl

    def _current_slot(self) -> Slot:
        t = self.world.sim_time
        idx = (t.hour * 60 + t.minute) // SLOT_MINUTES
        idx = max(0, min(SLOTS_PER_DAY - 1, idx))
        return self.timeline.slots[idx]

    # ------------------------------------------------------------------
    #                  navigation helpers
    # ------------------------------------------------------------------

    def _next_move_target(self, current_uid: str | None, dest_uid: str | None) -> str | None:
        """Resolve the `move` target for this tick: the NEXT hop on the
        shortest path from `current_uid` to the slot destination `dest_uid`.

        NPCs know the full topology, so the search spans the whole scene graph.
        Movement is stepwise (one hop per tick) so a far destination is reached
        over several ticks with a visible trajectory. Falls back to the final
        destination (a teleport) when current is unknown or the destination is
        unreachable, so behaviour never regresses below the old one-step move.
        """
        if not dest_uid:
            return dest_uid
        if not current_uid or current_uid == dest_uid:
            return dest_uid
        nxt = self.scene.next_hop(current_uid, dest_uid)
        return nxt if nxt is not None else dest_uid

    def _prefer_location(
        self, here_uid: str | None, candidates: list[str], visible_uids: set[str],
    ) -> str | None:
        """Pick a destination from `candidates`, biased toward what the NPC can
        currently perceive / reach quickly.

        Priority: (1) a candidate in the current perception range, then
        (2) ascending hop-distance from `here_uid`, then (3) original order.
        This only re-ranks; every candidate stays reachable (global topology).
        """
        cands = [c for c in candidates if c]
        if not cands:
            return None

        def sort_key(uid: str) -> tuple[int, int, int]:
            visible = 0 if uid in visible_uids else 1
            hops = self.scene.hop_distance(here_uid, uid) if here_uid else None
            hop_rank = hops if hops is not None else 10_000
            return (visible, hop_rank, cands.index(uid))

        return min(cands, key=sort_key)

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

            cur_loc = agent_state.location_uid if agent_state else None
            chosen_step = None
            chosen_params: dict[str, Any] = {}
            if plan:
                chosen_step = plan[0]
                if chosen_step.action_id == "move":
                    # Stepwise navigation: head to the NEXT hop on the shortest
                    # path toward the slot destination, not the final room, so a
                    # far-away target is reached over several ticks with a
                    # visible trajectory (disconnected → teleport fallback).
                    chosen_params = {
                        "target_uid": self._next_move_target(cur_loc, slot.location_uid),
                    }
            else:
                # No-plan fallback: move if needed, else idle.
                if slot.location_uid and agent_state and agent_state.location_uid != slot.location_uid:
                    from app.agents.decision.goap_planner import PlanStep
                    chosen_step = PlanStep(action_id="move", label="move (fallback)",
                                            cost=1, duration_minutes=SLOT_MINUTES)
                    chosen_params = {
                        "target_uid": self._next_move_target(cur_loc, slot.location_uid),
                    }
                else:
                    from app.agents.decision.goap_planner import PlanStep
                    chosen_step = PlanStep(action_id="idle", label="idle (fallback)",
                                            cost=1, duration_minutes=SLOT_MINUTES)

            # 6) Dialog channel — the second of the two behaviour channels.
            #    It runs ALONGSIDE the body action this tick (the NPC may "talk
            #    while moving" / "mutter while resting"), producing either a
            #    TalkTo (LLM dialog with a co-located peer) or, failing that, a
            #    Mutter (inner monologue), or staying silent. `body_action` is
            #    passed in so a mutter can react to what the NPC is doing.
            body_action = chosen_step.action_id if chosen_step else "idle"
            dialog_action = await self._run_dialog_channel(
                slot, snap, visible_agents, world, body_action,
            )

            # Persona + scene-aware rephrasing of the raw schedule/fragment
            # label, surfaced to the UI so it shows what THIS npc is actually
            # doing here (cached per activity+place, so cheap across ticks).
            activity_desc = await self._describe_activity(
                activity_text, slot, snap, world,
            )

            # Navigation telemetry: when this tick's body action is a move,
            # expose the destination, the chosen next hop, and how many hops
            # remain so the UI can follow the multi-hop journey.
            nav: dict[str, Any] | None = None
            if body_action == "move" and slot.location_uid:
                nav = {
                    "dest": slot.location_uid,
                    "next_hop": chosen_params.get("target_uid"),
                    "hops_remaining": self.scene.hop_distance(cur_loc, slot.location_uid)
                    if cur_loc else None,
                }

            # 6b) Emit decision event — now carrying BOTH channels so the UI can
            #     surface the dual-channel behaviour (body + dialog).
            await event_bus.publish({
                "type": "agent_decision",
                "ts_sim": world.sim_time.isoformat(),
                "agent_id": self.persona.id,
                "payload": {
                    "activity": activity_text,
                    "activity_desc": activity_desc.get("zh") if activity_desc else None,
                    "activity_desc_en": activity_desc.get("en") if activity_desc else None,
                    "slot_kind": slot.kind.value,
                    "location_uid": slot.location_uid,
                    "goal": goal,
                    "plan": [
                        {"action_id": s.action_id, "label": s.label, "cost": s.cost,
                         "duration_minutes": s.duration_minutes}
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
                    "channels": {"body": body_action, "dialog": dialog_action},
                    "nav": nav,
                },
            })

            # 7) Execute step + write a result-flavoured STM so future decisions
            #    can see what just happened (success/failure + reason + state).
            if chosen_step is not None:
                # Commit under the world lock so precondition-check + effect-apply
                # is atomic across concurrently-ticking agents. We also re-read
                # the live state inside the lock (the perception that drove the
                # plan may be a few awaits stale) so pre_state reflects reality.
                async with world.lock:
                    live = world.agents.get(self.persona.id)
                    if live is not None:
                        pre_state = {
                            "agent.location_uid": live.location_uid,
                            "agent.energy": live.energy,
                            "agent.hunger": live.hunger,
                            "agent.money": live.money,
                            "agent.mood": live.mood,
                        }
                    else:
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

            # 8) Occasional emergent item carry: pick up a movable item nearby,
            # or drop something we're already carrying. Light-touch, but enough
            # to keep the scene-graph items panel visibly evolving.
            try:
                await self._maybe_carry_item(world, activity_text)
            except Exception as exc:
                log.debug("carry-item hook failed for %s: %s", self.persona.id, exc)

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

        # First, give a special "insert event" a chance to claim this gap.
        # If an eligible high-affinity event exists, the LLM picks one and we
        # write it as a FRAGMENT-kind block destined for the event's end room
        # (GOAP drives the start→end trip via its location goal).
        if self.insert_selector is not None and await self._maybe_inject_event(
            cur_idx, gap_minutes, ctx, query,
        ):
            return

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
        # Pick the fragment's destination with a perception bias: prefer a
        # preferred location the NPC can currently see / reach quickly, rather
        # than always grabbing the first one listed.
        visible_uids: set[str] = set()
        if snap is not None:
            visible_uids = {
                room.uid
                for room in (snap.children + snap.siblings + snap.adjacent_fallback)
            }
        loc = self._prefer_location(
            here_uid, frag.preferred_location_uids, visible_uids,
        )
        if loc is None:
            loc = (self.world.agents[self.persona.id].location_uid
                   if self.persona.id in self.world.agents else None)
        # only fill the slots covered by the fragment's nominal duration
        slot_span = max(1, frag.duration_minutes // SLOT_MINUTES)
        end_idx = min(SLOTS_PER_DAY, cur_idx + slot_span)
        self.timeline.set_fragment(
            cur_idx, end_idx,
            activity=frag.label,
            location_uid=loc,
            fragment_id=frag.id,
        )

    async def _maybe_inject_event(
        self,
        cur_idx: int,
        gap_minutes: int,
        ctx: dict,
        query: str,
    ) -> bool:
        """Try to claim the current gap with a special insert event.

        Returns True if an event was written into the timeline (so the caller
        skips the generic fragment fill); False otherwise.
        """
        if self.insert_selector is None:
            return False
        try:
            choice = await self.insert_selector.select(
                gap_minutes=gap_minutes,
                persona=self.persona.to_dict(),
                memories=[m.text for m in self.retriever.retrieve(
                    query=query or "free time", top_k=5,
                )],
                context=ctx,
            )
        except Exception as exc:
            log.debug("insert-event select failed for %s: %s", self.persona.id, exc)
            return False
        if choice is None:
            return False

        ev = choice.event
        slot_span = max(1, ev.duration_minutes // SLOT_MINUTES)
        end_idx = min(SLOTS_PER_DAY, cur_idx + slot_span)
        # The event ends at `end_uid`; GOAP turns this location goal into the
        # start→end move. `activity` carries the NL description so the UI + the
        # dialog hint can read it.
        self.timeline.set_fragment(
            cur_idx, end_idx,
            activity=ev.description_zh or ev.id,
            location_uid=ev.end_uid,
            fragment_id=f"insert:{ev.id}",
        )
        await event_bus.publish({
            "type": "insert_event",
            "ts_sim": self.world.sim_time.isoformat(),
            "agent_id": self.persona.id,
            "payload": {
                "event_id": ev.id,
                "description_zh": ev.description_zh,
                "description_en": ev.description_en,
                "tags": ev.tags,
                "from": ev.start_uid,
                "to": ev.end_uid,
                "duration_minutes": ev.duration_minutes,
                "rationale": choice.rationale,
                "degraded": choice.degraded,
            },
        })
        return True

    # ------------------------------------------------------------------
    #                  dialog pipeline
    # ------------------------------------------------------------------

    def _is_social_activity(self, activity: str | None) -> bool:
        if not activity:
            return False
        low = activity.lower()
        return any(h in low for h in SOCIAL_HINTS)

    async def _maybe_carry_item(self, world: "WorldState", activity_text: str) -> None:
        """Probabilistic pickup / drop. Lets NPCs ferry chairs / mugs / books
        across rooms — a lightweight stand-in for a goal-driven inventory plan.

        * If holding nothing & a movable item is in the room: ~15% chance pickup.
        * If currently holding an item: ~25% chance drop (after at least one
          room change so the user can see something *move*).
        """
        import random
        a = world.agents.get(self.persona.id)
        if not a:
            return

        # Drop branch — only when we've already moved to a *different* room
        # than where we picked it up (otherwise it's not visually interesting).
        if a.holding:
            iid = a.holding
            it = world.items.get(iid)
            if not it:
                a.holding = None
                return
            origin = (it.extra or {}).get("origin_uid")
            if origin and origin != a.location_uid and random.random() < 0.25:
                if self.behavior_executor is not None:
                    async with world.lock:
                        res = await self.behavior_executor.execute(
                            self.persona.id, "drop", {"item_id": iid}, world,
                        )
                    if res.ok:
                        await event_bus.publish({
                            "type": "behavior",
                            "ts_sim": world.sim_time.isoformat(),
                            "agent_id": self.persona.id,
                            "payload": {
                                **res.to_dict(),
                                "item_id": iid,
                                "from": origin,
                                "to": a.location_uid,
                                "activity": f"drop({iid})",
                            },
                        })
            return

        # Pickup branch
        if random.random() >= 0.15:
            return
        # candidates: movable items in this room, not already carried
        here_items = [
            it for it in world.items.values()
            if it.location_uid == a.location_uid
            and not (it.extra or {}).get("carrier_id")
            and (it.extra or {}).get("movable")
        ]
        if not here_items:
            return
        pick = random.choice(here_items)
        # remember where it came from so we know when a drop is "meaningful"
        pick.extra["origin_uid"] = a.location_uid
        if self.behavior_executor is not None:
            async with world.lock:
                res = await self.behavior_executor.execute(
                    self.persona.id, "pickup", {"item_id": pick.id}, world,
                )
            if res.ok:
                await event_bus.publish({
                    "type": "behavior",
                    "ts_sim": world.sim_time.isoformat(),
                    "agent_id": self.persona.id,
                    "payload": {
                        **res.to_dict(),
                        "item_id": pick.id,
                        "from": a.location_uid,
                        "to": a.location_uid,
                        "activity": f"pickup({pick.id})",
                    },
                })

    async def _maybe_have_dialog(
        self,
        slot: Slot,
        snap: PerceptionSnapshot,
        visible_agents: list[str],
        world: "WorldState",
    ) -> bool:
        """Dialog-channel `TalkTo`: if someone is co-located and the NPC feels
        social enough this tick, ask the LLM for one short dialog and persist
        both sides. Returns True iff a dialog actually happened.

        Co-location is required so the `talk` precondition
        (target.location_uid == agent.location_uid) is guaranteed to hold.
        Note: this is NO LONGER hard-gated on the activity being "social" — the
        activity only nudges the social-willingness roll, and the LLM
        `choose_dialog_target` makes the final WHO/whether-to-talk call (it can
        return null for heads-down moments). This is what lets dialogs happen
        at meals / club / lectures, not just the rare `group_discussion` slot.
        """
        # Co-location is a SAME-ROOM relationship, which the perception snapshot
        # does NOT expose: `visible_agents` / snap.children / snap.siblings only
        # cover *neighbouring* rooms (children/siblings are adjacent rooms, never
        # `here` itself). Gating on `visible_agents` here was the dialog bug —
        # at a packed canteen with empty neighbours `visible_agents` is [], so
        # everyone stayed silent even though dozens shared the room. So we read
        # same-room peers straight from WorldState, which is exactly what the
        # `talk` precondition (target.location_uid == agent.location_uid) needs.
        colocated = sorted({
            aid for aid, st in world.agents.items()
            if aid != self.persona.id and st.location_uid == snap.here_uid
        })
        if not colocated:
            log.debug("dialog[%s] skip: no co-located peers in %s",
                      self.persona.id, snap.here_uid)
            return False

        situation = {
            "sim_time": world.sim_time.isoformat(timespec="minutes"),
            "weekday": self._weekday_name(),
            "here_uid": snap.here_uid,
            "here_name": snap.here_name,
            "current_activity": slot.activity,
        }

        # Build the candidate roster (co-located, resolvable personas) and let
        # the LLM decide WHO to talk to — rather than always grabbing the
        # alphabetically-first neighbour (the old `colocated[0]`, which made the
        # same pair converse every single tick with near-identical context, so
        # the LLM kept echoing the same line).
        #
        # We first drop anyone we spoke with within DIALOG_COOLDOWN_MIN sim-min:
        # a deterministic cooldown that, by itself, prevents the same pair from
        # re-talking back-to-back. Whoever survives the filter is handed to the
        # LLM, which picks the actual partner.
        candidates: list[dict[str, Any]] = []
        now = world.sim_time
        for cid in colocated:
            peer = self._registry.get(cid)
            if peer is None:
                continue
            last = self._dialog_last.get(cid)
            mins_since = int((now - last).total_seconds() // 60) if last else None
            if mins_since is not None and mins_since < DIALOG_COOLDOWN_MIN:
                continue  # talked too recently — skip to avoid repeats
            candidates.append({
                "id": cid,
                "name": peer.persona.name,
                "name_en": getattr(peer.persona, "name_en", "") or peer.persona.name,
                "archetype": getattr(peer.persona, "archetype", "") or "",
                # how long since we last spoke (None = never) — helps the chooser
                # favour fresh / less-recent partners.
                "minutes_since_last_talk": mins_since,
            })
        if not candidates:
            log.debug("dialog[%s] skip: all %d co-located peers on cooldown in %s",
                      self.persona.id, len(colocated), snap.here_uid)
            return False

        # Social-willingness gate (cheap, no LLM): extraverts and socially
        # flavoured activities are more likely to strike up a conversation.
        # If the roll fails we stay quiet this tick — which leaves the door
        # open for a Mutter instead.
        if not self._social_willingness(slot):
            log.debug("dialog[%s] skip: not willing this tick (act=%r, %d candidates)",
                      self.persona.id, slot.activity, len(candidates))
            return False
        log.info("dialog[%s] willing @%s act=%r candidates=%d → choosing target",
                 self.persona.id, snap.here_uid, slot.activity, len(candidates))

        target_id: str | None = None
        try:
            target_id, why = await self.llm.choose_dialog_target(
                speaker=self.persona.to_dict(),
                candidates=candidates,
                situation=situation,
            )
        except Exception as exc:
            log.debug("choose_dialog_target failed for %s: %s", self.persona.id, exc)
            target_id = None

        # Honor an explicit "stay silent" decision from the LLM.
        if not target_id:
            log.info("dialog[%s] LLM chose to stay silent (%d candidates)",
                     self.persona.id, len(candidates))
            return False
        # Guard against a hallucinated id outside the co-located roster.
        if target_id not in {c["id"] for c in candidates}:
            log.debug("dialog target %r not co-located; skipping", target_id)
            return False

        listener = self._registry.get(target_id)
        if listener is None:
            return False
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
            return False
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
        # Held under the world lock together with the cross-agent STM / memory
        # writes below so a concurrent tick can't interleave with them.
        async with world.lock:
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
        # Commit both STMs under the world lock; run the (possibly LLM-backed)
        # compression OUTSIDE the lock so we never hold it across a network call.
        async with world.lock:
            sp_added = self.stm.add(speaker_stm)
            li_added = listener.stm.add(listener_stm)
        if sp_added:
            try:
                await self.compressor.maybe_compress(now=world.sim_time)
            except Exception:
                pass
        if li_added:
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
        async with world.lock:
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

        # Remember this exchange on both sides so the next target choice can
        # see "we just spoke" and prefer variety / silence.
        self._dialog_last[target_id] = world.sim_time
        listener._dialog_last[self.persona.id] = world.sim_time
        return True

    # ------------------------------------------------------------------
    #                  dialog channel orchestration
    # ------------------------------------------------------------------

    def _extraversion(self) -> float:
        """Best-effort extraversion in [0, 1].

        Persona personality may be flat (`{"extroversion": 0.7}`) or nested
        (`{"ocean": {...}}`), and the data uses the -version/-aversion spelling
        inconsistently, so we probe several keys and normalise a 0-100 value.
        """
        p = self.persona.personality or {}
        src = p.get("ocean") if isinstance(p.get("ocean"), dict) else p
        if not isinstance(src, dict):
            return 0.5
        for k in ("extraversion", "extroversion", "E", "e"):
            v = src.get(k)
            if v is None:
                continue
            try:
                f = float(v)
            except (TypeError, ValueError):
                continue
            return max(0.0, min(1.0, f / 100.0 if f > 1.0 else f))
        return 0.5

    def _social_willingness(self, slot: Slot) -> bool:
        """Cheap (no-LLM) roll for whether to attempt a conversation this tick.

        Extraverts talk more; a socially flavoured activity boosts the odds.
        The LLM still gets the final say on WHO / whether to speak.
        """
        import random
        prob = 0.25 + 0.5 * self._extraversion()
        if self._is_social_activity(slot.activity):
            prob = min(1.0, prob + 0.35)
        return random.random() < prob

    # Raw labels we never bother to "describe" (action verbs / trivial states).
    _UNDESCRIBED_ACTIVITIES = {"", "idle", "idle (fallback)"}

    async def _describe_activity(
        self,
        activity: str,
        slot: Slot,
        snap: PerceptionSnapshot,
        world: "WorldState",
    ) -> dict[str, str] | None:
        """Return a persona + scene-aware description of the current activity,
        so the UI shows a processed line instead of the raw fragment label.

        Cached per (activity, here_uid) on this agent — a fragment occupies the
        slot for many ticks, so we only call the LLM once per distinct
        (activity, place) and reuse it. Returns None for trivial activities or
        on failure (UI then falls back to the raw label).
        """
        act = (activity or "").strip()
        if act in self._UNDESCRIBED_ACTIVITIES:
            return None
        # Action-shaped labels like "pickup(x)" / "drop(y)" aren't schedule
        # activities — leave them untouched.
        if act.endswith(")") and ("(" in act):
            return None
        here = snap.here_uid or ""
        key = (act, here)
        cached = self._activity_desc_cache.get(key)
        if cached is not None:
            return cached
        try:
            desc = await self.llm.describe_activity(
                persona=self.persona.to_dict(),
                activity=act,
                situation={
                    "sim_time": world.sim_time.isoformat(timespec="minutes"),
                    "weekday": self._weekday_name(),
                    "here_uid": snap.here_uid,
                    "here_name": snap.here_name,
                },
            )
        except Exception as exc:
            log.debug("describe_activity failed for %s: %s", self.persona.id, exc)
            return None
        if not isinstance(desc, dict) or not desc.get("description_zh"):
            return None
        out = {
            "zh": str(desc.get("description_zh", "")).strip(),
            "en": str(desc.get("description_en", "")).strip()
            or str(desc.get("description_zh", "")).strip(),
        }
        self._activity_desc_cache[key] = out
        return out

    async def _run_dialog_channel(
        self,
        slot: Slot,
        snap: PerceptionSnapshot,
        visible_agents: list[str],
        world: "WorldState",
        body_action: str,
    ) -> str:
        """Drive the dialog channel for one tick.

        Tries a `TalkTo` first; if no conversation happens, MAY fall back to a
        `Mutter` (inner monologue). Returns the dialog action that occurred:
        "talk" | "mutter" | "silent".
        """
        talked = False
        try:
            talked = await self._maybe_have_dialog(slot, snap, visible_agents, world)
        except Exception as exc:
            log.warning("dialog pipeline failed for %s: %s", self.persona.id, exc)
        if talked:
            return "talk"

        muttered = False
        try:
            muttered = await self._maybe_mutter(slot, snap, world, body_action)
        except Exception as exc:
            log.debug("mutter pipeline failed for %s: %s", self.persona.id, exc)
        return "mutter" if muttered else "silent"

    async def _maybe_mutter(
        self,
        slot: Slot,
        snap: PerceptionSnapshot,
        world: "WorldState",
        body_action: str,
    ) -> bool:
        """Dialog-channel `Mutter`: a short inner monologue when there's no one
        to talk to. Gated by a cooldown + probability to bound LLM volume.
        Returns True iff a mutter was produced.
        """
        import random
        now = world.sim_time
        if self._mutter_last is not None:
            mins_since = (now - self._mutter_last).total_seconds() / 60.0
            if mins_since < MUTTER_COOLDOWN_MIN:
                return False
        if random.random() >= MUTTER_PROBABILITY:
            return False

        situation = {
            "sim_time": now.isoformat(timespec="minutes"),
            "weekday": self._weekday_name(),
            "here_uid": snap.here_uid,
            "here_name": snap.here_name,
            "current_activity": slot.activity or "idle",
            "body_action": body_action or "idle",
        }
        memories = [
            m.text for m in self.retriever.retrieve(
                query=slot.activity or "free time", top_k=2,
            )
        ]
        try:
            result = await self.llm.generate_mutter(
                speaker=self.persona.to_dict(),
                situation=situation,
                memories=memories,
            )
        except Exception as exc:
            log.debug("generate_mutter failed for %s: %s", self.persona.id, exc)
            return False

        line = (result.get("line") or "").strip()
        if not line:
            return False
        line_en = (result.get("line_en") or line).strip() or line
        mood = (result.get("mood") or "neutral").strip() or "neutral"
        hhmm = now.strftime("%H:%M")

        # STM (single-sided — only this NPC "hears" their own thought).
        stm_item = ShortTermItem(
            id=f"stm_mut_{uuid.uuid4().hex[:8]}",
            text=f"[{hhmm}]（心想）{line}",
            text_en=f"[{hhmm}] (thought) {line_en}",
            ts=now,
            source="mutter",
            meta={
                "agent_id": self.persona.id,
                "mood": mood,
                "here_uid": snap.here_uid,
                "activity": slot.activity,
                "body_action": body_action,
                "line": line,
                "line_en": line_en,
            },
        )
        if self.stm.add(stm_item):
            try:
                await self.compressor.maybe_compress(now=now)
            except Exception:
                pass

        # Record in behavior history so day-summary + introspection see it.
        async with world.lock:
            try:
                await self.behavior_executor.execute(
                    self.persona.id, "mutter", {}, world,
                )
            except Exception as exc:
                log.debug("mutter action exec failed: %s", exc)

        await event_bus.publish({
            "type": "mutter",
            "ts_sim": now.isoformat(),
            "agent_id": self.persona.id,
            "payload": {
                "agent_id": self.persona.id,
                "name": self.persona.name,
                "name_en": getattr(self.persona, "name_en", None) or self.persona.name,
                "here_uid": snap.here_uid,
                "line": line,
                "line_en": line_en,
                "mood": mood,
                "activity": slot.activity,
                "body_action": body_action,
            },
        })
        self._mutter_last = now
        return True

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

    def week_view(self) -> dict[str, Any]:
        """Weekly schedule (Mon–Sun) for the NPC-detail page.

        Each day returns ALL 288 five-minute slots (including empty ones) so
        the UI can render the full grid and watch gaps fill in over the day.
        Days already visited this week carry their accumulated TEMPLATE +
        FRAGMENT/insert fills; not-yet-reached days show template-only.
        """
        today_wd = self._weekday_name()
        cur = self._current_slot()
        days: list[dict[str, Any]] = []
        for wd in WEEKDAY_NAMES:
            tl = self.week_timelines.get(wd) or self._template_only_timeline(wd)
            label_zh, label_en = WEEKDAY_LABELS[wd]
            days.append({
                "weekday": wd,
                "label_zh": label_zh,
                "label_en": label_en,
                "is_today": wd == today_wd,
                "slots": [
                    {
                        "index": s.index,
                        "kind": s.kind.value,
                        "activity": s.activity,
                        "location_uid": s.location_uid,
                        "source_id": s.source_id,
                    }
                    for s in tl.slots
                ],
            })
        return {
            "mode": "week",
            "today": today_wd,
            "current_slot_index": cur.index,
            "slot_minutes": SLOT_MINUTES,
            "days": days,
        }

    def schedule_view(self, day: str | None = None, week: bool = False) -> dict[str, Any]:
        if week:
            return self.week_view()
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
