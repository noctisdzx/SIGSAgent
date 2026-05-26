"""SQLite persistence for memory (STM / LTM / graph / hits)."""

from __future__ import annotations

from pathlib import Path

import aiosqlite


SCHEMA = """
CREATE TABLE IF NOT EXISTS stm (
    agent_id TEXT NOT NULL,
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    ts TEXT NOT NULL,
    source TEXT NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 0,
    meta TEXT
);

CREATE TABLE IF NOT EXISTS ltm (
    agent_id TEXT NOT NULL,
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    ts TEXT NOT NULL,
    source_ids TEXT NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 0,
    degraded INTEGER NOT NULL DEFAULT 0,
    meta TEXT
);

CREATE TABLE IF NOT EXISTS mem_graph (
    agent_id TEXT NOT NULL,
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    ts TEXT NOT NULL,
    location_uid TEXT,
    tone TEXT,
    meta TEXT
);

CREATE INDEX IF NOT EXISTS idx_stm_agent ON stm(agent_id);
CREATE INDEX IF NOT EXISTS idx_ltm_agent ON ltm(agent_id);
CREATE INDEX IF NOT EXISTS idx_graph_agent ON mem_graph(agent_id);
"""


class MemoryStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    async def initialize(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(SCHEMA)
            await db.commit()

    async def upsert_stm(self, agent_id: str, items: list[dict]) -> None:
        raise NotImplementedError

    async def upsert_ltm(self, agent_id: str, items: list[dict]) -> None:
        raise NotImplementedError

    async def append_graph(self, agent_id: str, triplets: list[dict]) -> None:
        raise NotImplementedError

    async def load_all(self, agent_id: str) -> dict:
        raise NotImplementedError
