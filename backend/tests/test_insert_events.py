"""InsertEvent library + scoring + selector coverage:
- library.fits() respects duration, resolved location, and the role gate.
- score() is role-gated (0 for an ineligible archetype) and positive otherwise.
- selector.shortlist() returns the top-N above threshold.
- selector.select(): happy path (LLM returns a valid id) + fallback
  (raising LLM → highest-scoring candidate, degraded=True).
"""

from __future__ import annotations

from typing import Any

from app.agents.schedule.insert_events import (
    InsertEvent,
    InsertEventLibrary,
    InsertEventSelector,
    classify,
    score,
)


def _event(eid: str, *, duration: int, arches: list[str], tags: list[str],
           start="438038e3", end="9a49343c", mbti="ENTP",
           ocean: dict | None = None, drives: dict | None = None) -> InsertEvent:
    return InsertEvent(
        id=eid,
        description_zh=f"{eid} 描述",
        description_en=f"{eid} desc",
        tags=tags,
        duration_minutes=duration,
        start_uid=start,
        end_uid=end,
        start_name="Dorm",
        end_name="Canteen",
        role="student",
        eligible_archetypes=arches,
        ocean=ocean or {"openness": 0.9, "conscientiousness": 0.5, "extroversion": 0.4,
                        "agreeableness": 0.7, "neuroticism": 0.6},
        drives=drives or {"curiosity": 0.9, "club_engagement": 0.8, "research_interest": 0.7,
                          "loneliness": 0.5, "stress": 0.4},
        mbti=mbti,
    )


UNDERGRAD = {
    "id": "npc_u",
    "role": "undergraduate_x",
    "personality": {"openness": 0.85, "conscientiousness": 0.5, "extraversion": 0.45,
                    "agreeableness": 0.7, "neuroticism": 0.6},
    "preferences": {"favorite_tags": ["leisure", "social"]},
    "profile": {"role_zh": "大二", "mbti": "ENTP"},
}

FACULTY = {
    "id": "npc_f",
    "role": "faculty_x",
    "personality": {"openness": 0.6, "conscientiousness": 0.8, "extraversion": 0.5,
                    "agreeableness": 0.6, "neuroticism": 0.3},
    "preferences": {"favorite_tags": ["study"]},
    "profile": {"role_zh": "教授", "mbti": "INTJ"},
}


def _library() -> InsertEventLibrary:
    return InsertEventLibrary([
        _event("IE01", duration=30, arches=["undergrad", "grad"], tags=["social", "leisure"]),
        _event("IE02", duration=60, arches=["undergrad", "grad"], tags=["study"]),
        _event("IE03", duration=30, arches=["faculty"], tags=["study"]),
        _event("IE04", duration=300, arches=["undergrad", "grad"], tags=["fitness"]),  # too long
    ])


def test_classify_basic():
    assert classify(UNDERGRAD) == "undergrad"
    assert classify(FACULTY) == "faculty"


def test_fits_duration_and_role_gate():
    lib = _library()
    fitting = lib.fits(gap_minutes=60, archetype="undergrad")
    ids = {e.id for e in fitting}
    # IE01 (30) + IE02 (60) fit & undergrad-eligible; IE03 faculty-only; IE04 too long.
    assert ids == {"IE01", "IE02"}


def test_fits_excludes_unresolved_location():
    ev = _event("IE_noloc", duration=30, arches=["undergrad"], tags=["x"], end=None)
    lib = InsertEventLibrary([ev])
    assert lib.fits(gap_minutes=60, archetype="undergrad") == []


def test_score_role_gated_to_zero():
    ev = _event("IE_fac", duration=30, arches=["faculty"], tags=["study"])
    assert score(UNDERGRAD, ev) == 0.0
    assert score(FACULTY, ev) > 0.0


def test_shortlist_top_n_and_threshold():
    sel = InsertEventSelector(_library(), _GoodLLM(), top_n=1, score_threshold=0.0)
    short = sel.shortlist(gap_minutes=60, persona=UNDERGRAD)
    assert len(short) == 1
    assert short[0].id in {"IE01", "IE02"}


class _GoodLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def choose_insert_event(
        self,
        gap_minutes: int,
        persona: dict,
        memories: list[str],
        candidates: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        self.calls += 1
        return candidates[0]["id"], "测试LLM选了第一个"


class _BadLLM:
    async def choose_insert_event(self, *a, **kw) -> tuple[str, str]:
        raise RuntimeError("LLM down")


async def test_select_happy_path():
    llm = _GoodLLM()
    sel = InsertEventSelector(_library(), llm, top_n=3, score_threshold=0.0)
    out = await sel.select(gap_minutes=60, persona=UNDERGRAD, memories=["精神不错"])
    assert out is not None
    assert out.degraded is False
    assert out.event.id in {"IE01", "IE02"}
    assert llm.calls == 1


async def test_select_fallback_when_llm_raises():
    sel = InsertEventSelector(_library(), _BadLLM(), top_n=3, score_threshold=0.0)
    out = await sel.select(gap_minutes=60, persona=UNDERGRAD, memories=["精神不错"])
    assert out is not None
    assert out.degraded is True
    assert out.event.id in {"IE01", "IE02"}


async def test_select_returns_none_when_no_candidates():
    # gap shorter than every event → empty shortlist
    sel = InsertEventSelector(_library(), _GoodLLM(), score_threshold=0.0)
    out = await sel.select(gap_minutes=10, persona=UNDERGRAD, memories=[])
    assert out is None
