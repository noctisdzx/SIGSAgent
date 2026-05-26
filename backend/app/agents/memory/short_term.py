"""Short-Term Memory (STM).

Rules:
- Capacity: 30 items.
- Each item carries a `hit_count`.
- Sorting on retrieval / compression: hit_count desc, then `ts` desc (newer first).
- Source: every confirmed schedule item is converted into 1 STM entry by
  `agents/schedule/builder.py`.
- When capacity overflows, `MemoryCompressor` is invoked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable


STM_CAPACITY = 30


@dataclass
class ShortTermItem:
    id: str
    text: str
    ts: datetime
    source: str  # e.g. "schedule:<schedule_item_id>"
    hit_count: int = 0
    meta: dict = field(default_factory=dict)


class ShortTermMemory:
    def __init__(self, capacity: int = STM_CAPACITY) -> None:
        self.capacity = capacity
        self._items: list[ShortTermItem] = []

    # ----- mutation -----

    def add(self, item: ShortTermItem) -> bool:
        """Returns True iff capacity was exceeded after add (caller should compress)."""
        self._items.append(item)
        return len(self._items) > self.capacity

    def bump_hit(self, item_id: str) -> None:
        for it in self._items:
            if it.id == item_id:
                it.hit_count += 1
                return

    def drop_oldest(self, n: int) -> list[ShortTermItem]:
        """Drop n items with the *lowest* (hit_count, ts) — the "back 20" of the spec."""
        ordered = self.sorted_for_compress()
        keep = ordered[: max(0, len(ordered) - n)]
        dropped = ordered[len(keep):]
        self._items = keep
        return dropped

    # ----- queries -----

    def all(self) -> list[ShortTermItem]:
        return list(self._items)

    def sorted_for_compress(self) -> list[ShortTermItem]:
        """hit_count desc, ts desc."""
        return sorted(self._items, key=lambda x: (x.hit_count, x.ts), reverse=True)

    def top_for_compress(self, n: int = 10) -> list[ShortTermItem]:
        return self.sorted_for_compress()[:n]

    def size(self) -> int:
        return len(self._items)

    def load(self, items: Iterable[ShortTermItem]) -> None:
        self._items = list(items)

    def to_dict_list(self) -> list[dict]:
        """JSON-friendly snapshot for REST/WS responses."""
        return [
            {
                "id": it.id,
                "text": it.text,
                "ts": it.ts.isoformat(),
                "source": it.source,
                "hit_count": it.hit_count,
                "meta": dict(it.meta),
            }
            for it in self._items
        ]
