"""Solver interface only. P00 contains no cycle calculation."""

from typing import Protocol

from agent_hvac.schemas.design import DesignSpecification
from agent_hvac.schemas.results import SimulationResult


class HVACSolver(Protocol):
    def simulate(self, design: DesignSpecification) -> SimulationResult: ...
