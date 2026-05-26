"""Item catalog & status machine (placeholder)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ItemSpec:
    id: str
    label: str
    default_status: str = "idle"
    allowed_status: list[str] | None = None
    extra: dict[str, Any] | None = None


class ItemCatalog:
    def __init__(self) -> None:
        self._specs: dict[str, ItemSpec] = {}

    def register(self, spec: ItemSpec) -> None:
        self._specs[spec.id] = spec

    def get(self, item_id: str) -> ItemSpec:
        return self._specs[item_id]
