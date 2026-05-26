"""SQLite persistence for memory (STM / LTM / graph).

Used at boot to seed STM/triplets from `data/memory_seed.json` and during
shutdown / periodic checkpoints to persist the live state of every agent.
All operations are async via `aiosqlite`; rows are dataclass-ish dicts so
the in-memory representation in `short_term.py` / `long_term.py` /
`memory_graph.py` stays the source of truth.

Schema is forward-only: `idx_stm/ltm/graph_agent` indexes on `agent_id`,
PKs on `id` so upserts are cheap. A composite secondary key
`(agent_id, id)` is implicit since `id` is already unique per agent in
practice (we generate them with `uuid.uuid4().hex[:8]`).
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import aiosqlite

from .long_term import LongTermItem
from .memory_graph import Triplet
from .short_term import ShortTermItem


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


# ---------------------------------------------------------------------------
# Internal converters
# ---------------------------------------------------------------------------
def _stm_to_row(agent_id: str, item: ShortTermItem) -> tuple:
    return (
        agent_id,
        item.id,
        item.text,
        item.ts.isoformat(),
        item.source,
        int(item.hit_count),
        json.dumps(item.meta or {}, ensure_ascii=False),
    )


def _row_to_stm(row: aiosqlite.Row) -> ShortTermItem:
    meta = json.loads(row["meta"]) if row["meta"] else {}
    return ShortTermItem(
        id=row["id"],
        text=row["text"],
        ts=datetime.fromisoformat(row["ts"]),
        source=row["source"],
        hit_count=int(row["hit_count"] or 0),
        meta=meta,
    )


def _ltm_to_row(agent_id: str, item: LongTermItem) -> tuple:
    return (
        agent_id,
        item.id,
        item.text,
        item.ts.isoformat(),
        json.dumps(list(item.source_ids), ensure_ascii=False),
        int(item.hit_count),
        1 if item.degraded else 0,
        json.dumps(item.meta or {}, ensure_ascii=False),
    )


def _row_to_ltm(row: aiosqlite.Row) -> LongTermItem:
    meta = json.loads(row["meta"]) if row["meta"] else {}
    sids = json.loads(row["source_ids"]) if row["source_ids"] else []
    return LongTermItem(
        id=row["id"],
        text=row["text"],
        ts=datetime.fromisoformat(row["ts"]),
        source_ids=list(sids),
        hit_count=int(row["hit_count"] or 0),
        degraded=bool(row["degraded"]),
        meta=meta,
    )


def _trp_to_row(agent_id: str, t: Triplet) -> tuple:
    return (
        agent_id,
        t.id,
        t.subject,
        t.predicate,
        t.obj,
        t.ts.isoformat(),
        t.location_uid,
        t.tone,
        json.dumps(t.meta or {}, ensure_ascii=False),
    )


def _row_to_triplet(row: aiosqlite.Row) -> Triplet:
    meta = json.loads(row["meta"]) if row["meta"] else {}
    return Triplet(
        id=row["id"],
        subject=row["subject"],
        predicate=row["predicate"],
        obj=row["object"],
        ts=datetime.fromisoformat(row["ts"]),
        location_uid=row["location_uid"],
        tone=row["tone"],
        meta=meta,
    )


# ---------------------------------------------------------------------------
# Public store
# ---------------------------------------------------------------------------
class MemoryStore:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)

    async def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(SCHEMA)
            await db.commit()

    # ----- STM -----

    async def upsert_stm(self, agent_id: str, items: Iterable[ShortTermItem]) -> None:
        rows = [_stm_to_row(agent_id, it) for it in items]
        if not rows:
            return
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany(
                """INSERT INTO stm(agent_id, id, text, ts, source, hit_count, meta)
                   VALUES(?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     agent_id=excluded.agent_id,
                     text=excluded.text,
                     ts=excluded.ts,
                     source=excluded.source,
                     hit_count=excluded.hit_count,
                     meta=excluded.meta""",
                rows,
            )
            await db.commit()

    # ----- LTM -----

    async def upsert_ltm(self, agent_id: str, items: Iterable[LongTermItem]) -> None:
        rows = [_ltm_to_row(agent_id, it) for it in items]
        if not rows:
            return
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany(
                """INSERT INTO ltm(agent_id, id, text, ts, source_ids, hit_count, degraded, meta)
                   VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     agent_id=excluded.agent_id,
                     text=excluded.text,
                     ts=excluded.ts,
                     source_ids=excluded.source_ids,
                     hit_count=excluded.hit_count,
                     degraded=excluded.degraded,
                     meta=excluded.meta""",
                rows,
            )
            await db.commit()

    # ----- Graph -----

    async def append_graph(self, agent_id: str, triplets: Iterable[Triplet]) -> None:
        rows = [_trp_to_row(agent_id, t) for t in triplets]
        if not rows:
            return
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany(
                """INSERT OR IGNORE INTO mem_graph(
                       agent_id, id, subject, predicate, object,
                       ts, location_uid, tone, meta)
                   VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
            await db.commit()

    # ----- Loads -----

    async def load_all(self, agent_id: str) -> dict[str, list]:
        out: dict[str, list] = {"stm": [], "ltm": [], "graph": []}
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM stm WHERE agent_id=? ORDER BY ts",
                (agent_id,),
            ) as cur:
                async for row in cur:
                    out["stm"].append(_row_to_stm(row))
            async with db.execute(
                "SELECT * FROM ltm WHERE agent_id=? ORDER BY ts",
                (agent_id,),
            ) as cur:
                async for row in cur:
                    out["ltm"].append(_row_to_ltm(row))
            async with db.execute(
                "SELECT * FROM mem_graph WHERE agent_id=? ORDER BY ts",
                (agent_id,),
            ) as cur:
                async for row in cur:
                    out["graph"].append(_row_to_triplet(row))
        return out

    # ----- Seeding -----

    async def seed_from_memory_seed(
        self,
        memory_seed: dict[str, Any],
        persona_id: str,
        *,
        anchor_day: datetime | None = None,
    ) -> dict[str, int]:
        """Seed STM + triplets for a single persona from `data/memory_seed.json`.

        The JSON shape is `{persona_id: {memories: [...], triplets: [...]}}`,
        nested either directly or under `per_agent`. Each memory has
        `{text, tone, ts}`; `ts` is a relative anchor like `"T 07:05"` or
        `"T-1d 23:50"`. We resolve them against `anchor_day` (default = today
        midnight) so seeded items don't collide with live timestamps.
        """
        per_agent = memory_seed.get("per_agent", memory_seed) if isinstance(memory_seed, dict) else {}
        seed = per_agent.get(persona_id) if isinstance(per_agent, dict) else None
        if not seed:
            return {"stm": 0, "triplets": 0}

        anchor = anchor_day or datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        stm_items: list[ShortTermItem] = []
        for raw in seed.get("memories", []) or []:
            text = raw.get("text") or raw.get("text_en") or ""
            if not text:
                continue
            ts = _parse_seed_ts(raw.get("ts"), anchor)
            stm_items.append(
                ShortTermItem(
                    id=f"stm_seed_{uuid.uuid4().hex[:8]}",
                    text=text,
                    ts=ts,
                    source="seed",
                    meta={
                        "agent_id": persona_id,
                        "tone": raw.get("tone"),
                        "text_en": raw.get("text_en"),
                    },
                )
            )

        triplets: list[Triplet] = []
        for raw in seed.get("triplets", []) or []:
            subj = raw.get("subject")
            pred = raw.get("predicate")
            obj = raw.get("object")
            if not (isinstance(subj, str) and isinstance(pred, str) and isinstance(obj, str)):
                continue
            triplets.append(
                Triplet(
                    id=f"trp_seed_{uuid.uuid4().hex[:8]}",
                    subject=subj,
                    predicate=pred,
                    obj=obj,
                    ts=anchor,
                    location_uid=raw.get("location_uid"),
                    tone=raw.get("tone"),
                    meta={
                        "narrative_zh": raw.get("narrative_zh"),
                        "narrative_en": raw.get("narrative_en"),
                    },
                )
            )

        await self.upsert_stm(persona_id, stm_items)
        await self.append_graph(persona_id, triplets)
        return {"stm": len(stm_items), "triplets": len(triplets)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_TS_RE = re.compile(
    r"^\s*T\s*(?P<sign>[+-])?(?P<days>\d+)?(?:d)?\s*"
    r"(?:(?P<hh>\d{1,2}):(?P<mm>\d{2}))?\s*$",
    flags=re.IGNORECASE,
)


def _parse_seed_ts(raw: Any, anchor: datetime) -> datetime:
    """Parse seed `ts` strings like `"T 07:05"`, `"T-1d 23:50"`, or ISO.

    On any parse failure, fall back to `anchor`.
    """
    if isinstance(raw, datetime):
        return raw
    if not isinstance(raw, str):
        return anchor
    s = raw.strip()
    if not s:
        return anchor
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass

    m = _TS_RE.match(s)
    if not m:
        return anchor
    days = int(m.group("days") or 0)
    if (m.group("sign") or "+") == "-":
        days = -days
    from datetime import timedelta

    base = anchor.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days)
    if m.group("hh") and m.group("mm"):
        base = base.replace(hour=int(m.group("hh")), minute=int(m.group("mm")))
    return base
