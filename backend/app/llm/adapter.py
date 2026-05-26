"""Abstract LLM interface used by memory / decision modules,
plus a deterministic Mock used as the ultimate fallback so the
simulation never grinds to a halt because of LLM provider issues.
"""

from __future__ import annotations

from typing import Any, Protocol


class LLMAdapter(Protocol):
    async def summarize_memories(self, texts: list[str]) -> str: ...

    async def choose_fragment(
        self,
        gap_minutes: int,
        persona: dict,
        memories: list[str],
        candidates: list[dict[str, Any]],
    ) -> tuple[str, str]:
        """Return (fragment_id, rationale)."""
        ...

    async def extract_triplets(
        self,
        agent_id: str,
        events: list[str],
    ) -> list[dict[str, Any]]: ...


class MockLLMAdapter:
    """No-network deterministic fallback."""

    async def summarize_memories(self, texts: list[str]) -> str:
        if not texts:
            return "(empty)"
        return "summary: " + " | ".join(t[:60] for t in texts)

    async def choose_fragment(
        self,
        gap_minutes: int,
        persona: dict,
        memories: list[str],
        candidates: list[dict[str, Any]],
    ) -> tuple[str, str]:
        first = candidates[0]
        return first["id"], "mock: picked the first candidate"

    async def extract_triplets(
        self,
        agent_id: str,
        events: list[str],
    ) -> list[dict[str, Any]]:
        return [
            {"subject": agent_id, "predicate": "did", "object": ev[:30]}
            for ev in events
        ]
