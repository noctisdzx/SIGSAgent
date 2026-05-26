"""Narrative memory graph: schedule items recorded as (subject, predicate, object) triplets.

NOT used during NPC decision-making. Purpose:
- summarize a day's events per agent for the player's view;
- supply structured material for downstream narrative LLM passes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from app.llm.adapter import LLMAdapter


@dataclass
class Triplet:
    id: str
    subject: str
    predicate: str
    obj: str
    ts: datetime
    location_uid: str | None = None
    tone: str | None = None
    meta: dict = field(default_factory=dict)


class MemoryGraph:
    def __init__(self) -> None:
        self._triplets: list[Triplet] = []

    def add(self, t: Triplet) -> None:
        self._triplets.append(t)

    def all(self) -> list[Triplet]:
        return list(self._triplets)

    def by_subject(self, subject: str) -> list[Triplet]:
        return [t for t in self._triplets if t.subject == subject]

    def by_day(self, day: str) -> list[Triplet]:
        return [t for t in self._triplets if t.ts.date().isoformat() == day]

    def load(self, items: Iterable[Triplet]) -> None:
        self._triplets = list(items)

    def to_dict_list(self) -> list[dict]:
        """JSON-friendly snapshot for REST/WS responses."""
        return [
            {
                "id": t.id,
                "subject": t.subject,
                "predicate": t.predicate,
                "object": t.obj,
                "ts": t.ts.isoformat(),
                "location_uid": t.location_uid,
                "tone": t.tone,
                "meta": dict(t.meta),
            }
            for t in self._triplets
        ]

    async def extract_from_events(
        self,
        agent_id: str,
        events: list[str],
        llm: "LLMAdapter",
    ) -> list[Triplet]:
        """Ask the LLM to extract triplets and append them to the graph.

        On any failure (bad JSON, network), append nothing and return [];
        callers wishing to capture degradation should wrap in `safe_call`.
        """
        if not events:
            return []
        try:
            raw_triplets = await llm.extract_triplets(agent_id, events)
        except Exception:
            return []

        added: list[Triplet] = []
        now = datetime.utcnow()
        for raw in raw_triplets:
            if not isinstance(raw, dict):
                continue
            subj = raw.get("subject")
            pred = raw.get("predicate")
            obj = raw.get("object")
            if not (isinstance(subj, str) and isinstance(pred, str) and isinstance(obj, str)):
                continue
            t = Triplet(
                id=f"trp_{uuid.uuid4().hex[:8]}",
                subject=subj,
                predicate=pred,
                obj=obj,
                ts=now,
                location_uid=raw.get("location_uid"),
                tone=raw.get("tone"),
                meta={k: v for k, v in raw.items()
                      if k not in {"subject", "predicate", "object", "location_uid", "tone"}},
            )
            self.add(t)
            added.append(t)
        return added

    def to_dict(self) -> dict[str, Any]:
        """Convenience: graph snapshot as `{"triplets": [...]}`."""
        return {"triplets": self.to_dict_list()}
