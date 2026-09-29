"""Internal S2 settings, trace and result contracts (no shared schema migration)."""

import math
from typing import Literal, Self

from pydantic import Field, model_validator

from agent_hvac.schemas.base import ContractModel, NonEmptyStr
from agent_hvac.solvers.system_cycle.models import (
    CircuitResult,
    CircuitStatus,
    PressureSample,
    SyntheticScenario,
)
from agent_hvac.utils.units import PressureDifference, SpecificEnthalpy, TemperatureDifference


class ConvergenceSettings(ContractModel):
    lower_enthalpy: SpecificEnthalpy
    upper_enthalpy: SpecificEnthalpy
    scan_intervals: int = Field(ge=1, le=1000, strict=True)
    max_iterations: int = Field(ge=1, le=1000, strict=True)
    enthalpy_tolerance: SpecificEnthalpy
    pressure_tolerance: PressureDifference
    temperature_tolerance: TemperatureDifference
    relative_energy_tolerance: float = Field(gt=0, le=1e-6)
    relative_mass_tolerance: float = Field(gt=0, le=1e-12)

    @model_validator(mode="after")
    def bounds_and_tolerances(self) -> Self:
        span = self.upper_enthalpy.value - self.lower_enthalpy.value
        if not math.isfinite(span) or span <= 0:
            raise ValueError("enthalpy bounds must have a finite positive span")
        if not 0 < self.enthalpy_tolerance.value <= min(0.01, span):
            raise ValueError("enthalpy tolerance must be positive and <= min(0.01 J/kg, span)")
        if not 0 < self.pressure_tolerance.value <= 1.0:
            raise ValueError("pressure tolerance must be in (0, 1] Pa")
        if not 0 < self.temperature_tolerance.value <= 1e-4:
            raise ValueError("temperature tolerance must be in (0, 1e-4] K")
        return self


class ConvergenceRequest(ContractModel):
    scenario: SyntheticScenario
    settings: ConvergenceSettings


class IterationSample(ContractModel):
    pressure_history: tuple[PressureSample, ...] = ()
    evaluation: int = Field(ge=1)
    phase: Literal["scan", "bisection"]
    trial_enthalpy: SpecificEnthalpy
    status: CircuitStatus
    residual: SpecificEnthalpy | None
    failed_stage: str | None
    message: NonEmptyStr


class CyclePerformance(ContractModel):
    """Only populated after independent closure checks; refrigerant-side COP."""

    cooling_cop: float = Field(gt=0)
    relative_energy_error: float = Field(ge=0)
    relative_mass_error: float = Field(ge=0)


class ConvergenceResult(ContractModel):
    request: ConvergenceRequest
    is_mock: Literal[True] = True
    cycle_converged: bool
    status: Literal["converged", "unconverged"]
    reason: NonEmptyStr
    message: NonEmptyStr
    bisection_iterations: int = Field(ge=0)
    history: tuple[IterationSample, ...]
    last_evaluation: CircuitResult | None
    performance: CyclePerformance | None = None

    @model_validator(mode="after")
    def consistent_result(self) -> Self:
        success = self.status == "converged"
        if success != self.cycle_converged or success != (self.performance is not None):
            raise ValueError("only a converged result can contain performance")
        if success and (self.last_evaluation is None or self.last_evaluation.status != "evaluated"):
            raise ValueError("convergence requires a complete circuit evaluation")
        return self
