"""Long-Term Memory (LTM).

Rules:
- Capacity: 15 items.
- Each item carries a `hit_count`.
- When STM compression has < 5 free LTM slots, the *bottom 3* LTM items
  (by hit_count asc, then ts asc) are themselves compressed into 1 to
  free space, then the STM compression proceeds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable


LTM_CAPACITY = 15
LTM_FREE_SLOT_THRESHOLD = 5
LTM_BOTTOM_COMPRESS_COUNT = 3


@dataclass
class LongTermItem:
    id: str
    text: str
    ts: datetime
    source_ids: list[str] = field(default_factory=list)  # which STM/LTM items merged in
    hit_count: int = 0
    degraded: bool = False  # True if produced by fallback (not LLM)
    meta: dict = field(default_factory=dict)


class LongTermMemory:
    def __init__(self, capacity: int = LTM_CAPACITY) -> None:
        self.capacity = capacity
        self._items: list[LongTermItem] = []

    # ----- mutation -----

    def add(self, item: LongTermItem) -> None:
        self._items.append(item)

    def replace(self, drop_ids: list[str], new_item: LongTermItem) -> None:
        self._items = [it for it in self._items if it.id not in drop_ids]
        self._items.append(new_item)

    def bump_hit(self, item_id: str) -> None:
        for it in self._items:
            if it.id == item_id:
                it.hit_count += 1
                return

    # ----- queries -----

    def all(self) -> list[LongTermItem]:
        return list(self._items)

    def free_slots(self) -> int:
        return max(0, self.capacity - len(self._items))

    def bottom(self, n: int = LTM_BOTTOM_COMPRESS_COUNT) -> list[LongTermItem]:
        """Lowest-priority items: hit_count asc, ts asc."""
        return sorted(self._items, key=lambda x: (x.hit_count, x.ts))[:n]

    def size(self) -> int:
        return len(self._items)

    def load(self, items: Iterable[LongTermItem]) -> None:
        self._items = list(items)

    def to_dict_list(self) -> list[dict]:
        """JSON-friendly snapshot for REST/WS responses."""
        return [
            {
                "id": it.id,
                "text": it.text,
                "ts": it.ts.isoformat(),
                "source_ids": list(it.source_ids),
                "hit_count": it.hit_count,
                "degraded": it.degraded,
                "meta": dict(it.meta),
            }
            for it in self._items
        ]
