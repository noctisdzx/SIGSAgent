"""STM→LTM compression spec.

Covers both branches of `MemoryCompressor.compress`:
- LTM has ≥ 5 free slots → STM top-10 squeezed into 1 LTM, STM back-20 dropped.
- LTM has < 5 free slots → bottom-3 LTM compacted first, then STM step.

Plus the fallback path: a raising LLM produces a `degraded=True` LTM item.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.agents.memory.compressor import MemoryCompressor
from app.agents.memory.long_term import LongTermItem, LongTermMemory
from app.agents.memory.short_term import ShortTermItem, ShortTermMemory


class _FakeLLM:
    """Deterministic + introspectable. Tracks call count."""

    def __init__(self, raise_on_call: bool = False) -> None:
        self.calls = 0
        self.raise_on_call = raise_on_call

    async def summarize_memories(self, texts: list[str]) -> str:
        self.calls += 1
        if self.raise_on_call:
            raise RuntimeError("simulated LLM outage")
        return f"summary({len(texts)})"

    async def choose_fragment(self, *a, **kw) -> tuple[str, str]:  # pragma: no cover
        raise NotImplementedError

    async def extract_triplets(self, *a, **kw) -> list[dict[str, Any]]:  # pragma: no cover
        return []


def _stm_filled(n: int) -> ShortTermMemory:
    stm = ShortTermMemory()
    base = datetime(2026, 5, 26, 7, 0)
    for i in range(n):
        stm.add(
            ShortTermItem(
                id=f"s{i:03d}",
                text=f"event-{i}",
                ts=base + timedelta(minutes=i),
                source="schedule:test",
                hit_count=i % 4,
            )
        )
    return stm


def _ltm_filled(n: int) -> LongTermMemory:
    ltm = LongTermMemory()
    base = datetime(2026, 5, 25, 7, 0)
    for i in range(n):
        ltm.add(
            LongTermItem(
                id=f"l{i:02d}",
                text=f"long-{i}",
                ts=base + timedelta(hours=i),
                source_ids=[],
                hit_count=i,
            )
        )
    return ltm


def test_stm_capacity():
    assert ShortTermMemory().capacity == 30


def test_ltm_capacity():
    assert LongTermMemory().capacity == 15


async def test_compress_with_free_ltm_slots():
    stm = _stm_filled(40)        # 40 > 30
    ltm = _ltm_filled(5)         # free_slots = 10 ≥ 5
    llm = _FakeLLM()

    comp = MemoryCompressor(stm, ltm, llm)
    result = await comp.maybe_compress()
    assert result is not None
    assert result.replaced_ltm_ids == []   # no LTM eviction needed
    assert result.degraded is False
    assert llm.calls == 1                  # only the STM compression call

    # 40 - 20 dropped = 20 left
    assert stm.size() == 20
    # LTM grew by 1 fresh item
    assert ltm.size() == 6
    # The new item references 10 STM ids
    assert len(result.new_ltm.source_ids) == 10
    assert result.new_ltm.degraded is False


async def test_compress_with_full_ltm_evicts_bottom_first():
    stm = _stm_filled(35)
    ltm = _ltm_filled(15)        # free_slots = 0 < 5
    llm = _FakeLLM()

    comp = MemoryCompressor(stm, ltm, llm)
    result = await comp.maybe_compress()
    assert result is not None
    # Bottom 3 LTM evicted into 1 fresh, then STM step adds 1 more.
    assert len(result.replaced_ltm_ids) == 3
    assert llm.calls == 2          # one for LTM bottom, one for STM top
    # 15 - 3 + 1 (LTM compaction) + 1 (STM→LTM) = 14
    assert ltm.size() == 14


async def test_compress_idempotent_when_under_capacity():
    stm = _stm_filled(10)        # under capacity
    ltm = _ltm_filled(0)
    llm = _FakeLLM()

    comp = MemoryCompressor(stm, ltm, llm)
    assert await comp.maybe_compress() is None
    assert llm.calls == 0


async def test_fallback_marks_degraded():
    stm = _stm_filled(35)
    ltm = _ltm_filled(0)
    llm = _FakeLLM(raise_on_call=True)

    comp = MemoryCompressor(stm, ltm, llm)
    result = await comp.maybe_compress()
    assert result is not None
    # Even after retries the LLM keeps failing → fallback used.
    assert result.degraded is True
    assert result.new_ltm.degraded is True
    # The fallback summary is the joined source texts.
    assert " | " in result.new_ltm.text
