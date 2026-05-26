"""SlotFiller covers:
- Happy path with a fake LLM that returns a valid candidate id.
- Fallback path: a raising LLM produces a degraded SlotFillChoice via
  weighted random; result still references one of the candidates.
- LRU caching: identical (persona_id, memories, gap) hits the cache.
"""

from __future__ import annotations

from typing import Any

from app.agents.decision.slot_filler import SlotFiller
from app.agents.schedule.fragments import Fragment, FragmentLibrary


def _library() -> FragmentLibrary:
    return FragmentLibrary([
        Fragment(
            id="frag_chat_cafe",
            label="去咖啡角和朋友闲聊",
            duration_minutes=15,
            tags=["social", "leisure"],
            preferred_location_uids=[],
        ),
        Fragment(
            id="frag_read_lab",
            label="在自习区翻几页文献",
            duration_minutes=20,
            tags=["study"],
            preferred_location_uids=[],
        ),
        Fragment(
            id="frag_walk_garden",
            label="在花园散步",
            duration_minutes=10,
            tags=["leisure", "fitness"],
            preferred_location_uids=[],
        ),
    ])


class _GoodLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def summarize_memories(self, texts: list[str]) -> str:  # pragma: no cover
        return "(unused)"

    async def choose_fragment(
        self,
        gap_minutes: int,
        persona: dict,
        memories: list[str],
        candidates: list[dict[str, Any]],
    ) -> tuple[str, str]:
        self.calls += 1
        return "frag_read_lab", "测试LLM选了文献"

    async def extract_triplets(self, *a, **kw) -> list[dict[str, Any]]:  # pragma: no cover
        return []


class _BadLLM:
    async def summarize_memories(self, texts: list[str]) -> str:  # pragma: no cover
        return "(unused)"

    async def choose_fragment(self, *a, **kw) -> tuple[str, str]:
        raise RuntimeError("LLM down")

    async def extract_triplets(self, *a, **kw) -> list[dict[str, Any]]:  # pragma: no cover
        return []


PERSONA = {
    "id": "demo_alice",
    "preferences": {"favorite_tags": ["study", "leisure"]},
}


async def test_happy_path_picks_llm_choice():
    sf = SlotFiller(_library(), _GoodLLM())
    out = await sf.fill(gap_minutes=30, persona=PERSONA, memories=["今天精神不错"])
    assert out is not None
    assert out.fragment.id == "frag_read_lab"
    assert out.degraded is False
    assert "文献" in out.rationale or "study" in out.rationale.lower()


async def test_fallback_when_llm_raises():
    sf = SlotFiller(_library(), _BadLLM())
    out = await sf.fill(gap_minutes=30, persona=PERSONA, memories=["今天精神不错"])
    assert out is not None
    assert out.degraded is True
    assert out.fragment.id in {"frag_chat_cafe", "frag_read_lab", "frag_walk_garden"}


async def test_no_candidates_returns_none():
    sf = SlotFiller(_library(), _GoodLLM())
    # gap shorter than every fragment's duration
    out = await sf.fill(gap_minutes=5, persona=PERSONA, memories=[])
    assert out is None


async def test_cache_hit_skips_llm():
    llm = _GoodLLM()
    sf = SlotFiller(_library(), llm)
    args = dict(gap_minutes=30, persona=PERSONA, memories=["m1", "m2"])
    a = await sf.fill(**args)
    b = await sf.fill(**args)
    assert a is b
    assert llm.calls == 1   # second call served from cache


async def test_cache_keyed_on_memories():
    llm = _GoodLLM()
    sf = SlotFiller(_library(), llm)
    await sf.fill(gap_minutes=30, persona=PERSONA, memories=["m1"])
    await sf.fill(gap_minutes=30, persona=PERSONA, memories=["m2"])
    # Different memories → fresh call
    assert llm.calls == 2
