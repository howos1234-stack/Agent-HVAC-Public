"""Deterministic cold-start Cartesian sweeps, retaining every failed point."""

import csv
import io
from itertools import product
from typing import Literal, Self

from pydantic import Field, ValidationError, model_validator

from agent_hvac.properties.base import PropertyBackend
from agent_hvac.schemas.base import ContractModel, NonEmptyStr
from agent_hvac.solvers.system_cycle.convergence import solve_circuit
from agent_hvac.solvers.system_cycle.convergence_models import ConvergenceRequest, ConvergenceResult
from agent_hvac.utils.units import MassFlow, Pressure, Temperature


class OperatingMapRequest(ContractModel):
    base: ConvergenceRequest
    discharge_pressures: tuple[Pressure, ...] = Field(min_length=1, max_length=100)
    sink_inlet_temperatures: tuple[Temperature, ...] = Field(min_length=1, max_length=100)
    mass_flows: tuple[MassFlow, ...] | None = Field(default=None, min_length=1, max_length=100)
    max_points: int = Field(ge=1, le=100, strict=True)

    @model_validator(mode="after")
    def bounded_unique_grid(self) -> Self:
        if (
            len(self.discharge_pressures) * len(self.sink_inlet_temperatures) * len(self.flow_axis)
            > self.max_points
        ):
            raise ValueError("grid exceeds explicit max_points")
        for axis in (self.discharge_pressures, self.sink_inlet_temperatures, self.flow_axis):
            if len({v.value for v in axis}) != len(axis):
                raise ValueError("duplicate canonical coordinates are not allowed")
        if any(m.value <= 0 for m in self.flow_axis):
            raise ValueError("prescribed mass flows must be positive")
        return self

    @property
    def flow_axis(self) -> tuple[MassFlow, ...]:
        """Omitted axis preserves historical two-dimensional requests."""
        return (
            self.mass_flows
            if self.mass_flows is not None
            else (self.base.scenario.refrigerant_mass_flow,)
        )


class OperatingMapPoint(ContractModel):
    index: int = Field(ge=0)
    discharge_pressure: Pressure
    sink_inlet_temperature: Temperature
    prescribed_mass_flow: MassFlow | None = None  # None only for legacy 2D artifacts.
    status: Literal["converged", "unconverged", "invalid-input"]
    message: NonEmptyStr
    result: ConvergenceResult | None

    @model_validator(mode="after")
    def consistent_point(self) -> Self:
        if self.status == "invalid-input":
            if self.result is not None:
                raise ValueError("invalid input cannot have a solve result")
        elif self.result is None or self.result.status != self.status:
            raise ValueError("point status must match solve result")
        return self


class OperatingMapResult(ContractModel):
    request: OperatingMapRequest
    is_mock: Literal[True] = True
    start_policy: Literal["cold-start"] = "cold-start"
    points: tuple[OperatingMapPoint, ...]
    converged_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)

    @model_validator(mode="after")
    def complete_grid(self) -> Self:
        expected = list(
            product(
                self.request.discharge_pressures,
                self.request.sink_inlet_temperatures,
                self.request.flow_axis,
            )
        )
        if len(self.points) != len(expected):
            raise ValueError("map must retain every requested point")
        for index, (point, coords) in enumerate(zip(self.points, expected, strict=True)):
            mass = point.prescribed_mass_flow
            if mass is None:
                if self.request.mass_flows is not None:
                    raise ValueError("mass-axis points must retain their prescribed flow")
                mass = self.request.base.scenario.refrigerant_mass_flow
            if (
                point.index != index
                or (point.discharge_pressure, point.sink_inlet_temperature, mass) != coords
            ):
                raise ValueError("map order or coordinates differ from request")
            if point.result is not None:
                scenario = point.result.request.scenario
                if (
                    scenario.discharge_pressure,
                    scenario.high_side_hx.secondary_inlet_temperature,
                    scenario.refrigerant_mass_flow,
                ) != coords:
                    raise ValueError("solved request differs from map coordinates")
        successes = sum(p.status == "converged" for p in self.points)
        if self.converged_count != successes or self.failed_count != len(expected) - successes:
            raise ValueError("map summary does not match point outcomes")
        return self


