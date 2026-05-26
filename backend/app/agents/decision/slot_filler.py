"""Chooses which generic Fragment to insert into a timeline gap.

Pipeline:
1. Take an empty gap (start_idx, end_idx) from `DailyTimeline.gaps()`.
2. Load persona + retrieved memories.
3. Ask LLM to pick a Fragment whose `duration_minutes <= gap_minutes`
   and is most consistent with persona + recent memory.
4. Fallback when LLM fails: weighted random over fitting fragments,
   weighted by persona's `favorite_tags` overlap.

A small in-memory LRU keyed on `(persona_id, hash(memories), gap_minutes)`
suppresses duplicate calls within a single tick — the sim loop may resolve
many gaps for the same agent in immediate succession.
"""

from __future__ import annotations

import hashlib
import random
from collections import OrderedDict
from dataclasses import dataclass

from app.agents.memory.retriever import RetrievedMemory
from app.agents.schedule.fragments import Fragment, FragmentLibrary
from app.llm.adapter import LLMAdapter


CACHE_SIZE = 64


@dataclass
class SlotFillChoice:
    fragment: Fragment
    rationale: str
    degraded: bool = False


def _memories_signature(memories: list[RetrievedMemory] | list[str]) -> str:
    """Stable hash of the memory texts (order-sensitive)."""
    h = hashlib.sha1()
    for m in memories:
        text = m.text if isinstance(m, RetrievedMemory) else str(m)
        h.update(text.encode("utf-8"))
        h.update(b"\x1e")
    return h.hexdigest()[:16]


class SlotFiller:
    def __init__(self, library: FragmentLibrary, llm: LLMAdapter) -> None:
        self.library = library
        self.llm = llm
        self._cache: "OrderedDict[tuple[str, str, int], SlotFillChoice]" = OrderedDict()

    async def fill(
        self,
        gap_minutes: int,
        persona: dict,
        memories: list[RetrievedMemory] | list[str],
        context: dict | None = None,
    ) -> SlotFillChoice | None:
        """Pick a fragment to fill `gap_minutes` of empty schedule.

        `context` may include `sim_time`, `weekday`, `here_uid`, `visible_agents`,
        `visible_items`, `last_activity` — these are forwarded to the LLM so it
        can reason about the actual situation (e.g. prefer a social fragment
        when someone is nearby).
        """
        candidates = self.library.fits(gap_minutes)
        if not candidates:
            return None

        persona_id = persona.get("id", "<unknown>")
        # cache key includes a context signature so different situations don't
        # collide (e.g. same persona+memories but different visible agents).
        ctx_sig = _memories_signature([str(sorted((context or {}).items()))])
        cache_key = (persona_id, _memories_signature(memories) + ctx_sig, int(gap_minutes))
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._cache.move_to_end(cache_key)
            return cached

        mem_texts: list[str] = [
            m.text if isinstance(m, RetrievedMemory) else str(m) for m in memories
        ]

        try:
            choice_id, rationale = await self.llm.choose_fragment(
                gap_minutes=gap_minutes,
                persona=persona,
                memories=mem_texts,
                candidates=[
                    {"id": f.id, "label": f.label, "tags": f.tags}
                    for f in candidates
                ],
                context=context,
            )
            chosen = next((f for f in candidates if f.id == choice_id), None)
            if chosen is None:
                raise ValueError("LLM returned unknown fragment id")
            choice = SlotFillChoice(fragment=chosen, rationale=rationale)
        except Exception:
            choice = SlotFillChoice(
                fragment=self._weighted_random(candidates, persona, context=context),
                rationale="fallback: weighted random over fitting fragments",
                degraded=True,
            )

        self._cache_put(cache_key, choice)
        return choice

    # ----- internals -----

    def _cache_put(self, key, value: SlotFillChoice) -> None:
        self._cache[key] = value
        self._cache.move_to_end(key)
        while len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)

    def clear_cache(self) -> None:
        self._cache.clear()

    @staticmethod
    def _weighted_random(candidates: list[Fragment], persona: dict,
                         context: dict | None = None) -> Fragment:
        favs = set(persona.get("preferences", {}).get("favorite_tags", []))
        visible = set((context or {}).get("visible_agents", []) or [])
        weights = []
        for f in candidates:
            w = 1 + len(favs & set(f.tags))
            # social-tagged fragment gets a bump if someone is nearby
            if visible and ("social" in (f.tags or []) or "chat" in (f.tags or [])):
                w += 2
            weights.append(w)
        return random.choices(candidates, weights=weights, k=1)[0]
