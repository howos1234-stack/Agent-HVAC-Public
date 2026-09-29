"""Explicit outcomes prevent failed or mock runs from becoming released designs."""

from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from agent_hvac.physics.state import ThermoState
from agent_hvac.schemas.base import ContractModel, NonEmptyStr
from agent_hvac.schemas.design import DesignSpecification
from agent_hvac.schemas.provenance import RunMetadata
from agent_hvac.utils.units import MassFlow, Power, PressureDifference, Quantity


class SolverStatus(StrEnum):
    CONVERGED = "converged"
    UNCONVERGED = "unconverged"
    INFEASIBLE = "infeasible"
    INVALID_PROPERTY_STATE = "invalid-property-state"
    ENVELOPE_VIOLATION = "component-envelope-violation"


class SimulationResult(ContractModel):
    design_id: NonEmptyStr
    status: SolverStatus
    is_mock: bool
    state_points: dict[str, ThermoState] = Field(default_factory=dict)
    mass_flow: MassFlow | None = None
    compressor_power: Power | None = None
    evaporator_capacity: Power | None = None
    heat_rejection: Power | None = None
    cop: float | None = Field(default=None, ge=0)
    eer: float | None = Field(default=None, ge=0)
    pressure_drops: dict[str, PressureDifference] = Field(default_factory=dict)
    heat_exchanger_duties: dict[str, Power] = Field(default_factory=dict)
    energy_balance_error: float | None = Field(default=None, ge=0)
    mass_balance_error: float | None = Field(default=None, ge=0)
    active_constraints: tuple[str, ...] = ()
    envelope_margins: dict[str, Quantity] = Field(default_factory=dict)
    messages: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def complete_success(self) -> Self:
        if self.status == SolverStatus.CONVERGED:
            required = (
                self.mass_flow,
                self.compressor_power,
                self.evaporator_capacity,
                self.heat_rejection,
                self.cop,
                self.energy_balance_error,
                self.mass_balance_error,
            )
            if not self.state_points or any(v is None for v in required):
                raise ValueError("Converged result requires states, duties and balance residuals")
        elif not self.messages:
            raise ValueError("Failed simulation requires an explanation")
        return self


class ConstraintCheck(ContractModel):
    rule_id: NonEmptyStr
    passed: bool
    hard: bool
    message: NonEmptyStr
    margin: Quantity | None = None


class ConstraintReport(ContractModel):
    design_id: NonEmptyStr
    checks: tuple[ConstraintCheck, ...]
    feasible: bool
    is_mock: bool

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.feasible and (not self.checks or any(c.hard and not c.passed for c in self.checks)):
            raise ValueError("Feasibility requires checks and no failed hard constraint")
        return self


class RankedDesign(ContractModel):
    design: DesignSpecification
    simulation: SimulationResult
    constraints: ConstraintReport
    objective_value: Quantity

    @model_validator(mode="after")
    def eligible(self) -> Self:
        if self.simulation.status != SolverStatus.CONVERGED or not self.constraints.feasible:
            raise ValueError("Only converged feasible designs can be ranked")
        if {self.design.design_id, self.simulation.design_id, self.constraints.design_id} != {
            self.design.design_id
        }:
            raise ValueError("Design/result identifiers differ")
        if len({self.design.is_mock, self.simulation.is_mock, self.constraints.is_mock}) != 1:
            raise ValueError("Mixed mock and real artifacts")
        return self


class OptimizationResult(ContractModel):
    status: str = Field(pattern="^(completed|infeasible|failed)$")
    ranked_designs: tuple[RankedDesign, ...] = ()
    messages: tuple[NonEmptyStr, ...] = ()
    is_mock: bool

    @model_validator(mode="after")
    def valid_outcome(self) -> Self:
        if self.status == "completed" and not self.ranked_designs:
            raise ValueError("Completed optimization requires a ranked design")
        if self.status != "completed" and (self.ranked_designs or not self.messages):
            raise ValueError("Failed optimization requires reason and no ranked designs")
        if any(r.design.is_mock != self.is_mock for r in self.ranked_designs):
            raise ValueError("Mixed mock and real optimization artifacts")
        return self


class FinalDesignPackage(ContractModel):
    metadata: RunMetadata
    selected: RankedDesign
    alternatives: tuple[RankedDesign, ...] = ()
    warnings: tuple[str, ...] = ()
    approval_status: str = Field(pattern="^(not_required|pending|approved|rejected)$")
    release_ready: bool = False

    @model_validator(mode="after")
    def guard_release(self) -> Self:
        designs = (self.selected,) + self.alternatives
        if any(r.design.is_mock != self.metadata.is_mock for r in designs):
            raise ValueError("Metadata mock flag differs from design artifacts")
        if self.release_ready:
            if any(
                m.classification == "essential" for m in self.selected.design.requirements.missing
            ):
                raise ValueError("Unresolved essential requirements cannot be released")
            if self.metadata.is_mock or self.approval_status in ("pending", "rejected"):
                raise ValueError("Mock or unapproved package cannot be release-ready")
            if self.selected.design.requirements.hitl_mode != "AUTO":
                if self.approval_status != "approved":
                    raise ValueError("Human approval required by HITL policy")
        return self
