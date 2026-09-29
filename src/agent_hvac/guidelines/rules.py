"""Constraint evaluation contract; enforcement is a later deterministic service."""

from typing import Protocol

from agent_hvac.schemas.design import DesignSpecification
from agent_hvac.schemas.results import ConstraintReport, SimulationResult


class ConstraintEngine(Protocol):
    def evaluate(
        self, design: DesignSpecification, result: SimulationResult
    ) -> ConstraintReport: ...
