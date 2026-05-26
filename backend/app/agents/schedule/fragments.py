"""Generic schedule fragments — the pool that fills template gaps.

Granularity matches the sim's 5-min tick.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Fragment:
    id: str
    label: str
    duration_minutes: int
    tags: list[str] = field(default_factory=list)
    preferred_location_uids: list[str] = field(default_factory=list)
    cost: int = 0
    preconditions: dict = field(default_factory=dict)


class FragmentLibrary:
    def __init__(self, fragments: list[Fragment]) -> None:
        self._by_id: dict[str, Fragment] = {f.id: f for f in fragments}

    @classmethod
    def from_json(cls, path: Path) -> "FragmentLibrary":
        raw = json.loads(path.read_text(encoding="utf-8"))
        fragments = [Fragment(**f) for f in raw.get("fragments", [])]
        return cls(fragments)

    def get(self, fid: str) -> Fragment:
        return self._by_id[fid]

    def all(self) -> list[Fragment]:
        return list(self._by_id.values())

    def fits(self, duration_minutes: int) -> list[Fragment]:
        return [f for f in self._by_id.values() if f.duration_minutes <= duration_minutes]
