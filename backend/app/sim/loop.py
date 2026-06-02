"""Per-tick orchestration: advance sim time, then each agent perceives→decides→acts.

Also detects midnight rollover and asks the LLM for an omniscient narrator
day summary, then auto-pauses so the player can read it before opting into
the next day via /api/sim/start.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from app.events.bus import event_bus
from app.world.scene_graph import SceneGraph
from app.world.world_state import WorldState
from .clock import TickClock

log = logging.getLogger("sigs.sim")


class SimLoop:
    def __init__(self, world: WorldState, scene: SceneGraph) -> None:
        self.world = world
        self.scene = scene
        self.agents: dict[str, Any] = {}
        self.clock = TickClock(on_tick=self._tick)
        self._running = False
        self._latest_decisions: list[dict[str, Any]] = []
        # Day-summary plumbing
        self.llm: Any | None = None
        self.day_summaries: list[dict[str, Any]] = []
        self.pause_reason: str | None = None
        # Track which sim-day we last summarised so we only fire once per rollover.
        self._last_summarised_day: date | None = None
        self._busy_summarising: bool = False

    def set_llm(self, llm: Any) -> None:
        self.llm = llm

    # ----- registration -----

    def register_agent(self, agent_id: str, agent: Any) -> None:
        self.agents[agent_id] = agent

    def unregister_agent(self, agent_id: str) -> None:
        self.agents.pop(agent_id, None)

    def clear_agents(self) -> None:
        self.agents.clear()

    # ----- tick -----

    async def _tick(self, idx: int) -> None:
        # Snapshot positions BEFORE the tick so we can compute world_delta.
        before = {aid: a.location_uid for aid, a in self.world.agents.items()}
        prev_day = self.world.sim_time.date()

        self.world.sim_time = self.world.sim_time + self.clock.sim_tick_delta
        new_day = self.world.sim_time.date()

        # Midnight rollover → run a day summary then pause, so the player can
        # read it before opting into the next day. Only once per real day even
        # if the loop is repeatedly stepped.
        if new_day != prev_day and self._last_summarised_day != prev_day:
            self._last_summarised_day = prev_day
            try:
                await self._do_day_summary(prev_day)
            except Exception as exc:
                log.exception("day summary failed for %s: %s", prev_day, exc)
            # Auto-pause regardless of whether the LLM call succeeded.
            self.pause_reason = f"day_summary:{prev_day.isoformat()}"
            await self.stop()
            return  # skip the rest of this tick — the next /api/sim/start re-enters

        recent_decisions: list[dict[str, Any]] = []
        for aid, agent in self.agents.items():
            try:
                await agent.perceive_decide_act(self.world, self.scene)
                # Best-effort latest-decision snapshot for the tick payload.
                history = getattr(agent, "behavior_executor", None)
                if history and getattr(history, "history", None):
                    last = history.history.get(aid, [])
                    if last:
                        recent_decisions.append(last[-1].to_dict())
            except NotImplementedError:
                continue
            except Exception as exc:
                log.exception("agent %s tick failed: %s", aid, exc)
                await event_bus.publish({
                    "type": "agent_error",
                    "ts_sim": self.world.sim_time.isoformat(),
                    "agent_id": aid,
                    "payload": {"error": repr(exc)},
                })

        # Compute world_delta: which agents moved this tick.
        moved: list[dict[str, str]] = []
        for aid, a in self.world.agents.items():
            prev = before.get(aid)
            if prev is not None and prev != a.location_uid:
                moved.append({"agent_id": aid, "from": prev, "to": a.location_uid})

        # Items being carried follow their carrier across rooms.
        self.world.tick_carried_items()

        self._latest_decisions = recent_decisions

        await event_bus.publish({
            "type": "tick",
            "ts_sim": self.world.sim_time.isoformat(),
            "payload": {
                "index": idx,
                "n_agents": len(self.agents),
                "world_delta": {"moved": moved},
                "recent_decisions": recent_decisions[:20],
            },
        })

    # ----- control -----

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        # Once the player resumes, clear the pause reason so the UI can hide
        # the "next day" prompt; the next midnight rollover will set it again.
        self.pause_reason = None
        await self.clock.start()

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        await self.clock.stop()

    async def step(self) -> None:
        await self.clock.step()

    @property
    def is_running(self) -> bool:
        return self._running

    # ----- day summary -----

    async def _do_day_summary(self, summarised_day: date) -> None:
        """Collect the day's events from every agent and ask the LLM for a
        bilingual omniscient-narrator paragraph. Persists the result to
        ``self.day_summaries`` and publishes a `day_summary` WS event.
        """
        if self._busy_summarising:
            return
        self._busy_summarising = True
        try:
            day_iso = summarised_day.isoformat()
            log.info("Generating day summary for %s ...", day_iso)

            # Collect lightweight bullets: dialogs first (most narratively rich),
            # then behavior history and STM, capped so the prompt stays sane.
            bullets: list[str] = []
            n_agents = len(self.agents)
            n_dialogs = 0
            n_behaviors = 0
            n_memories = 0

            # Per-NPC tally so the LLM can pick a real protagonist.
            per_actor: dict[str, dict[str, Any]] = {}

            def _bump(aid: str, pname: str, pname_en: str, key: str) -> None:
                slot = per_actor.setdefault(aid, {
                    "id": aid,
                    "name": pname,
                    "name_en": pname_en or pname,
                    "n_behaviors": 0,
                    "n_dialogs": 0,
                })
                slot[key] = int(slot.get(key, 0)) + 1

            for aid, agent in self.agents.items():
                persona = getattr(agent, "persona", None)
                pname = getattr(persona, "name", aid)
                pname_en = getattr(persona, "name_en", "") or pname

                # Dialogs (from STM source=dialog:*) belong to this day if ts.date matches
                stm_items = getattr(getattr(agent, "stm", None), "all", lambda: [])()
                for it in stm_items:
                    if it.ts.date() != summarised_day:
                        continue
                    n_memories += 1
                    if (it.source or "").startswith("dialog:"):
                        n_dialogs += 1
                        _bump(aid, pname, pname_en, "n_dialogs")
                        partner = (it.meta or {}).get("partner_name", "?")
                        line = (it.meta or {}).get("line", "")
                        reply = (it.meta or {}).get("reply", "")
                        bullets.append(
                            f"{it.ts.strftime('%H:%M')} {pname} ↔ {partner}: "
                            f"\"{line}\" / \"{reply}\""
                        )

                # Behavior history (executor side)
                exec_ = getattr(agent, "behavior_executor", None)
                if exec_ is not None:
                    items = exec_.history_for(aid, limit=200) if hasattr(exec_, "history_for") else []
                    for h in items:
                        if getattr(h, "ts", None) is None or h.ts.date() != summarised_day:
                            continue
                        if h.action_id in {"move", "talk", "interact"}:
                            n_behaviors += 1
                            _bump(aid, pname, pname_en, "n_behaviors")
                            ok = "✓" if h.ok else "✗"
                            bullets.append(
                                f"{h.ts.strftime('%H:%M')} {pname} {ok} "
                                f"{h.action_id}({h.params})"
                            )

            # Cap bullets to ~120 entries to stay friendly to LLM context.
            bullets = bullets[-120:]

            # Top-12 actors by (behaviors + 2*dialogs) so dialog-heavy NPCs surface.
            activity_top = sorted(
                per_actor.values(),
                key=lambda a: int(a.get("n_behaviors", 0)) + 2 * int(a.get("n_dialogs", 0)),
                reverse=True,
            )[:12]

            summary_meta = {
                "day": day_iso,
                "n_agents": n_agents,
                "n_dialogs": n_dialogs,
                "n_behaviors": n_behaviors,
                "n_memories": n_memories,
                "n_bullets_used": len(bullets),
                "activity_top": activity_top,
            }
            log.info("day-summary inputs: %s", summary_meta)

            zh = "（今日无事可记。）"
            en = "(Nothing of note happened today.)"
            degraded = True
            rich: dict[str, Any] = {}

            if self.llm is not None and bullets:
                try:
                    result = await self.llm.narrate_day(
                        day=day_iso,
                        bullets=bullets,
                        stats=summary_meta,
                    )
                    zh = (result.get("zh") or zh).strip() or zh
                    en = (result.get("en") or en).strip() or en
                    degraded = bool(result.get("degraded", False))
                    # Carry over the short-story payload; missing keys are tolerated
                    # by the frontend renderer which falls back to the synopsis.
                    rich = {
                        "title_zh": str(result.get("title_zh", "")).strip(),
                        "title_en": str(result.get("title_en", "")).strip(),
                        "protagonist": result.get("protagonist") or {},
                        "supporting": result.get("supporting") or [],
                        "story_zh": str(result.get("story_zh", "")).strip(),
                        "story_en": str(result.get("story_en", "")).strip(),
                        "tomorrow_zh": str(result.get("tomorrow_zh", "")).strip(),
                        "tomorrow_en": str(result.get("tomorrow_en", "")).strip(),
                    }
                except Exception as exc:
                    log.warning("LLM narrate_day failed: %s", exc)
                    degraded = True

            # Strip the heavy activity_top off the persisted stats blob — the
            # frontend doesn't need it and it bloats the WS payload.
            stats_for_entry = {k: v for k, v in summary_meta.items() if k != "activity_top"}

            entry = {
                "day": day_iso,
                "ts_real": __import__("datetime").datetime.utcnow().isoformat(),
                "ts_sim": self.world.sim_time.isoformat(),
                "narrative_zh": zh,
                "narrative_en": en,
                "stats": stats_for_entry,
                "degraded": degraded,
                **rich,
            }
            self.day_summaries.append(entry)
            # Cap retained summaries so memory doesn't grow forever.
            if len(self.day_summaries) > 60:
                self.day_summaries = self.day_summaries[-60:]

            await event_bus.publish({
                "type": "day_summary",
                "ts_sim": self.world.sim_time.isoformat(),
                "agent_id": None,
                "payload": entry,
            })
            log.info("Day summary for %s ready (zh %d / en %d chars, degraded=%s)",
                     day_iso, len(zh), len(en), degraded)
        finally:
            self._busy_summarising = False
