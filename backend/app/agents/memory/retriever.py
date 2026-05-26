"""Memory retrieval for decision-making.

Process:
1. Load **all** STM (cheap).
2. Retrieve LTM by relevance to the query context.
3. Pick top-k across the union.
4. For each picked item, increment its `hit_count` (which biases compression
   priority).

Relevance scoring is intentionally pluggable: default = naive token / char
bigram overlap with a small recency boost; swap in an embedding-based
reranker later without changing the call site.

Chinese-friendly note: when the query has no whitespace tokens (typical in
Chinese), we fall back to character bigrams so 中文 queries score sensibly
without taking on a `jieba` dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .long_term import LongTermMemory
from .short_term import ShortTermMemory


@dataclass
class RetrievedMemory:
    text: str
    score: float
    tier: str  # "STM" or "LTM"
    source_id: str


class MemoryRetriever:
    def __init__(
        self,
        stm: ShortTermMemory,
        ltm: LongTermMemory,
        boost_recent: float = 0.1,
    ) -> None:
        self.stm = stm
        self.ltm = ltm
        # Additional score bonus that decays with age (linear from 0..boost_recent
        # for the most-recent..oldest item in the candidate pool). Only used as
        # a tie-breaker; the main signal is overlap.
        self.boost_recent = boost_recent

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievedMemory]:
        """Pick top-k memory items most relevant to `query`."""
        rows: list[tuple[float, datetime, str, str, str]] = []  # score, ts, text, tier, sid
        for it in self.stm.all():
            rows.append((self._score(query, it.text), it.ts, it.text, "STM", it.id))
        for it in self.ltm.all():
            rows.append((self._score(query, it.text), it.ts, it.text, "LTM", it.id))

        if not rows:
            return []

        # Recency bonus: linear from 0 (oldest) to boost_recent (newest).
        ts_values = [r[1] for r in rows]
        oldest = min(ts_values)
        newest = max(ts_values)
        span = (newest - oldest).total_seconds() if newest != oldest else 0.0
        boosted: list[tuple[float, datetime, str, str, str]] = []
        for s, ts, text, tier, sid in rows:
            if self.boost_recent > 0.0 and span > 0.0:
                age = (newest - ts).total_seconds()
                bonus = self.boost_recent * (1.0 - age / span)
            else:
                bonus = 0.0
            boosted.append((s + bonus, ts, text, tier, sid))

        # Sort by total score desc, then ts desc.
        boosted.sort(key=lambda x: (x[0], x[1]), reverse=True)
        picked = boosted[:top_k]

        for _, _, _, tier, sid in picked:
            if tier == "STM":
                self.stm.bump_hit(sid)
            else:
                self.ltm.bump_hit(sid)

        return [
            RetrievedMemory(text=t, score=round(s, 4), tier=tier, source_id=sid)
            for s, _ts, t, tier, sid in picked
        ]

    # ----- scoring -----

    def _score(self, query: str, text: str) -> float:
        """Token overlap (Jaccard); falls back to char-bigram Jaccard for
        whitespace-free / Chinese queries.
        """
        q_norm = (query or "").lower()
        t_norm = (text or "").lower()
        if not q_norm or not t_norm:
            return 0.0

        q_tokens = set(q_norm.split())
        t_tokens = set(t_norm.split())
        # If the query is plainly tokenizable on whitespace and at least 2 tokens,
        # use word Jaccard; else try char bigrams to cover Chinese-style queries.
        if len(q_tokens) >= 2:
            inter = len(q_tokens & t_tokens)
            union = len(q_tokens | t_tokens) or 1
            return inter / union

        q_bi = _bigrams(q_norm)
        t_bi = _bigrams(t_norm)
        if not q_bi:
            return 0.0
        inter = len(q_bi & t_bi)
        union = len(q_bi | t_bi) or 1
        return inter / union


def _bigrams(s: str) -> set[str]:
    s = "".join(ch for ch in s if not ch.isspace())
    if len(s) < 2:
        return set([s] if s else [])
    return {s[i : i + 2] for i in range(len(s) - 1)}


__all__ = ["MemoryRetriever", "RetrievedMemory"]
