"""Simulation loop: tick clock + perceive→decide→act per agent."""

from .clock import TickClock
from .loop import SimLoop

__all__ = ["TickClock", "SimLoop"]
