"""Pydantic v2 schemas mirrored against the JSON files in `data/`."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FurnitureSchema(BaseModel):
    name: str
    num: int


class RoomSchema(BaseModel):
    index: int
    uid: str
    name: str
    tag: list[str] = Field(default_factory=list)
    adjacent: list[str] = Field(default_factory=list)
    description: str = ""
    position: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    containment: int = 0
    furniture: list[FurnitureSchema] = Field(default_factory=list)


class SceneFileSchema(BaseModel):
    rooms: list[RoomSchema]


class PersonaSchema(BaseModel):
    id: str
    name: str
    role: str
    personality: dict[str, float] = Field(default_factory=dict)
    preferences: dict[str, Any] = Field(default_factory=dict)
    relations: dict[str, Any] = Field(default_factory=dict)
    initial_location_uid: str
    schedule_template_id: str


class TemplateBlockSchema(BaseModel):
    start: str
    end: str
    activity: str
    location_uid: str


class ScheduleTemplateSchema(BaseModel):
    id: str
    description: str = ""
    week: dict[str, list[TemplateBlockSchema]] = Field(default_factory=dict)


class FragmentSchema(BaseModel):
    id: str
    label: str
    duration_minutes: int
    tags: list[str] = Field(default_factory=list)
    preferred_location_uids: list[str] = Field(default_factory=list)
    cost: int = 0
    preconditions: dict[str, Any] = Field(default_factory=dict)


class FragmentFileSchema(BaseModel):
    fragments: list[FragmentSchema]


class ActionSchema(BaseModel):
    id: str
    label: str
    cost: int
    duration_minutes: int = 5
    params: list[str] = Field(default_factory=list)
    preconditions: dict[str, str] = Field(default_factory=dict)
    effects: dict[str, str] = Field(default_factory=dict)
    concurrent_with: list[str] = Field(default_factory=list)
    stochastic: dict[str, Any] | None = None


class ActionFileSchema(BaseModel):
    actions: list[ActionSchema]
