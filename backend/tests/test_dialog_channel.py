"""Dual-channel behaviour: dialog-channel willingness + mutter gating.

These exercise the pure / early-return logic of the dialog channel without
standing up a full NPCAgent (scene + world + libs). We bypass __init__ via
`__new__` and attach only the attributes each method touches.
"""

from __future__ import annotations

import random as _random
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.agents.agent import NPCAgent, PersonaConfig


def _bare_agent(personality: dict) -> NPCAgent:
    a = NPCAgent.__new__(NPCAgent)
    a.persona = PersonaConfig(
        id="x",
        name="测试",
        role="student",
        personality=personality,
        preferences={},
        relations={},
        initial_location_uid="u",
        schedule_template_id="t",
    )
    a._mutter_last = None
    return a


def test_extraversion_normalization():
    assert _bare_agent({"extraversion": 0.7})._extraversion() == 0.7
    # 0-100 scale is normalised to 0-1.
    assert _bare_agent({"extroversion": 80})._extraversion() == 0.8
    # Missing → neutral default.
    assert _bare_agent({})._extraversion() == 0.5
    # Nested OCEAN dict is also probed.
    assert _bare_agent({"ocean": {"extroversion": 0.3}})._extraversion() == 0.3


def test_social_willingness_extremes(monkeypatch):
    # Force the roll to the top of the range so only a ~1.0 probability passes.
    monkeypatch.setattr(_random, "random", lambda: 0.99)
    introvert = _bare_agent({"extraversion": 0.0})
    extravert = _bare_agent({"extraversion": 1.0})
    nonsocial = SimpleNamespace(activity="attend_class")
    social = SimpleNamespace(activity="group_discussion")

    # introvert + non-social: prob = 0.25 → 0.99 not < 0.25 → stays quiet.
    assert introvert._social_willingness(nonsocial) is False
    # extravert + social: prob = min(1, 0.75 + 0.35) = 1.0 → 0.99 < 1.0 → talks.
    assert extravert._social_willingness(social) is True


async def test_maybe_mutter_respects_cooldown():
    a = _bare_agent({"extraversion": 1.0})
    now = datetime(2025, 1, 1, 12, 0)
    a._mutter_last = now  # just muttered
    world = SimpleNamespace(sim_time=now + timedelta(minutes=10))  # < 30min cooldown
    slot = SimpleNamespace(activity="walk")
    snap = SimpleNamespace(here_uid="u", here_name="Room")
    assert await a._maybe_mutter(slot, snap, world, "move") is False


async def test_maybe_mutter_probability_gate(monkeypatch):
    # Roll above MUTTER_PROBABILITY → no mutter (returns before any LLM call).
    monkeypatch.setattr(_random, "random", lambda: 0.99)
    a = _bare_agent({"extraversion": 1.0})
    a._mutter_last = None
    now = datetime(2025, 1, 1, 12, 0)
    world = SimpleNamespace(sim_time=now)
    slot = SimpleNamespace(activity="walk")
    snap = SimpleNamespace(here_uid="u", here_name="Room")
    assert await a._maybe_mutter(slot, snap, world, "move") is False
