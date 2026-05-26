"""Memory retrieval for decision-making.

Process:
1. Load **all** STM (cheap).
2. Retrieve LTM by relevance to the query context.
3. Pick top-5 across the union.
4. For each picked item, increment its `hit_count` (which biases compression
   priority).

Relevance scoring is intentionally pluggable: default = naive keyword overlap;
swap in an embedding-based reranker later without changing the call site.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .long_term import LongTermItem, LongTermMemory
from .short_term import ShortTermItem, ShortTermMemory


@dataclass
class RetrievedMemory:
    text: str
    score: float
    tier: str  # "STM" or "LTM"
    source_id: str


class MemoryRetriever:
    def __init__(self, stm: ShortTermMemory, ltm: LongTermMemory) -> None:
        self.stm = stm
        self.ltm = ltm

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievedMemory]:
        """Pick top-k memory items most relevant to `query`."""
        candidates: list[tuple[float, str, str, str]] = []
        for it in self.stm.all():
            candidates.append((self._score(query, it.text), it.text, "STM", it.id))
        for it in self.ltm.all():
            candidates.append((self._score(query, it.text), it.text, "LTM", it.id))

        candidates.sort(key=lambda x: x[0], reverse=True)
        picked = candidates[:top_k]

        for _, _, tier, sid in picked:
            if tier == "STM":
                self.stm.bump_hit(sid)
            else:
                self.ltm.bump_hit(sid)

        return [RetrievedMemory(text=t, score=s, tier=tier, source_id=sid)
                for s, t, tier, sid in picked]

    @staticmethod
    def _score(query: str, text: str) -> float:
        # Placeholder: token-overlap. Replace with embeddings later.
        q = set(query.lower().split())
        t = set(text.lower().split())
        if not q or not t:
            return 0.0
        return len(q & t) / len(q | t)
