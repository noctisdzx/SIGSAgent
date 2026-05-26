"""Tiny SQLite wrapper. The memory schema lives in `agents/memory/store.py`;
runtime tables (behavior history, world snapshots metadata, etc.) live here.
"""

from __future__ import annotations

from pathlib import Path

import aiosqlite


RUNTIME_SCHEMA = """
CREATE TABLE IF NOT EXISTS behavior_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    params TEXT,
    ok INTEGER NOT NULL DEFAULT 1,
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_history_agent ON behavior_history(agent_id);
CREATE INDEX IF NOT EXISTS idx_history_ts ON behavior_history(ts);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(RUNTIME_SCHEMA)
            await db.commit()
