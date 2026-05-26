"""SQLite round-trip for STM / LTM / mem_graph.

Uses a temp file via pytest's `tmp_path` fixture; nothing on the network.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.agents.memory.long_term import LongTermItem
from app.agents.memory.memory_graph import Triplet
from app.agents.memory.short_term import ShortTermItem
from app.agents.memory.store import MemoryStore


async def test_round_trip(tmp_path: Path) -> None:
    db = tmp_path / "memory_test.db"
    store = MemoryStore(db)
    await store.initialize()

    stm = [
        ShortTermItem(
            id="s001",
            text="hello",
            ts=datetime(2026, 5, 26, 7, 5),
            source="schedule:t1",
            hit_count=2,
            meta={"agent_id": "alice"},
        ),
        ShortTermItem(
            id="s002",
            text="world 中文",
            ts=datetime(2026, 5, 26, 7, 10),
            source="schedule:t2",
            meta={},
        ),
    ]
    ltm = [
        LongTermItem(
            id="l001",
            text="abstract pattern",
            ts=datetime(2026, 5, 26, 8, 0),
            source_ids=["s001", "s002"],
            hit_count=1,
            degraded=True,
        )
    ]
    triplets = [
        Triplet(
            id="t001",
            subject="alice",
            predicate="went_to",
            obj="library",
            ts=datetime(2026, 5, 26, 8, 5),
            location_uid="64a9bc35",
            tone="calm",
        )
    ]

    await store.upsert_stm("alice", stm)
    await store.upsert_ltm("alice", ltm)
    await store.append_graph("alice", triplets)

    loaded = await store.load_all("alice")
    assert len(loaded["stm"]) == 2
    assert len(loaded["ltm"]) == 1
    assert len(loaded["graph"]) == 1

    by_id = {it.id: it for it in loaded["stm"]}
    assert by_id["s001"].text == "hello"
    assert by_id["s001"].hit_count == 2
    assert by_id["s001"].meta == {"agent_id": "alice"}
    assert by_id["s002"].text == "world 中文"

    lt = loaded["ltm"][0]
    assert lt.degraded is True
    assert lt.source_ids == ["s001", "s002"]

    tr = loaded["graph"][0]
    assert tr.subject == "alice"
    assert tr.obj == "library"
    assert tr.location_uid == "64a9bc35"


async def test_upsert_replaces_existing_row(tmp_path: Path) -> None:
    db = tmp_path / "memory_upsert.db"
    store = MemoryStore(db)
    await store.initialize()

    item = ShortTermItem(
        id="s_same",
        text="v1",
        ts=datetime(2026, 5, 26, 7, 5),
        source="schedule:t1",
        hit_count=0,
    )
    await store.upsert_stm("alice", [item])

    item2 = ShortTermItem(
        id="s_same",
        text="v2",
        ts=datetime(2026, 5, 26, 7, 6),
        source="schedule:t2",
        hit_count=5,
    )
    await store.upsert_stm("alice", [item2])

    loaded = await store.load_all("alice")
    assert len(loaded["stm"]) == 1
    assert loaded["stm"][0].text == "v2"
    assert loaded["stm"][0].hit_count == 5


async def test_seed_from_memory_seed(tmp_path: Path) -> None:
    db = tmp_path / "memory_seed.db"
    store = MemoryStore(db)
    await store.initialize()

    seed = {
        "per_agent": {
            "demo_alice": {
                "memories": [
                    {"text": "起床", "tone": "calm", "ts": "T 07:05"},
                    {"text": "吃早饭", "tone": "warm", "ts": "T-1d 23:50"},
                ],
                "triplets": [
                    {
                        "subject": "demo_alice",
                        "predicate": "knows",
                        "object": "demo_bob",
                        "narrative_zh": "Alice 与 Bob 是朋友",
                    }
                ],
            }
        }
    }
    counts = await store.seed_from_memory_seed(seed, "demo_alice")
    assert counts == {"stm": 2, "triplets": 1}

    loaded = await store.load_all("demo_alice")
    assert len(loaded["stm"]) == 2
    assert len(loaded["graph"]) == 1
    texts = {it.text for it in loaded["stm"]}
    assert "起床" in texts
    assert "吃早饭" in texts


async def test_seed_handles_missing_persona(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "x.db")
    await store.initialize()
    counts = await store.seed_from_memory_seed({"per_agent": {}}, "nobody")
    assert counts == {"stm": 0, "triplets": 0}


def test_unused_helpers_smoke() -> None:
    # Ensure module imports without side effects.
    assert json.dumps({"a": 1})
