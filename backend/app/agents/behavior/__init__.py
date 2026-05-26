"""Behavior subsystem: GOAP-style action specs + runtime executor."""

from .action_specs import ActionSpecLibrary, ActionSpecDoc
from .executor import BehaviorExecutor

__all__ = ["ActionSpecLibrary", "ActionSpecDoc", "BehaviorExecutor"]
