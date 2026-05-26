"""Process-global read-only config registry, populated at startup."""

from __future__ import annotations

from dataclasses import dataclass, field

from .schemas import (
    ActionFileSchema,
    FragmentFileSchema,
    PersonaSchema,
    SceneFileSchema,
    ScheduleTemplateSchema,
)


@dataclass
class Registry:
    scenes: dict[str, SceneFileSchema] = field(default_factory=dict)
    personas: dict[str, PersonaSchema] = field(default_factory=dict)
    schedule_templates: dict[str, ScheduleTemplateSchema] = field(default_factory=dict)
    fragments: FragmentFileSchema | None = None
    actions: ActionFileSchema | None = None


_registry: Registry = Registry()


def get_registry() -> Registry:
    return _registry
