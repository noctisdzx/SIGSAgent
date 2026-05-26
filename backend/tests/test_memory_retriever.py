"""Retriever sanity:
- token Jaccard for whitespace queries,
- char-bigram fallback for Chinese-like queries (no whitespace),
- bumps hit_count for picked items,
- recency boost breaks ties towards newer items.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.agents.memory.long_term import LongTermItem, LongTermMemory
from app.agents.memory.retriever import MemoryRetriever
from app.agents.memory.short_term import ShortTermItem, ShortTermMemory


def _stm(items: list[tuple[str, str, datetime]]) -> ShortTermMemory:
    s = ShortTermMemory()
    for sid, text, ts in items:
        s.add(ShortTermItem(id=sid, text=text, ts=ts, source="t"))
    return s


def test_token_jaccard():
    base = datetime(2026, 5, 26, 7, 0)
    s = _stm([
        ("a", "the cat sat", base),
        ("b", "dogs run fast", base + timedelta(minutes=1)),
    ])
    r = MemoryRetriever(s, LongTermMemory())
    out = r.retrieve("the cat", top_k=2)
    assert out[0].source_id == "a"


def test_chinese_bigram_fallback():
    base = datetime(2026, 5, 26, 7, 0)
    s = _stm([
        ("zh1", "去图书馆看书", base),
        ("zh2", "在花园散步", base + timedelta(minutes=1)),
    ])
    r = MemoryRetriever(s, LongTermMemory())
    out = r.retrieve("图书馆", top_k=1)
    assert out[0].source_id == "zh1"


def test_recency_breaks_ties():
    base = datetime(2026, 5, 26, 7, 0)
    s = _stm([
        ("old", "neutral text", base),
        ("new", "neutral text", base + timedelta(hours=1)),
    ])
    r = MemoryRetriever(s, LongTermMemory(), boost_recent=0.5)
    out = r.retrieve("zzzz nothing matches", top_k=2)
    # Both score 0 on the query, but the newer item gets the bigger recency
    # bonus, so it ranks first.
    assert out[0].source_id == "new"


def test_bump_hit_on_pick():
    base = datetime(2026, 5, 26, 7, 0)
    s = _stm([("a", "alpha beta", base)])
    r = MemoryRetriever(s, LongTermMemory())
    r.retrieve("alpha", top_k=1)
    assert s.all()[0].hit_count == 1


def test_ltm_picked_too():
    base = datetime(2026, 5, 26, 7, 0)
    ltm = LongTermMemory()
    ltm.add(LongTermItem(id="L1", text="alpha gamma", ts=base, source_ids=[]))
    s = _stm([("S1", "delta epsilon", base)])
    r = MemoryRetriever(s, ltm)
    out = r.retrieve("alpha", top_k=1)
    assert out[0].tier == "LTM"
    assert ltm.all()[0].hit_count == 1
