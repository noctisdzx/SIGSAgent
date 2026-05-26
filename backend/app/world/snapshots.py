"""Periodic WorldState snapshots to `runtime/snapshots/`."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .world_state import WorldState


class SnapshotWriter:
    def __init__(self, out_dir: Path) -> None:
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def write(self, world: WorldState) -> Path:
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        path = self.out_dir / f"world_{ts}.json"
        path.write_text(json.dumps(world.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path
