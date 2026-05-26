"""STM → LTM compression and LTM internal compaction.

Spec recap:
- Trigger: STM exceeded capacity (30).
- If `LTM.free_slots() >= 5`:
    take `STM.top_for_compress(10)` (by hit_count desc, ts desc),
    compress into 1 LTM item, then `STM.drop_oldest(20)`
    (drops the *back 20*: lowest priority by the same ordering).
- Else (free_slots < 5):
    first compress `LTM.bottom(3)` into 1 LTM item to free space,
    then proceed with the STM compression step above.
- LLM call MUST have a fallback: on failure, produce a degraded item
  by concatenating sources with timestamps and set `degraded=True`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.llm.adapter import LLMAdapter
from .long_term import (
    LTM_BOTTOM_COMPRESS_COUNT,
    LTM_FREE_SLOT_THRESHOLD,
    LongTermItem,
    LongTermMemory,
)
from .short_term import ShortTermMemory


@dataclass
class CompressionResult:
    new_ltm: LongTermItem
    dropped_stm_ids: list[str]
    replaced_ltm_ids: list[str]


class MemoryCompressor:
    def __init__(self, stm: ShortTermMemory, ltm: LongTermMemory, llm: LLMAdapter) -> None:
        self.stm = stm
        self.ltm = ltm
        self.llm = llm

    async def maybe_compress(self) -> CompressionResult | None:
        if self.stm.size() <= self.stm.capacity:
            return None
        return await self.compress()

    async def compress(self) -> CompressionResult:
        replaced: list[str] = []

        if self.ltm.free_slots() < LTM_FREE_SLOT_THRESHOLD:
            bottom = self.ltm.bottom(LTM_BOTTOM_COMPRESS_COUNT)
            merged_ltm = await self._llm_compress_ltm(bottom)
            self.ltm.replace([b.id for b in bottom], merged_ltm)
            replaced = [b.id for b in bottom]

        top10 = self.stm.top_for_compress(10)
        new_ltm = await self._llm_compress_stm(top10)
        self.ltm.add(new_ltm)
        dropped = self.stm.drop_oldest(20)

        return CompressionResult(
            new_ltm=new_ltm,
            dropped_stm_ids=[d.id for d in dropped],
            replaced_ltm_ids=replaced,
        )

    # --------- LLM calls with fallback ---------

    async def _llm_compress_stm(self, items) -> LongTermItem:
        texts = [f"[{it.ts.isoformat()}] {it.text}" for it in items]
        try:
            summary = await self.llm.summarize_memories(texts)
            degraded = False
        except Exception:
            summary = " | ".join(texts)
            degraded = True
        return LongTermItem(
            id=f"ltm_{uuid.uuid4().hex[:8]}",
            text=summary,
            ts=datetime.utcnow(),
            source_ids=[it.id for it in items],
            degraded=degraded,
        )

    async def _llm_compress_ltm(self, items) -> LongTermItem:
        texts = [f"[{it.ts.isoformat()}] {it.text}" for it in items]
        try:
            summary = await self.llm.summarize_memories(texts)
            degraded = False
        except Exception:
            summary = " | ".join(texts)
            degraded = True
        return LongTermItem(
            id=f"ltm_{uuid.uuid4().hex[:8]}",
            text=summary,
            ts=datetime.utcnow(),
            source_ids=[it.id for it in items],
            degraded=degraded,
        )
