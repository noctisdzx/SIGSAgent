"""Schedule subsystem: weekly template + fragment library + 5-min timeline + STM builder."""

from .builder import bulk_build_for_day, schedule_item_to_stm
from .fragments import Fragment, FragmentLibrary
from .insert_events import (
    InsertEvent,
    InsertEventChoice,
    InsertEventLibrary,
    InsertEventSelector,
)
from .template import ScheduleTemplate, TemplateBlock
from .timeline import DailyTimeline, Slot, SlotKind

__all__ = [
    "ScheduleTemplate",
    "TemplateBlock",
    "Fragment",
    "FragmentLibrary",
    "InsertEvent",
    "InsertEventLibrary",
    "InsertEventSelector",
    "InsertEventChoice",
    "DailyTimeline",
    "Slot",
    "SlotKind",
    "schedule_item_to_stm",
    "bulk_build_for_day",
]
