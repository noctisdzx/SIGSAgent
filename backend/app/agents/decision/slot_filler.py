"""Chooses which generic Fragment to insert into a timeline gap.

Pipeline:
1. Take an empty gap (start_idx, end_idx) from `DailyTimeline.gaps()`.
2. Load persona + retrieved memories.
3. Ask LLM to pick a Fragment whose `duration_minutes <= gap_minutes`
   and is most consistent with persona + recent memory.
4. Fallback when LLM fails: weighted random over fitting fragments,
   weighted by persona's `favorite_tags` overlap.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from app.agents.memory.retriever import RetrievedMemory
from app.agents.schedule.fragments import Fragment, FragmentLibrary
from app.llm.adapter import LLMAdapter


@dataclass
class SlotFillChoice:
    fragment: Fragment
    rationale: str
    degraded: bool = False


class SlotFiller:
    def __init__(self, library: FragmentLibrary, llm: LLMAdapter) -> None:
        self.library = library
        self.llm = llm

    async def fill(
        self,
        gap_minutes: int,
        persona: dict,
        memories: list[RetrievedMemory],
    ) -> SlotFillChoice | None:
        candidates = self.library.fits(gap_minutes)
        if not candidates:
            return None

        try:
            choice_id, rationale = await self.llm.choose_fragment(
                gap_minutes=gap_minutes,
                persona=persona,
                memories=[m.text for m in memories],
                candidates=[{"id": f.id, "label": f.label, "tags": f.tags} for f in candidates],
            )
            chosen = next((f for f in candidates if f.id == choice_id), None)
            if chosen is None:
                raise ValueError("LLM returned unknown fragment id")
            return SlotFillChoice(fragment=chosen, rationale=rationale)
        except Exception:
            return SlotFillChoice(
                fragment=self._weighted_random(candidates, persona),
                rationale="fallback: weighted random over fitting fragments",
                degraded=True,
            )

    @staticmethod
    def _weighted_random(candidates: list[Fragment], persona: dict) -> Fragment:
        favs = set(persona.get("preferences", {}).get("favorite_tags", []))
        weights = [1 + len(favs & set(f.tags)) for f in candidates]
        return random.choices(candidates, weights=weights, k=1)[0]
