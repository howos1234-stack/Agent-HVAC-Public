"""Structured tool contracts independent of any LLM SDK."""

from typing import Protocol

from agent_hvac.schemas.base import ContractModel
from agent_hvac.schemas.design import DesignSpecification
from agent_hvac.schemas.results import SimulationResult


class SimulateDesignInput(ContractModel):
    design: DesignSpecification


class SimulateDesignOutput(ContractModel):
    result: SimulationResult


class SimulationTool(Protocol):
    def __call__(self, request: SimulateDesignInput) -> SimulateDesignOutput: ...