def solve_operating_map(
    backend: PropertyBackend, request: OperatingMapRequest
) -> OperatingMapResult:
    request = OperatingMapRequest.model_validate(request.model_dump(mode="json"))
    points: list[OperatingMapPoint] = []
    for pressure, temperature, mass_flow in product(
        request.discharge_pressures, request.sink_inlet_temperatures, request.flow_axis
    ):
        data = request.base.model_dump(mode="json")
        data["scenario"]["refrigerant_mass_flow"] = mass_flow.model_dump(mode="json")
        data["scenario"]["discharge_pressure"] = pressure.model_dump(mode="json")
        data["scenario"][request.base.scenario.high_side_name]["secondary_inlet_temperature"] = (
            temperature.model_dump(mode="json")
        )
        data["scenario"]["scenario_id"] += f"-map-{len(points)}"
        result = None
        try:
            point_request = ConvergenceRequest.model_validate(data)
        except ValidationError as exc:
            status: Literal["converged", "unconverged", "invalid-input"] = "invalid-input"
            message = str(exc)
        else:
            # Unknown programming/backend exceptions deliberately propagate.
            result = solve_circuit(backend, point_request)
            status, message = result.status, f"{result.reason}: {result.message}"
            if not result.cycle_converged and result.last_evaluation is not None:
                failures = [p for p in result.last_evaluation.pressure_history if p.failed_stage]
                if failures:
                    last_failure = failures[-1]
                    message += (
                        f"; last component failure: {last_failure.failed_stage}: "
                        f"{last_failure.message}"
                    )

        points.append(
            OperatingMapPoint(
                index=len(points),
                discharge_pressure=pressure,
                sink_inlet_temperature=temperature,
                prescribed_mass_flow=mass_flow,
                status=status,
                message=message,
                result=result,
            )
        )
    count = sum(p.status == "converged" for p in points)
    return OperatingMapResult(
        request=request,
        points=tuple(points),
        converged_count=count,
        failed_count=len(points) - count,
    )


def operating_map_csv(result: OperatingMapResult) -> str:
    """Only converged points expose performance; failed points keep reasons/residuals."""
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "point",
            "discharge_pressure_Pa",
            "sink_inlet_temperature_K",
            "status",
            "is_mock",
            "start_policy",
            "prescribed_mass_flow_kg_s",
            "cooling_COP",
            "cooling_W",
            "compressor_W",
            f"{result.request.base.scenario.high_side_name}_rejection_W",
            "pipe_heat_to_refrigerant_W",
            "enthalpy_residual_J_kg",
            "pressure_residual_Pa",
            "enthalpy_evaluations",
            "pressure_evaluations",
            "reason",
        ]
    )
    for point in result.points:
        solved = point.result
        circuit = solved.last_evaluation if solved else None
        diag = circuit.diagnostics if circuit else None
        success = solved is not None and solved.cycle_converged
        # Prefix externally derived free text so CSV readers cannot execute formulas.
        reason = point.message
        if reason.lstrip().startswith(("=", "+", "-", "@")):
            reason = "'" + reason
        writer.writerow(
            [
                point.index,
                point.discharge_pressure.value,
                point.sink_inlet_temperature.value,
                point.status,
                True,
                result.start_policy,
                (
                    point.prescribed_mass_flow or result.request.base.scenario.refrigerant_mass_flow
                ).value,
                solved.performance.cooling_cop if solved and solved.performance else "",
                diag.evaporator_heat.value if diag and success else "",
                diag.compressor_power.value if diag and success else "",
                diag.high_side_heat_rejection.value if diag and success else "",
                sum(t.heat_to_refrigerant.value for t in circuit.components if t.pipe is not None)
                if circuit and success
                else "",
                diag.enthalpy_return_minus_trial.value if diag else "",
                diag.pressure_return_minus_trial.value if diag else "",
                len(solved.history) if solved else 0,
                sum(len(s.pressure_history) for s in solved.history) if solved else 0,
                reason,
            ]
        )
    return output.getvalue()
