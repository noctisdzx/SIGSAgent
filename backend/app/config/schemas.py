"""Pydantic v2 schemas mirrored against the JSON files in `data/`.

Pydantic v2's default `extra='ignore'` is fine for our purposes — most NPC
JSON files carry rich `profile` / `narrative_*` annotations that the runtime
does not consume directly but still wants to expose to the frontend; we allow
them through with `extra='allow'` so they remain accessible.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _BaseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class FurnitureSchema(_BaseModel):
    name: str
    num: int


class RoomSchema(_BaseModel):
    index: int
    uid: str
    name: str
    tag: list[str] = Field(default_factory=list)
    adjacent: list[str] = Field(default_factory=list)
    description: str = ""
    position: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    containment: int = 0
    furniture: list[FurnitureSchema] = Field(default_factory=list)


class SceneFileSchema(_BaseModel):
    rooms: list[RoomSchema]


class PersonaSchema(_BaseModel):
    id: str
    name: str
    role: str
    personality: dict[str, float] = Field(default_factory=dict)
    preferences: dict[str, Any] = Field(default_factory=dict)
    relations: dict[str, Any] = Field(default_factory=dict)
    initial_location_uid: str
    schedule_template_id: str
    profile: dict[str, Any] = Field(default_factory=dict)


class TemplateBlockSchema(_BaseModel):
    start: str
    end: str
    activity: str
    location_uid: str


class ScheduleTemplateSchema(_BaseModel):
    id: str
    description: str = ""
    week: dict[str, list[TemplateBlockSchema]] = Field(default_factory=dict)


class FragmentSchema(_BaseModel):
    id: str
    label: str
    duration_minutes: int
    tags: list[str] = Field(default_factory=list)
    preferred_location_uids: list[str] = Field(default_factory=list)
    cost: int = 0
    preconditions: dict[str, Any] = Field(default_factory=dict)


class FragmentFileSchema(_BaseModel):
    fragments: list[FragmentSchema]


class ActionSchema(_BaseModel):
    id: str
    label: str
    cost: int
    duration_minutes: int = 5
    params: list[str] = Field(default_factory=list)
    preconditions: dict[str, str] = Field(default_factory=dict)
    effects: dict[str, str] = Field(default_factory=dict)
    concurrent_with: list[str] = Field(default_factory=list)
    stochastic: dict[str, Any] | None = None


class ActionFileSchema(_BaseModel):
    actions: list[ActionSchema]


# ---------- Newly added auxiliary datasets ----------

class RelationEdgeSchema(_BaseModel):
    source: str
    target: str
    label: str
    weight: float = 0.5
    tone: str | None = None
    color: str | None = None
    label_en: str | None = None
    label_zh: str | None = None


class RelationsSchema(_BaseModel):
    edges: list[RelationEdgeSchema] = Field(default_factory=list)


class SocialSceneSchema(_BaseModel):
    id: str
    title: str
    tags: list[str] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)
    location_uid: str | None = None
    trigger: str | None = None


class ScenesLibrarySchema(_BaseModel):
    scenes: list[SocialSceneSchema] = Field(default_factory=list)


class TimelineEventSchema(_BaseModel):
    day: str
    time: str
    title: str
    location_uid: str | None = None
    people: list[str] = Field(default_factory=list)


class TimelineSeedSchema(_BaseModel):
    events: list[TimelineEventSchema] = Field(default_factory=list)


class MemorySeedItemSchema(_BaseModel):
    text: str
    text_en: str | None = None
    tone: str | None = None
    ts: str | None = None


class MemorySeedTripletSchema(_BaseModel):
    subject: str
    predicate: str
    object: str
    narrative_zh: str | None = None
    narrative_en: str | None = None


class MemorySeedEntrySchema(_BaseModel):
    memories: list[MemorySeedItemSchema] = Field(default_factory=list)
    triplets: list[MemorySeedTripletSchema] = Field(default_factory=list)


class MemorySeedSchema(_BaseModel):
    per_agent: dict[str, MemorySeedEntrySchema] = Field(default_factory=dict)
