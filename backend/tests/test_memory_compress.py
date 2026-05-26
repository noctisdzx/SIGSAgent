"""Placeholder test for the STM→LTM compression spec.

To be expanded once the compressor is fully wired.
"""

from app.agents.memory.short_term import ShortTermMemory, ShortTermItem
from app.agents.memory.long_term import LongTermMemory


def test_stm_capacity():
    stm = ShortTermMemory()
    assert stm.capacity == 30


def test_ltm_capacity():
    ltm = LongTermMemory()
    assert ltm.capacity == 15
