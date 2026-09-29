"""Bounded dry-room steady load sizing; no room transient or thermostat model."""

from typing import Literal, Self

from pydantic import Field, model_validator

from agent_hvac.components.heat_exchanger_1d import ThermalConductance
from agent_hvac.properties.base import PropertyBackend
from agent_hvac.schemas.base import ContractModel, NonEmptyStr
from agent_hvac.solvers.system_cycle.convergence import solve_circuit
from agent_hvac.solvers.system_cycle.convergence_models import ConvergenceRequest, ConvergenceResult
from agent_hvac.utils.units import Power, Temperature


class RoomSizingRequest(ContractModel):
    base: ConvergenceRequest
    source_ref: NonEmptyStr
    room_temperature: Temperature
    sensible_load: Power
    ua_samples: tuple[ThermalConductance, ...] = Field(min_length=2, max_length=100)
    load_tolerance: Power
    max_iterations: int = Field(ge=1, le=40, strict=True)

    @model_validator(mode="after")
    def boundaries(self) -> Self:
        if self.room_temperature != self.base.scenario.evaporator.secondary_inlet_temperature:
            raise ValueError("room temperature must equal evaporator air inlet")
        if self.base.scenario.condenser is None:
            raise ValueError("room cooling sizing requires an explicit condenser")
        if self.sensible_load.value <= 0 or not 0 < self.load_tolerance.value <= 1:
            raise ValueError("positive sensible load and tolerance in (0, 1] W required")
        values = [v.value for v in self.ua_samples]
        if any(v <= 0 for v in values) or values != sorted(set(values)):
            raise ValueError("UA samples must be strictly increasing and positive")
        return self


class RoomSample(ContractModel):
    ua: ThermalConductance
    cycle: ConvergenceResult
    load_residual: Power | None
    supply_temperature: Temperature | None
    air_balance_error: Power | None

    @model_validator(mode="after")
    def consistent(self) -> Self:
        present = (self.load_residual, self.supply_temperature, self.air_balance_error)
        if any(v is None for v in present) == self.cycle.cycle_converged:
            raise ValueError("only converged cycles may expose room performance")
        if not self.cycle.cycle_converged and any(v is not None for v in present):
            raise ValueError("failed cycles cannot expose room performance")
        return self


class RoomSizingResult(ContractModel):
    request: RoomSizingRequest
    is_mock: Literal[True] = True
    status: Literal["satisfied", "unsatisfied"]
    reason: NonEmptyStr
    history: tuple[RoomSample, ...] = Field(min_length=1)
    cycle_converged: bool
    load_balance_satisfied: bool
    design_target_satisfied: bool

    @model_validator(mode="after")
    def outcome(self) -> Self:
        last = self.history[-1]
        balanced = (
            last.load_residual is not None
            and abs(last.load_residual.value) <= self.request.load_tolerance.value
            and last.air_balance_error is not None
            and abs(last.air_balance_error.value) <= 1e-6
        )
        if self.cycle_converged != last.cycle.cycle_converged:
            raise ValueError("cycle flag must match final evaluated cycle")
        if self.load_balance_satisfied != balanced:
            raise ValueError("load flag must match the independent load/air balance")
        satisfied = self.cycle_converged and balanced
        if self.design_target_satisfied != satisfied or (self.status == "satisfied") != satisfied:
            raise ValueError("design satisfaction requires cycle and load closure")
        return self


def size_room_cooling(backend: PropertyBackend, request: RoomSizingRequest) -> RoomSizingResult:
    """Scan only explicit UA bounds, then bisect adjacent valid cycles; retain failures."""
    request = RoomSizingRequest.model_validate(request.model_dump(mode="json"))
    history: list[RoomSample] = []

    def sample(ua: float) -> float | None:
        data = request.base.model_dump(mode="json")
        data["scenario"]["evaporator"]["total_thermal_conductance"] = {"value": ua, "unit": "W/K"}
        cycle = solve_circuit(backend, ConvergenceRequest.model_validate(data))
        residual = None
        supply = None
        error = None
        if cycle.cycle_converged:
            circuit = cycle.last_evaluation
            assert circuit is not None and circuit.diagnostics is not None
            evaporator = next(
                t.heat_exchanger for t in circuit.components if t.component == "evaporator"
            )
            assert evaporator is not None
            supply = evaporator.secondary_outlet_temperature
            config = cycle.request.scenario.evaporator
            air_heat = (
                config.secondary_mass_flow.value
                * config.secondary_specific_heat_capacity.value
                * (request.room_temperature.value - supply.value)
            )
            heat = circuit.diagnostics.evaporator_heat.value
            residual = Power(value=heat - request.sensible_load.value, unit="W")
            error = Power(value=air_heat - heat, unit="W")
        history.append(
            RoomSample(
                ua=ThermalConductance(value=ua, unit="W/K"),
                cycle=cycle,
                load_residual=residual,
                supply_temperature=supply,
                air_balance_error=error,
            )
        )
        return residual.value if residual is not None else None

    def accepted() -> bool:
        last = history[-1]
        return (
            last.load_residual is not None
            and abs(last.load_residual.value) <= request.load_tolerance.value
            and last.air_balance_error is not None
            and abs(last.air_balance_error.value) <= 1e-6
        )

    def finish(reason: str) -> RoomSizingResult:
        ok = accepted()
        return RoomSizingResult(
            request=request,
            status="satisfied" if ok else "unsatisfied",
            reason=reason,
            history=tuple(history),
            cycle_converged=history[-1].cycle.cycle_converged,
            load_balance_satisfied=ok,
            design_target_satisfied=ok,
        )

    previous: tuple[float, float] | None = None
    bracket: tuple[float, float, float] | None = None
    for ua in request.ua_samples:
        residual = sample(ua.value)
        if accepted():
            return finish("cycle-and-room-load-satisfied")
        if residual is None:
            previous = None
            continue
        if previous is not None and (previous[1] < 0) != (residual < 0):
            bracket = previous[0], ua.value, previous[1]
            break
        previous = ua.value, residual
    if bracket is None:
        return finish("no-adjacent-valid-load-bracket; inspect retained cycle failures")
    lo, hi, rlo = bracket
    for _ in range(request.max_iterations):
        mid = lo + (hi - lo) / 2
        if mid in (lo, hi):
            return finish("floating-point-stagnation")
        residual = sample(mid)
        if accepted():
            return finish("cycle-and-room-load-satisfied")
        if residual is None:
            return finish("invalid-cycle-in-load-bracket")
        if (rlo < 0) == (residual < 0):
            lo, rlo = mid, residual
        else:
            hi = mid
    return finish("max-iterations")
