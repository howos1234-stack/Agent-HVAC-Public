"""Optimizer interface; no optimization algorithm in P00."""

from typing import Protocol

from agent_hvac.schemas.design import DesignProblem
from agent_hvac.schemas.results import OptimizationResult


class DesignOptimizer(Protocol):
    def optimize(self, problem: DesignProblem) -> OptimizationResult: ...
