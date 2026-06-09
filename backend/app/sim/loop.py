"""Per-tick orchestration: advance sim time, then each agent perceives→decides→acts.

Also detects midnight rollover and asks the LLM for an omniscient narrator
day summary, then auto-pauses so the player can read it before opting into
the next day via /api/sim/start.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

from app.events.bus import event_bus
from app.settings import get_settings
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
        # Optional per-tick recorder (set by main.py). None = no recording.
        self.recorder: Any | None = None
        # Whole-run ("各总") cumulative heat — independent of the frontend's
        # localStorage counters so it survives reloads and can be exported.
        #   heat_moves: undirected edge "a|b" (a<b)  -> traversal count
        #   heat_dwell: room uid                     -> per-tick presence samples
        self.heat_moves: dict[str, int] = {}
        self.heat_dwell: dict[str, int] = {}
        self._heat_ticks: int = 0

    def set_recorder(self, recorder: Any) -> None:
        self.recorder = recorder

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

        # Run agents concurrently (bounded) — the per-agent work is dominated by
        # awaited LLM calls, so firing them together collapses N sequential
        # network round-trips into ~1. A semaphore caps how many hit the LLM at
        # once; set SIM_TICK_CONCURRENCY=1 to restore strict sequential ticking.
        recent_decisions: list[dict[str, Any]] = []
        concurrency = max(1, get_settings().sim_tick_concurrency)
        sem = asyncio.Semaphore(concurrency)

        async def _run_one(aid: str, agent: Any) -> None:
            async with sem:
                try:
                    await agent.perceive_decide_act(self.world, self.scene)
                    history = getattr(agent, "behavior_executor", None)
                    if history and getattr(history, "history", None):
                        last = history.history.get(aid, [])
                        if last:
                            recent_decisions.append(last[-1].to_dict())
                except NotImplementedError:
                    return
                except Exception as exc:
                    log.exception("agent %s tick failed: %s", aid, exc)
                    await event_bus.publish({
                        "type": "agent_error",
                        "ts_sim": self.world.sim_time.isoformat(),
                        "agent_id": aid,
                        "payload": {"error": repr(exc)},
                    })

        await asyncio.gather(*(_run_one(aid, agent) for aid, agent in self.agents.items()))

        # Compute world_delta: which agents moved this tick.
        moved: list[dict[str, str]] = []
        for aid, a in self.world.agents.items():
            prev = before.get(aid)
            if prev is not None and prev != a.location_uid:
                moved.append({"agent_id": aid, "from": prev, "to": a.location_uid})

        # Accumulate the whole-run heat map (cumulative, server-side).
        self._accumulate_heat(moved)

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

        # Persist this tick as a playback frame (world snapshot + the events
        # emitted during the tick, which the recorder tapped off the bus).
        if self.recorder is not None:
            try:
                self.recorder.write_frame(
                    index=idx,
                    sim_time=self.world.sim_time.isoformat(),
                    world=self.world.snapshot(),
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("recorder.write_frame failed: %s", exc)

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

    # ----- whole-run heat map -----

    def _accumulate_heat(self, moved: list[dict[str, str]]) -> None:
        """Fold this tick into the cumulative heat counters.

        - moves: one undirected-edge increment per agent that changed rooms
        - dwell: one increment for every agent's current room (a per-tick
          presence sample, the same proxy the frontend uses).
        """
        for m in moved:
            a, b = m.get("from"), m.get("to")
            if not a or not b or a == b:
                continue
            key = f"{a}|{b}" if a < b else f"{b}|{a}"
            self.heat_moves[key] = self.heat_moves.get(key, 0) + 1
        for st in self.world.agents.values():
            uid = getattr(st, "location_uid", None)
            if uid:
                self.heat_dwell[uid] = self.heat_dwell.get(uid, 0) + 1
        self._heat_ticks += 1

    def heatmap_view(self) -> dict[str, Any]:
        """Whole-run cumulative heat, ready for the UI / export.

        Keys match the frontend heat store (undirected "a|b" move edges, room
        uid dwell) so the client can load it directly.
        """
        return {
            "ticks": self._heat_ticks,
            "sim_time": self.world.sim_time.isoformat(),
            "moves": dict(self.heat_moves),
            "dwell": dict(self.heat_dwell),
            "max_move": max(self.heat_moves.values(), default=0),
            "max_dwell": max(self.heat_dwell.values(), default=0),
        }

    def load_state(
        self,
        *,
        heatmap: dict[str, Any] | None = None,
        day_summaries: list[dict[str, Any]] | None = None,
    ) -> None:
        """Restore SimLoop-owned state from an imported run so the sim can
        continue where it left off.

        - ``heatmap``: re-seeds the cumulative move/dwell counters + tick count.
        - ``day_summaries``: replaces the narrative log and marks the latest
          finished day as already-summarised, so resuming doesn't re-fire a
          summary for a day that's already done.
        """
        if heatmap:
            self.heat_moves = {
                str(k): int(v) for k, v in (heatmap.get("moves") or {}).items()
            }
            self.heat_dwell = {
                str(k): int(v) for k, v in (heatmap.get("dwell") or {}).items()
            }
            try:
                self._heat_ticks = int(heatmap.get("ticks", 0) or 0)
            except (TypeError, ValueError):
                self._heat_ticks = 0

        if day_summaries is not None:
            self.day_summaries = list(day_summaries)
            latest: date | None = None
            for s in day_summaries:
                raw = s.get("day") if isinstance(s, dict) else None
                if not raw:
                    continue
                try:
                    dd = date.fromisoformat(str(raw))
                except ValueError:
                    continue
                if latest is None or dd > latest:
                    latest = dd
            if latest is not None:
                self._last_summarised_day = latest

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
                    elif (it.source or "") == "mutter":
                        # Inner monologue (dialog channel's Mutter state) —
                        # adds narrative colour to the day recap.
                        line = (it.meta or {}).get("line", "")
                        if line:
                            bullets.append(
                                f"{it.ts.strftime('%H:%M')} {pname}（心想）{line}"
                            )

                # Behavior history (executor side)
                exec_ = getattr(agent, "behavior_executor", None)
                if exec_ is not None:
                    items = exec_.history_for(aid, limit=200) if hasattr(exec_, "history_for") else []
                    for h in items:
                        if getattr(h, "ts", None) is None or h.ts.date() != summarised_day:
                            continue
                        if h.action_id in {"move", "talk", "interact", "mutter"}:
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
