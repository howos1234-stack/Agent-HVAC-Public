"""Finite, explicit design-case studies around the unchanged synthetic cycle solver."""

import csv
import io
from collections.abc import Callable
from typing import Literal, Self

from pydantic import Field, model_validator

from agent_hvac.properties.base import PropertyBackend
from agent_hvac.schemas.base import ContractModel, NonEmptyStr
from agent_hvac.solvers.system_cycle.convergence import solve_circuit
from agent_hvac.solvers.system_cycle.convergence_models import ConvergenceRequest, ConvergenceResult
from agent_hvac.utils.units import MassFlow, Power, Temperature


class DesignCase(ContractModel):
    case_id: NonEmptyStr
    family: NonEmptyStr
    source_ref: NonEmptyStr
    cycle_request: ConvergenceRequest
    sensible_load: Power

    @model_validator(mode="after")
    def positive_load(self) -> Self:
        if self.sensible_load.value <= 0:
            raise ValueError("sensible load must be positive")
        if self.cycle_request.scenario.condenser is None:
            raise ValueError("design study requires an explicit condenser")
        return self


class DesignStudyRequest(ContractModel):
    source_ref: NonEmptyStr
    refrigerant: NonEmptyStr
    refrigerant_mass_flow: MassFlow
    room_temperature: Temperature
    cases: tuple[DesignCase, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def preserve_fixed_requirements(self) -> Self:
        if len({c.case_id for c in self.cases}) != len(self.cases):
            raise ValueError("case identifiers must be unique")
        for case in self.cases:
            s = case.cycle_request.scenario
            if (
                s.refrigerant != self.refrigerant
                or s.refrigerant_mass_flow != self.refrigerant_mass_flow
                or s.evaporator.secondary_inlet_temperature != self.room_temperature
            ):
                raise ValueError("case changed fixed refrigerant, mass flow or room boundary")
        return self


class DesignPoint(ContractModel):
    case: DesignCase
    cycle: ConvergenceResult
    cooling_design_eligible: bool
    eligibility_reason: NonEmptyStr
    cooling: Power | None = None
    load_residual: Power | None = None
    supply_temperature: Temperature | None = None
    air_balance_error: Power | None = None
    load_balance_satisfied: bool

    @model_validator(mode="after")
    def consistent_result(self) -> Self:
        if self.cycle.request != self.case.cycle_request:
            raise ValueError("cycle must correspond to the requested case")
        values = (self.cooling, self.load_residual, self.supply_temperature, self.air_balance_error)
        if self.cycle.cycle_converged:
            if any(v is None for v in values):
                raise ValueError("converged case must retain its actual room metrics")
            circuit = self.cycle.last_evaluation
            assert circuit is not None and circuit.diagnostics is not None
            eligible = (
                circuit.nodes["condenser_outlet"].phase == "liquid"
                and circuit.nodes["suction_trial"].phase == "gas"
                and circuit.nodes["suction_return"].phase == "gas"
            )
            if self.cooling_design_eligible != eligible:
                raise ValueError("eligibility must match actual phase states")
            hx = next(t.heat_exchanger for t in circuit.components if t.component == "evaporator")
            assert hx is not None and self.air_balance_error is not None
            config = self.case.cycle_request.scenario.evaporator
            air = (
                config.secondary_mass_flow.value
                * config.secondary_specific_heat_capacity.value
                * (config.secondary_inlet_temperature.value - hx.secondary_outlet_temperature.value)
            )
            if (
                self.cooling != circuit.diagnostics.evaporator_heat
                or self.supply_temperature != hx.secondary_outlet_temperature
                or self.air_balance_error.value != air - circuit.diagnostics.evaporator_heat.value
            ):
                raise ValueError("room metrics must match actual cycle and air boundary")
        elif any(v is not None for v in values) or self.cooling_design_eligible:
            raise ValueError("unconverged case cannot expose room performance or eligibility")
        if self.cooling is not None and self.load_residual is not None:
            if self.load_residual.value != self.cooling.value - self.case.sensible_load.value:
                raise ValueError("load residual must reflect the requested load")
        matched = (
            self.cooling_design_eligible
            and self.load_residual is not None
            and abs(self.load_residual.value) <= 1.0
            and self.air_balance_error is not None
            and abs(self.air_balance_error.value) <= 1e-6
        )
        if self.load_balance_satisfied != matched:
            raise ValueError("load match requires eligible closure and independent air balance")
        return self


class DesignStudyResult(ContractModel):
    is_mock: Literal[True] = True
    request: DesignStudyRequest
    points: tuple[DesignPoint, ...]

    @model_validator(mode="after")
    def complete_study(self) -> Self:
        if tuple(p.case for p in self.points) != self.request.cases:
            raise ValueError("study must preserve every requested case in order")
        return self


def evaluate_design_case(backend: PropertyBackend, case: DesignCase) -> DesignPoint:
    """Keep actual failure results; unexpected implementation errors propagate."""
    case = DesignCase.model_validate(case.model_dump(mode="json"))
    cycle = solve_circuit(backend, case.cycle_request)
    if not cycle.cycle_converged:
        return DesignPoint(
            case=case,
            cycle=cycle,
            cooling_design_eligible=False,
            eligibility_reason=f"unconverged: {cycle.reason}",
            load_balance_satisfied=False,
        )
    circuit = cycle.last_evaluation
    assert circuit is not None and circuit.diagnostics is not None
    eligible = (
        circuit.nodes["condenser_outlet"].phase == "liquid"
        and circuit.nodes["suction_trial"].phase == "gas"
        and circuit.nodes["suction_return"].phase == "gas"
    )
    evaporator = next(t.heat_exchanger for t in circuit.components if t.component == "evaporator")
    assert evaporator is not None
    config = case.cycle_request.scenario.evaporator
    supply = evaporator.secondary_outlet_temperature
    cooling = circuit.diagnostics.evaporator_heat
    air = (
        config.secondary_mass_flow.value
        * config.secondary_specific_heat_capacity.value
        * (config.secondary_inlet_temperature.value - supply.value)
    )
    residual = cooling.value - case.sensible_load.value
    error = air - cooling.value
    return DesignPoint(
        case=case,
        cycle=cycle,
        cooling_design_eligible=eligible,
        eligibility_reason="liquid condenser outlet and dry suction"
        if eligible
        else "phase requirements for the declared liquid-outlet cooling design not satisfied",
        cooling=cooling,
        load_residual=Power(value=residual, unit="W"),
        supply_temperature=supply,
        air_balance_error=Power(value=error, unit="W"),
        load_balance_satisfied=eligible and abs(residual) <= 1.0 and abs(error) <= 1e-6,
    )


def solve_design_study(
    backend: PropertyBackend,
    request: DesignStudyRequest,
    *,
    on_point: Callable[[DesignPoint], None] | None = None,
) -> DesignStudyResult:
    """Explicit cold-start cases; no extrapolation, implicit retries or dropped points."""
    request = DesignStudyRequest.model_validate(request.model_dump(mode="json"))
    points = []
    for case in request.cases:
        point = evaluate_design_case(backend, case)
        points.append(point)
        if on_point is not None:
            on_point(point)
    return DesignStudyResult(request=request, points=tuple(points))


def design_study_csv(result: DesignStudyResult) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(
        [
            "case",
            "family",
            "cycle_converged",
            "cooling_design_eligible",
            "load_matched",
            "suction_Pa",
            "discharge_Pa",
            "outdoor_K",
            "indoor_air_kg_s",
            "outdoor_air_kg_s",
            "condenser_UA_W_K",
            "evaporator_UA_W_K",
            "load_W",
            "cooling_W",
            "compressor_W",
            "COP",
            "supply_K",
            "load_residual_W",
            "reason",
        ]
    )

    def safe(text: str) -> str:
        return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text

    for point in result.points:
        s = point.case.cycle_request.scenario
        circuit = point.cycle.last_evaluation
        diag = circuit.diagnostics if circuit and point.cycle.cycle_converged else None
        performance = point.cycle.performance
        writer.writerow(
            [
                safe(point.case.case_id),
                safe(point.case.family),
                point.cycle.cycle_converged,
                point.cooling_design_eligible,
                point.load_balance_satisfied,
                s.suction_pressure.value,
                s.discharge_pressure.value,
                s.high_side_hx.secondary_inlet_temperature.value,
                s.evaporator.secondary_mass_flow.value,
                s.high_side_hx.secondary_mass_flow.value,
                s.high_side_hx.total_thermal_conductance.value,
                s.evaporator.total_thermal_conductance.value,
                point.case.sensible_load.value,
                point.cooling.value if point.cooling else "",
                diag.compressor_power.value if diag else "",
                performance.cooling_cop if performance else "",
                point.supply_temperature.value if point.supply_temperature else "",
                point.load_residual.value if point.load_residual else "",
                safe(point.eligibility_reason),
            ]
        )
    return stream.getvalue()


class FanControlDecision(ContractModel):
    """Steady sampled fan setting, not hardware commands or a temperature controller."""

    load: Power
    matched_case_id: str | None
    continuous_flow_solution_found: bool
    reference_on_fraction: float | None = Field(default=None, ge=0, le=1)
    reference_time_average_mass_flow: MassFlow | None = None
    on_off_satisfies_continuous_flow: Literal[False] = False


def assess_fan_control(
    result: DesignStudyResult, reference_case_id: str, loads: tuple[Power, ...]
) -> tuple[FanControlDecision, ...]:
    """Only fan flow may vary. UA, pressures, outdoor condition and hardware stay fixed.

    Duty arithmetic is a rejected continuous-flow alternative, not a simulated
    transient, electrical COP, or assertion that a real thermostat maintains 21 C.
    """
    result = DesignStudyResult.model_validate(result.model_dump(mode="json"))
    reference = next((p for p in result.points if p.case.case_id == reference_case_id), None)
    if reference is None or not reference.cooling_design_eligible or reference.cooling is None:
        raise ValueError("reference must be an eligible converged case")
    if not loads or any(q.value <= 0 for q in loads):
        raise ValueError("explicit positive loads are required")

    def fixed_config(point: DesignPoint) -> str:
        return point.case.cycle_request.scenario.model_dump_json(
            exclude={
                "scenario_id": True,
                "source_ref": True,
                "assumptions": True,
                "condenser": {"source_ref", "secondary_mass_flow"},
                "evaporator": {"source_ref", "secondary_mass_flow"},
            }
        )

    fixed = fixed_config(reference)
    candidates = [
        p for p in result.points if p.cooling_design_eligible and fixed_config(p) == fixed
    ]
    decisions = []
    for load in loads:
        matched = next(
            (
                p.case.case_id
                for p in candidates
                if p.cooling is not None
                and abs(p.cooling.value - load.value) <= 1.0
                and p.air_balance_error is not None
                and abs(p.air_balance_error.value) <= 1e-6
            ),
            None,
        )
        fraction = (
            load.value / reference.cooling.value if load.value < reference.cooling.value else None
        )
        decisions.append(
            FanControlDecision(
                load=load,
                matched_case_id=matched,
                continuous_flow_solution_found=matched is not None,
                reference_on_fraction=fraction,
                reference_time_average_mass_flow=MassFlow(
                    value=fraction * result.request.refrigerant_mass_flow.value, unit="kg/s"
                )
                if fraction is not None
                else None,
            )
        )
    return tuple(decisions)
