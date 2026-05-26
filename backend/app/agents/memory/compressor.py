"""STM → LTM compression and LTM internal compaction.

Spec recap (`docs/llm_fallback.md`):
- Trigger: STM exceeded capacity (30).
- If `LTM.free_slots() >= 5`:
    take `STM.top_for_compress(10)` (by hit_count desc, ts desc),
    compress into 1 LTM item, then `STM.drop_oldest(20)`
    (drops the *back 20*: lowest priority by the same ordering).
- Else (free_slots < 5):
    first compress `LTM.bottom(3)` into 1 LTM item to free space,
    then proceed with the STM compression step above.
- Every LLM call goes through `with_fallback`; on fallback the produced
  `LongTermItem.degraded` is set to True so the UI can flag it.
- `maybe_compress` is idempotent — re-runs whenever STM > capacity, no-ops
  otherwise. Once the post-condition `STM.size() <= capacity` holds, calling
  it again does nothing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.llm.adapter import LLMAdapter
from app.llm.retry import with_fallback

from .long_term import (
    LTM_BOTTOM_COMPRESS_COUNT,
    LTM_FREE_SLOT_THRESHOLD,
    LongTermItem,
    LongTermMemory,
)
from .short_term import ShortTermItem, ShortTermMemory


@dataclass
class CompressionResult:
    new_ltm: LongTermItem
    dropped_stm_ids: list[str]
    replaced_ltm_ids: list[str]
    degraded: bool = False


class MemoryCompressor:
    def __init__(self, stm: ShortTermMemory, ltm: LongTermMemory, llm: LLMAdapter) -> None:
        self.stm = stm
        self.ltm = ltm
        self.llm = llm

    async def maybe_compress(self, now: datetime | None = None) -> CompressionResult | None:
        """Compress iff STM is over capacity. No-op otherwise (idempotent).

        `now` is the in-game timestamp recorded on any LTM item produced.
        """
        if self.stm.size() <= self.stm.capacity:
            return None
        return await self.compress(now=now)

    async def compress(self, now: datetime | None = None) -> CompressionResult:
        replaced: list[str] = []
        any_degraded = False

        # Step A: if LTM is too full, evict its bottom-3 into 1 fresh LTM.
        if self.ltm.free_slots() < LTM_FREE_SLOT_THRESHOLD:
            bottom = self.ltm.bottom(LTM_BOTTOM_COMPRESS_COUNT)
            if bottom:
                merged_ltm = await self._llm_compress(bottom, now=now)
                self.ltm.replace([b.id for b in bottom], merged_ltm)
                replaced = [b.id for b in bottom]
                any_degraded = any_degraded or merged_ltm.degraded

        # Step B: compress STM top-10 → 1 LTM, drop STM back-20.
        top10 = self.stm.top_for_compress(10)
        new_ltm = await self._llm_compress(top10, now=now)
        self.ltm.add(new_ltm)
        any_degraded = any_degraded or new_ltm.degraded

        dropped = self.stm.drop_oldest(20)

        return CompressionResult(
            new_ltm=new_ltm,
            dropped_stm_ids=[d.id for d in dropped],
            replaced_ltm_ids=replaced,
            degraded=any_degraded,
        )

    # --------- LLM calls with fallback ---------

    async def _llm_compress(
        self,
        items: list[ShortTermItem] | list[LongTermItem],
        now: datetime | None = None,
    ) -> LongTermItem:
        """Summarize a batch (STM or LTM) into one LTM item, with fallback.

        Resulting LTM `ts` defaults to `now` (the in-game time when caller
        decided to compress); if `now` is None and items exist, falls back
        to the newest item's ts; only as a last resort uses wall-clock.
        """
        if not items:
            return LongTermItem(
                id=f"ltm_{uuid.uuid4().hex[:8]}",
                text="(empty)",
                ts=now or datetime.utcnow(),
                source_ids=[],
                degraded=True,
            )

        ts = now or max(it.ts for it in items)

        texts = [f"[{it.ts.isoformat()}] {it.text}" for it in items]

        async def _primary() -> str:
            return await self.llm.summarize_memories(texts)

        async def _fallback() -> str:
            joined = " | ".join(texts)
            return f"{joined}\u241F{joined}"  # mirror as both zh and en

        summary, degraded = await with_fallback(_primary, _fallback)

        # The adapter encodes bilingual output as "<zh>\u241F<en>". Split it
        # back into the two text fields; degrade gracefully if only one half is
        # present.
        zh_text, en_text = summary, None
        if "\u241F" in summary:
            zh_text, _, en_text = summary.partition("\u241F")
            zh_text = zh_text.strip() or summary
            en_text = en_text.strip() or None

        return LongTermItem(
            id=f"ltm_{uuid.uuid4().hex[:8]}",
            text=zh_text,
            text_en=en_text,
            ts=ts,
            source_ids=[it.id for it in items],
            degraded=degraded,
        )
