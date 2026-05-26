"""Config module: pydantic schemas + data/ loader + global registry."""

from .schemas import RoomSchema, PersonaSchema, ActionSchema, FragmentSchema, ScheduleTemplateSchema
from .loader import ConfigLoader
from .registry import Registry, get_registry

__all__ = [
    "RoomSchema",
    "PersonaSchema",
    "ActionSchema",
    "FragmentSchema",
    "ScheduleTemplateSchema",
    "ConfigLoader",
    "Registry",
    "get_registry",
]
