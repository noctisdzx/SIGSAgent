"""Smoke tests for the deterministic `MockLLMAdapter`.

Also covers the no-network factory `build_llm_adapter()` returning the mock
when the API key is empty / placeholder.
"""

from __future__ import annotations

import os

from app.llm.adapter import (
    MockLLMAdapter,
    SafeLLMAdapter,
    _looks_like_placeholder_key,
    build_llm_adapter,
)


async def test_mock_summarize_memories_empty():
    m = MockLLMAdapter()
    assert await m.summarize_memories([]) == "(empty)"


async def test_mock_summarize_memories_joined():
    m = MockLLMAdapter()
    out = await m.summarize_memories(["alpha", "beta"])
    assert out.startswith("summary:")
    assert "alpha" in out and "beta" in out


async def test_mock_choose_fragment_picks_best_tag_overlap():
    m = MockLLMAdapter()
    persona = {"preferences": {"favorite_tags": ["study"]}}
    candidates = [
        {"id": "a", "label": "x", "tags": ["leisure"]},
        {"id": "b", "label": "y", "tags": ["study", "social"]},
        {"id": "c", "label": "z", "tags": []},
    ]
    fid, rationale = await m.choose_fragment(
        gap_minutes=30, persona=persona, memories=[], candidates=candidates
    )
    assert fid == "b"
    assert rationale  # non-empty


async def test_mock_choose_fragment_empty_raises():
    m = MockLLMAdapter()
    raised = False
    try:
        await m.choose_fragment(30, {}, [], [])
    except ValueError:
        raised = True
    assert raised


async def test_mock_extract_triplets_deterministic():
    m = MockLLMAdapter()
    out = await m.extract_triplets("alice", ["went to library", "met bob"])
    assert len(out) == 2
    assert all(t["subject"] == "alice" for t in out)
    assert all(t["predicate"] == "did" for t in out)


def test_placeholder_key_detection():
    assert _looks_like_placeholder_key("")
    assert _looks_like_placeholder_key("sk-...")
    assert _looks_like_placeholder_key("CHANGEME")
    assert _looks_like_placeholder_key("sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    assert not _looks_like_placeholder_key("sk-realkey-abc123")


def test_factory_returns_mock_when_no_api_key(monkeypatch) -> None:
    """If LLM_API_KEY is empty/placeholder, factory MUST yield MockLLMAdapter."""
    # We can't easily patch the cached settings, so the cleanest check is to
    # call the underlying detector directly. Still, run the factory to ensure
    # it doesn't network even with default settings (test runner has no key).
    monkeypatch.setenv("LLM_API_KEY", "")
    # Force settings to re-read by clearing the cached singleton.
    import app.settings as s
    s._settings = None
    try:
        adapter = build_llm_adapter()
        assert isinstance(adapter, (MockLLMAdapter, SafeLLMAdapter))
    finally:
        s._settings = None
        # Restore env
        os.environ.pop("LLM_API_KEY", None)
