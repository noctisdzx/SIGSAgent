"""Per-tick orchestration: advance sim time, then each agent perceives→decides→acts.

Also detects midnight rollover and asks the LLM for an omniscient narrator
day summary, then auto-pauses so the player can read it before opting into
the next day via /api/sim/start.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
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
        # Weekly per-agent space evaluations (in-memory, regenerated each week).
        self.week_summaries: list[dict[str, Any]] = []
        self._last_week_summarised: int | None = None
        self._busy_week: bool = False
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

        # Midnight rollover → kick off the day summary in the BACKGROUND and keep
        # ticking (no auto-pause anymore). The frontend pops a replaceable modal
        # once the `day_summary` event arrives. Only once per sim-day.
        if new_day != prev_day and self._last_summarised_day != prev_day:
            self._last_summarised_day = prev_day
            asyncio.create_task(self._safe_day_summary(prev_day))
            # ISO-week rollover → per-agent weekly space evaluation (also async).
            try:
                prev_week = prev_day.isocalendar()[1]
                new_week = new_day.isocalendar()[1]
            except Exception:
                prev_week, new_week = 0, 0
            crossed_week = prev_week != new_week or (new_day - prev_day).days >= 7
            if crossed_week and self._last_week_summarised != prev_week:
                self._last_week_summarised = prev_week
                asyncio.create_task(self._safe_week_summary(prev_day))
            # NOTE: intentionally NOT pausing/returning — fall through to tick
            # the new day normally.

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

    async def _safe_day_summary(self, day: date) -> None:
        """Background-task wrapper: never let a summary failure crash the loop."""
        try:
            await self._do_day_summary(day)
        except Exception as exc:
            log.exception("day summary failed for %s: %s", day, exc)

    # ----- weekly space evaluation -----

    async def _safe_week_summary(self, week_end_day: date) -> None:
        try:
            await self._do_week_summary(week_end_day)
        except Exception as exc:
            log.exception("week summary failed (end=%s): %s", week_end_day, exc)

    def _room_name(self, uid: str | None) -> str:
        if uid and self.scene is not None and self.scene.has(uid):
            return self.scene.get(uid).name
        return ""

    def _build_agent_week_context(
        self, aid: str, agent: Any, week_start: date, week_end: date
    ) -> dict[str, Any]:
        """Gather an agent's FULL week-relevant data — persona, personality,
        preferences, memory (STM + LTM), dialogs and frequented places — into a
        compact dict for the space-evaluation prompt."""
        persona = getattr(agent, "persona", None)
        name = getattr(persona, "name", aid)
        name_en = getattr(persona, "name_en", "") or name
        role = getattr(persona, "role", "") or ""
        personality = dict(getattr(persona, "personality", {}) or {})
        preferences = dict(getattr(persona, "preferences", {}) or {})
        profile = dict(getattr(persona, "profile", {}) or {}) if getattr(persona, "profile", None) else {}

        def _in_week(d: date) -> bool:
            return week_start <= d <= week_end

        mem_lines: list[str] = []
        dialog_lines: list[str] = []
        stm_items = getattr(getattr(agent, "stm", None), "all", lambda: [])()
        for it in stm_items:
            ts = getattr(it, "ts", None)
            if ts is None or not _in_week(ts.date()):
                continue
            src = (getattr(it, "source", "") or "")
            meta = getattr(it, "meta", {}) or {}
            if src.startswith("dialog:"):
                partner = meta.get("partner_name", "?")
                line = meta.get("line", "")
                reply = meta.get("reply", "")
                if line:
                    dialog_lines.append(f"与{partner}：“{line}” / “{reply}”")
            elif src == "mutter":
                line = meta.get("line", "")
                if line:
                    mem_lines.append(f"（独白）{line}")
            else:
                txt = (getattr(it, "text", "") or "").strip()
                if txt:
                    mem_lines.append(txt)

        ltm_lines: list[str] = []
        for it in getattr(getattr(agent, "ltm", None), "all", lambda: [])():
            t = (getattr(it, "text", "") or "").strip()
            if t:
                ltm_lines.append(t)

        visited: dict[str, int] = {}
        exec_ = getattr(agent, "behavior_executor", None)
        if exec_ is not None and hasattr(exec_, "history_for"):
            for h in exec_.history_for(aid, limit=500):
                ts = getattr(h, "ts", None)
                if ts is None or not _in_week(ts.date()):
                    continue
                for v in (getattr(h, "params", {}) or {}).values():
                    if isinstance(v, str):
                        nm = self._room_name(v)
                        if nm:
                            visited[nm] = visited.get(nm, 0) + 1

        here_name = self._room_name(getattr(agent, "location_uid", None))
        if here_name:
            visited.setdefault(here_name, visited.get(here_name, 0))

        visited_top = sorted(visited.items(), key=lambda kv: kv[1], reverse=True)[:8]
        has_data = bool(mem_lines or dialog_lines or ltm_lines or visited_top)

        return {
            "id": aid,
            "name": name,
            "name_en": name_en,
            "role": role,
            "personality": personality,
            "preferences": preferences,
            "profile": profile,
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "here": here_name,
            "visited": [{"name": n, "count": c} for n, c in visited_top],
            "memories": mem_lines[-20:],
            "dialogs": dialog_lines[-12:],
            "long_term": ltm_lines[:10],
            "has_data": has_data,
        }

    def _degraded_space_eval(self, ctx: dict[str, Any]) -> dict[str, Any]:
        visited = ctx.get("visited") or []
        fav = visited[0]["name"] if visited else (ctx.get("here") or "")
        return {
            "evaluation_zh": (
                f"本周{ctx.get('name', '这位居民')}主要活动于"
                f"{fav or '校园各处'}，对当前空间整体感受平稳。（LLM 降级中，占位评价。）"
            ),
            "evaluation_en": (
                f"This week {ctx.get('name_en') or 'they'} mostly stayed around "
                f"{fav or 'the campus'}; overall the space felt fine. "
                "(LLM degraded placeholder.)"
            ),
            "favorite_place": fav,
            "wants": [],
            "pain_points": [],
            "degraded": True,
        }

    async def _do_week_summary(self, week_end_day: date) -> None:
        """For every agent, ask the LLM to evaluate the architectural space using
        the agent's full data (persona/personality/preferences + memory + visited
        places), surfacing wishes ("想要的新功能") and pain points ("感受不好的
        地方"). Publishes a `week_summary` WS event."""
        if self._busy_week:
            return
        self._busy_week = True
        try:
            week_start = week_end_day - timedelta(days=6)
            week_label = f"{week_start.isoformat()} ~ {week_end_day.isoformat()}"
            log.info("Generating weekly space evaluation for %s ...", week_label)

            sem = asyncio.Semaphore(max(1, get_settings().sim_tick_concurrency))
            fn = getattr(self.llm, "evaluate_space", None) if self.llm is not None else None
            agents_out: list[dict[str, Any]] = []

            async def _eval_one(aid: str, agent: Any) -> None:
                async with sem:
                    ctx = self._build_agent_week_context(aid, agent, week_start, week_end_day)
                    ev: dict[str, Any] | None = None
                    if fn is not None and ctx.get("has_data"):
                        try:
                            ev = await fn(ctx)
                        except Exception as exc:
                            log.warning("evaluate_space failed for %s: %s", aid, exc)
                    if not ev:
                        ev = self._degraded_space_eval(ctx)
                    agents_out.append({
                        "id": aid,
                        "name": ctx.get("name"),
                        "name_en": ctx.get("name_en"),
                        "role": ctx.get("role"),
                        "favorite_place": ev.get("favorite_place", ""),
                        "evaluation_zh": ev.get("evaluation_zh", ""),
                        "evaluation_en": ev.get("evaluation_en", ""),
                        "wants": ev.get("wants", []) or [],
                        "pain_points": ev.get("pain_points", []) or [],
                        "degraded": bool(ev.get("degraded", False)),
                    })

            await asyncio.gather(*[_eval_one(aid, a) for aid, a in list(self.agents.items())])
            agents_out.sort(key=lambda x: str(x.get("name") or x.get("id")))

            entry = {
                "week": week_label,
                "week_start": week_start.isoformat(),
                "week_end": week_end_day.isoformat(),
                "ts_real": datetime.utcnow().isoformat(),
                "ts_sim": self.world.sim_time.isoformat(),
                "n_agents": len(agents_out),
                "agents": agents_out,
            }
            self.week_summaries.append(entry)
            if len(self.week_summaries) > 26:
                self.week_summaries = self.week_summaries[-26:]

            await event_bus.publish({
                "type": "week_summary",
                "ts_sim": self.world.sim_time.isoformat(),
                "agent_id": None,
                "payload": entry,
            })
            log.info("Weekly evaluation for %s ready (%d agents)", week_label, len(agents_out))
        finally:
            self._busy_week = False
