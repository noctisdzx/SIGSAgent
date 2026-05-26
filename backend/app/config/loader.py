"""Loads all JSON files under `data/` with strict pydantic validation."""

from __future__ import annotations

import json
from pathlib import Path

from .schemas import (
    ActionFileSchema,
    FragmentFileSchema,
    PersonaSchema,
    SceneFileSchema,
    ScheduleTemplateSchema,
)


class ConfigLoader:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    # ----- helpers -----

    def _read(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    # ----- loaders -----

    def load_scenes(self) -> dict[str, SceneFileSchema]:
        out: dict[str, SceneFileSchema] = {}
        for p in (self.data_dir / "scenes").glob("*.json"):
            out[p.stem] = SceneFileSchema.model_validate(self._read(p))
        return out

    def load_personas(self) -> dict[str, PersonaSchema]:
        out: dict[str, PersonaSchema] = {}
        for p in (self.data_dir / "personas").glob("*.json"):
            persona = PersonaSchema.model_validate(self._read(p))
            out[persona.id] = persona
        return out

    def load_schedule_templates(self) -> dict[str, ScheduleTemplateSchema]:
        out: dict[str, ScheduleTemplateSchema] = {}
        for p in (self.data_dir / "schedule_templates").glob("*.json"):
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
