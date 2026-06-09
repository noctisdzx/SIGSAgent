"""Insertable campus "insert events" — special A→B trips an NPC may take in a
free gap, chosen by an LLM the same way `slot_filler` picks a fragment.

Pipeline at runtime:
1. `InsertEventLibrary.fits(gap_minutes, archetype)` filters by duration +
   role gate.
2. `score(persona, event)` ranks the survivors (OCEAN cosine + drive-proxy
   cosine + MBTI bonus) and `InsertEventSelector.shortlist` keeps the top-N.
3. The shortlist (id + natural-language description + tags + duration + trip)
   is handed to `llm.choose_insert_event`, which makes the final pick.
   On LLM failure we fall back to the highest-scoring candidate.

The library JSON is produced offline by `scripts/build_insert_events.py`.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

OCEAN_KEYS = ["openness", "conscientiousness", "extroversion", "agreeableness", "neuroticism"]
DRIVE_KEYS = [
    "stress", "curiosity", "procrastination", "budget", "loneliness",
    "weather_sensitivity", "health_awareness", "club_engagement",
    "research_interest", "romantic_interest",
]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class InsertEvent:
    id: str
    description_zh: str
    description_en: str
    tags: list[str]
    duration_minutes: int
    start_uid: str | None
    end_uid: str | None
    start_name: str
    end_name: str
    role: str
    eligible_archetypes: list[str]
    ocean: dict[str, float] = field(default_factory=dict)
    drives: dict[str, float] = field(default_factory=dict)
    mbti: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "InsertEvent":
        return cls(
            id=d["id"],
            description_zh=d.get("description_zh") or d.get("npc_description") or "",
            description_en=d.get("description_en") or "",
            tags=list(d.get("tags") or []),
            duration_minutes=int(d.get("duration_minutes", 0)),
            start_uid=d.get("start_uid"),
            end_uid=d.get("end_uid"),
            start_name=d.get("start_name", ""),
            end_name=d.get("end_name", ""),
            role=d.get("role", "student"),
            eligible_archetypes=list(d.get("eligible_archetypes") or []),
            ocean=dict(d.get("ocean") or {}),
            drives=dict(d.get("drives") or {}),
            mbti=d.get("mbti"),
        )

    def candidate_payload(self) -> dict[str, Any]:
        """Shape handed to the LLM via `choose_insert_event`."""
        return {
            "id": self.id,
            "description": self.description_zh,
            "tags": self.tags,
            "duration_minutes": self.duration_minutes,
            "from": self.start_uid,
            "to": self.end_uid,
        }


class InsertEventLibrary:
    def __init__(self, events: list[InsertEvent]) -> None:
        self._by_id: dict[str, InsertEvent] = {e.id: e for e in events}

    @classmethod
    def from_json(cls, path: Path) -> "InsertEventLibrary":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        events = [InsertEvent.from_dict(e) for e in raw.get("events", [])]
        return cls(events)

    def get(self, eid: str) -> InsertEvent:
        return self._by_id[eid]

    def all(self) -> list[InsertEvent]:
        return list(self._by_id.values())

    def fits(self, gap_minutes: int, archetype: str | None = None) -> list[InsertEvent]:
        """Events whose duration fits the gap and whose role gate admits the
        archetype (when given). Resolved-location events only."""
        out: list[InsertEvent] = []
        for e in self._by_id.values():
            if e.duration_minutes <= 0 or e.duration_minutes > gap_minutes:
                continue
            if not (e.start_uid and e.end_uid):
                continue
            if archetype is not None and e.eligible_archetypes and archetype not in e.eligible_archetypes:
                continue
            out.append(e)
        return out


# ---------------------------------------------------------------------------
# Persona classification + scoring (kept here so the runtime has no script dep)
# ---------------------------------------------------------------------------

def classify(persona: dict) -> str:
    """Return one of undergrad / grad / faculty / logistics / other."""
    profile = persona.get("profile", {}) or {}
    role_zh = (profile.get("role_zh") or "") + (profile.get("role_en") or "")
    text = role_zh + " " + (persona.get("role", "") or "")
    if any(k in text for k in ("教授", "讲师", "辅导员", "导师", "医生", "Professor", "Faculty")):
        return "faculty"
    if any(k in text for k in ("保卫", "食堂", "图书馆管理员", "保洁", "宿管", "守门人", "处长", "主厨", "Security", "Logistics")):
        return "logistics"
    if any(k in text for k in ("博", "研", "PhD", "Doctor", "research", "Research")):
        return "grad"
    if any(k in text for k in ("大一", "大二", "大三", "大四", "undergrad", "Yr1", "Yr2", "Yr3", "Yr4")):
        return "undergrad"
    return "other"


def _persona_ocean(persona: dict) -> dict[str, float]:
    p = persona.get("personality", {}) or {}
    return {
        "openness": float(p.get("openness", 0.5)),
        "conscientiousness": float(p.get("conscientiousness", 0.5)),
        "extroversion": float(p.get("extraversion", 0.5)),
        "agreeableness": float(p.get("agreeableness", 0.5)),
        "neuroticism": float(p.get("neuroticism", 0.5)),
    }


def _persona_drive_proxy(persona: dict) -> dict[str, float]:
    o = _persona_ocean(persona)
    arche = classify(persona)
    fav = set(persona.get("preferences", {}).get("favorite_tags", []) or [])
    research = 1.0 if arche in ("grad", "faculty") else 0.4
    social = 0.8 if (fav & {"social", "leisure"}) else o["extroversion"]
    return {
        "stress": o["neuroticism"],
        "curiosity": o["openness"],
        "procrastination": 1.0 - o["conscientiousness"],
        "budget": 0.5,
        "loneliness": 1.0 - o["extroversion"],
        "weather_sensitivity": 0.25 + 0.5 * o["neuroticism"],
        "health_awareness": o["conscientiousness"],
        "club_engagement": social,
        "research_interest": research,
        "romantic_interest": 0.5,
    }


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def score(persona: dict, event: InsertEvent) -> float:
    """Insertion affinity in [0,1]; 0 if role-gated out."""
    if event.eligible_archetypes and classify(persona) not in event.eligible_archetypes:
        return 0.0
    pe = _persona_ocean(persona)
    ocean_sim = _cosine(
        [float(event.ocean.get(k, 0.0)) for k in OCEAN_KEYS],
        [pe[k] for k in OCEAN_KEYS],
    )
    pd = _persona_drive_proxy(persona)
    drive_sim = _cosine(
        [float(event.drives.get(k, 0.0)) for k in DRIVE_KEYS],
        [pd[k] for k in DRIVE_KEYS],
    )
    mbti_bonus = 1.0 if persona.get("profile", {}).get("mbti") == event.mbti else 0.0
    return 0.6 * ocean_sim + 0.3 * drive_sim + 0.1 * mbti_bonus


# ---------------------------------------------------------------------------
# Selector
# ---------------------------------------------------------------------------

@dataclass
class InsertEventChoice:
    event: InsertEvent
    rationale: str
    degraded: bool = False


class InsertEventSelector:
    """Shortlist by role+duration+score, then let the LLM make the final pick."""

    def __init__(
        self,
        library: InsertEventLibrary,
        llm: Any,
        *,
        top_n: int = 5,
        score_threshold: float = 0.5,
        require_start_here: bool = False,
    ) -> None:
        self.library = library
        self.llm = llm
        self.top_n = top_n
        self.score_threshold = score_threshold
        self.require_start_here = require_start_here

    def shortlist(
        self,
        gap_minutes: int,
        persona: dict,
        here_uid: str | None = None,
    ) -> list[InsertEvent]:
        arche = classify(persona)
        fitting = self.library.fits(gap_minutes, archetype=arche)
        if self.require_start_here and here_uid:
            fitting = [e for e in fitting if e.start_uid == here_uid] or fitting
        ranked = sorted(fitting, key=lambda e: score(persona, e), reverse=True)
        ranked = [e for e in ranked if score(persona, e) >= self.score_threshold]
        return ranked[: self.top_n]

    async def select(
        self,
        gap_minutes: int,
        persona: dict,
        memories: list[str],
        context: dict | None = None,
    ) -> InsertEventChoice | None:
        here_uid = (context or {}).get("here_uid")
        candidates = self.shortlist(gap_minutes, persona, here_uid=here_uid)
        if not candidates:
            return None

        payloads = [e.candidate_payload() for e in candidates]
        by_id = {e.id: e for e in candidates}
        try:
            eid, rationale = await self.llm.choose_insert_event(
                gap_minutes=gap_minutes,
                persona=persona,
                memories=memories,
                candidates=payloads,
                context=context,
            )
            chosen = by_id.get(eid)
            if chosen is None:
                raise ValueError("LLM returned unknown insert-event id")
            return InsertEventChoice(event=chosen, rationale=rationale)
        except Exception:
            # Fallback: highest-scoring candidate.
            best = max(candidates, key=lambda e: score(persona, e))
            return InsertEventChoice(
                event=best,
                rationale="fallback: highest-scoring eligible event",
                degraded=True,
            )
