"""Per-tick playback recorder.

Writes one JSONL file per run session under ``runtime/recordings/``. The first
line is a header; every subsequent line is a frame::

    {"kind": "header", "ts_real": "...", "meta": {...}}
    {"kind": "frame", "index": 0, "sim_time": "...", "world": {...}, "events": [...]}
    ...

The recorder registers a *tap* on the event bus so it captures the complete
per-tick event stream (dialog / behavior / insert_event / tick / …) without the
lossy 200-event ring buffer. ``write_frame`` then pairs the world snapshot with
the events emitted since the previous frame.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("sigs.recorder")


class Recorder:
    def __init__(self, out_dir: Path, enabled: bool = True) -> None:
        self.out_dir = Path(out_dir)
        self.enabled = enabled
        self._pending: list[dict[str, Any]] = []
        self._fh = None
        self.path: Path | None = None
        self.frame_count = 0
        self.started_at: str | None = None

    # --- event-bus tap (synchronous, never drops) ---
    def tap(self, event: dict[str, Any]) -> None:
        if self.enabled:
            self._pending.append(event)

    # --- session lifecycle ---
    def start_session(self, meta: dict[str, Any] | None = None) -> None:
        if not self.enabled:
            return
        self.out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = self.out_dir / f"rec_{stamp}.jsonl"
        self._fh = self.path.open("w", encoding="utf-8")
        self.started_at = stamp
        self.frame_count = 0
        header = {
            "kind": "header",
            "ts_real": datetime.utcnow().isoformat(),
            "meta": meta or {},
        }
        self._fh.write(json.dumps(header, ensure_ascii=False) + "\n")
        self._fh.flush()
        log.info("recording session -> %s", self.path)

    def write_frame(self, index: int, sim_time: str, world: dict[str, Any]) -> None:
        if not self.enabled or self._fh is None:
            return
        events = self._pending
        self._pending = []
        frame = {
            "kind": "frame",
            "index": index,
            "sim_time": sim_time,
            "world": world,
            "events": events,
        }
        self._fh.write(json.dumps(frame, ensure_ascii=False) + "\n")
        self._fh.flush()
        self.frame_count += 1

    def close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            except Exception:
                pass
            self._fh = None
