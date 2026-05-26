"""Tiny SQLite wrapper. The memory schema lives in `agents/memory/store.py`;
runtime tables (behavior history, world snapshots, perceptions) live here.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

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

CREATE TABLE IF NOT EXISTS world_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_world_ts ON world_snapshots(ts);

CREATE TABLE IF NOT EXISTS agent_perceptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_perception_agent ON agent_perceptions(agent_id);
CREATE INDEX IF NOT EXISTS idx_perception_ts ON agent_perceptions(ts);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    # ----------- lifecycle -----------

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(RUNTIME_SCHEMA)
            await db.commit()

    # ----------- behavior history -----------

    async def append_behavior(self, record: dict[str, Any]) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO behavior_history(ts, agent_id, action_id, params, ok, note)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    record.get("ts") or datetime.utcnow().isoformat(),
                    record["agent_id"],
                    record["action_id"],
                    record.get("params") or "{}",
                    int(record.get("ok", 1)),
                    record.get("note") or "",
                ),
            )
            await db.commit()

    async def query_behavior(self, agent_id: str, limit: int = 100) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT ts, agent_id, action_id, params, ok, note"
                " FROM behavior_history WHERE agent_id = ?"
                " ORDER BY id DESC LIMIT ?",
                (agent_id, int(limit)),
            )
            rows = await cursor.fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            params_raw = r["params"] or "{}"
            try:
                params = json.loads(params_raw)
            except json.JSONDecodeError:
                params = {"_raw": params_raw}
            out.append({
                "ts": r["ts"],
                "agent_id": r["agent_id"],
                "action_id": r["action_id"],
                "params": params,
                "ok": bool(r["ok"]),
                "note": r["note"] or "",
            })
        return out

    # ----------- world snapshots -----------

    async def append_world_snapshot(self, payload: dict[str, Any]) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO world_snapshots(ts, payload_json) VALUES (?, ?)",
                (
                    payload.get("sim_time") or datetime.utcnow().isoformat(),
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            await db.commit()

    # ----------- agent perceptions -----------

    async def append_perception(self, agent_id: str, payload: dict[str, Any]) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO agent_perceptions(ts, agent_id, payload_json) VALUES (?, ?, ?)",
                (
                    payload.get("ts") or datetime.utcnow().isoformat(),
                    agent_id,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            await db.commit()
