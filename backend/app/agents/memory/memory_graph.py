"""Narrative memory graph: schedule items recorded as (subject, predicate, object) triplets.

NOT used during NPC decision-making. Purpose:
- summarize a day's events per agent for the player's view;
- supply structured material for downstream narrative LLM passes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable


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
