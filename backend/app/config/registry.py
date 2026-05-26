"""Process-global read-only config registry, populated at startup."""

from __future__ import annotations

from dataclasses import dataclass, field

from .schemas import (
    ActionFileSchema,
    FragmentFileSchema,
    MemorySeedSchema,
    PersonaSchema,
    RelationsSchema,
    SceneFileSchema,
    ScenesLibrarySchema,
    ScheduleTemplateSchema,
    TimelineSeedSchema,
)


@dataclass
class Registry:
    scenes: dict[str, SceneFileSchema] = field(default_factory=dict)
    personas: dict[str, PersonaSchema] = field(default_factory=dict)
    schedule_templates: dict[str, ScheduleTemplateSchema] = field(default_factory=dict)
    fragments: FragmentFileSchema | None = None
    actions: ActionFileSchema | None = None
    relations: RelationsSchema | None = None
    scenes_library: ScenesLibrarySchema | None = None
    timeline_seed: TimelineSeedSchema | None = None
    memory_seed: MemorySeedSchema | None = None


_registry: Registry = Registry()


def get_registry() -> Registry:
    return _registry


def reset_registry() -> None:
    """Replace the module-level registry with a fresh one (used by /config/reload)."""
    global _registry
    _registry = Registry()
