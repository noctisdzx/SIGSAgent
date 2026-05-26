"""Loads all JSON files under `data/` with strict pydantic validation."""

from __future__ import annotations

import json
from pathlib import Path

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


class ConfigLoader:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    # ----- helpers -----

    def _read(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    # ----- core loaders -----

    def load_scenes(self) -> dict[str, SceneFileSchema]:
        out: dict[str, SceneFileSchema] = {}
        scenes_dir = self.data_dir / "scenes"
        if not scenes_dir.exists():
            return out
        for p in scenes_dir.glob("*.json"):
            out[p.stem] = SceneFileSchema.model_validate(self._read(p))
        return out

    def load_personas(self) -> dict[str, PersonaSchema]:
        out: dict[str, PersonaSchema] = {}
        personas_dir = self.data_dir / "personas"
        if not personas_dir.exists():
            return out
        for p in personas_dir.glob("*.json"):
            persona = PersonaSchema.model_validate(self._read(p))
            out[persona.id] = persona
        return out

    def load_schedule_templates(self) -> dict[str, ScheduleTemplateSchema]:
        out: dict[str, ScheduleTemplateSchema] = {}
        tpl_dir = self.data_dir / "schedule_templates"
        if not tpl_dir.exists():
            return out
        for p in tpl_dir.glob("*.json"):
            tpl = ScheduleTemplateSchema.model_validate(self._read(p))
            out[tpl.id] = tpl
        return out

    def load_fragments(self) -> FragmentFileSchema | None:
        p = self.data_dir / "schedule_fragments" / "fragments.json"
        if not p.exists():
            return None
        return FragmentFileSchema.model_validate(self._read(p))

    def load_actions(self) -> ActionFileSchema | None:
        p = self.data_dir / "actions" / "actions.json"
        if not p.exists():
            return None
        return ActionFileSchema.model_validate(self._read(p))

    # ----- auxiliary loaders -----

    def load_relations(self) -> RelationsSchema | None:
        p = self.data_dir / "relations.json"
        if not p.exists():
            return None
        return RelationsSchema.model_validate(self._read(p))

    def load_scenes_library(self) -> ScenesLibrarySchema | None:
        p = self.data_dir / "scenes_library.json"
        if not p.exists():
            return None
        return ScenesLibrarySchema.model_validate(self._read(p))

    def load_timeline_seed(self) -> TimelineSeedSchema | None:
        p = self.data_dir / "timeline_seed.json"
        if not p.exists():
            return None
        return TimelineSeedSchema.model_validate(self._read(p))

    def load_memory_seed(self) -> MemorySeedSchema | None:
        p = self.data_dir / "memory_seed.json"
        if not p.exists():
            return None
        return MemorySeedSchema.model_validate(self._read(p))
