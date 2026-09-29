"""Deterministic four-state single-stage vapor-compression cycle."""

import math
from dataclasses import dataclass

from agent_hvac.components.compressor import evaluate_compressor
from agent_hvac.components.expansion_valve import evaluate_expansion_valve
from agent_hvac.physics.balances import (
    energy_balance_residual,
    mass_balance_residual,
    require_balances_within_tolerance,
)
from agent_hvac.physics.state import ThermoState
from agent_hvac.properties.base import PropertyBackend
from agent_hvac.utils.exceptions import InfeasibleDesignError, InvalidPropertyStateError
from agent_hvac.utils.units import MassFlow, Pressure, Temperature


@dataclass(frozen=True)
class BaselineCycleInputs:
    fluid: str
    evaporator_pressure: Pressure
    high_side_pressure: Pressure
    compressor_inlet_temperature: Temperature
    heat_rejection_outlet_temperature: Temperature
    refrigerant_mass_flow: MassFlow
    compressor_isentropic_efficiency: float


@dataclass(frozen=True)
class BaselineCycleSolution:
    state_points: dict[str, ThermoState]
    mass_flow_kg_s: float
    compressor_power_w: float
    evaporator_capacity_w: float
    heat_rejection_w: float
    cop: float
    energy_balance_error: float
    mass_balance_error: float


def _require_finite_positive(name: str, value: float) -> None:
    if not math.isfinite(value):
        raise InfeasibleDesignError(f"{name} must be finite")
    if value <= 0.0:
        raise InfeasibleDesignError(f"{name} must be positive")


def solve_baseline_cycle(
    backend: PropertyBackend,
    inputs: BaselineCycleInputs,
) -> BaselineCycleSolution:
    """Solve the approved P02 cycle using only PropertyBackend calls."""
    if inputs.high_side_pressure.value <= inputs.evaporator_pressure.value:
        raise InfeasibleDesignError("high_side_pressure must exceed evaporator_pressure")

    state_1 = backend.state_pt(
        inputs.fluid,
        inputs.evaporator_pressure,
        inputs.compressor_inlet_temperature,
    )
    if state_1.entropy is None:
        raise InvalidPropertyStateError("compressor inlet state is missing entropy")
    compressor = evaluate_compressor(
        backend,
        state_1,
        inputs.high_side_pressure,
        inputs.compressor_isentropic_efficiency,
    )
    state_2 = compressor.outlet
    state_3 = backend.state_pt(
        inputs.fluid,
        inputs.high_side_pressure,
        inputs.heat_rejection_outlet_temperature,
    )
    if state_3.entropy is None:
        raise InvalidPropertyStateError("heat-rejection outlet state is missing entropy")
    state_4 = evaluate_expansion_valve(backend, state_3, inputs.evaporator_pressure)

    mass_flow = inputs.refrigerant_mass_flow.value
    compressor_power = mass_flow * (state_2.enthalpy.value - state_1.enthalpy.value)
    evaporator_capacity = mass_flow * (state_1.enthalpy.value - state_4.enthalpy.value)
    heat_rejection = mass_flow * (state_2.enthalpy.value - state_3.enthalpy.value)
    _require_finite_positive("compressor power", compressor_power)
    _require_finite_positive("evaporator capacity", evaporator_capacity)
    _require_finite_positive("heat rejection", heat_rejection)
    cop = evaporator_capacity / compressor_power
    _require_finite_positive("cycle COP", cop)

    energy_error = energy_balance_residual(
        heat_rejection_w=heat_rejection,
        evaporator_capacity_w=evaporator_capacity,
        compressor_power_w=compressor_power,
    )
    mass_error = mass_balance_residual((mass_flow, mass_flow, mass_flow, mass_flow))
    require_balances_within_tolerance(energy_error, mass_error)
    return BaselineCycleSolution(
        state_points={
            "compressor_inlet": state_1,
            "compressor_outlet": state_2,
            "heat_rejection_outlet": state_3,
            "expansion_valve_outlet": state_4,
        },
        mass_flow_kg_s=mass_flow,
        compressor_power_w=compressor_power,
        evaporator_capacity_w=evaporator_capacity,
        heat_rejection_w=heat_rejection,
        cop=cop,
        energy_balance_error=energy_error,
        mass_balance_error=mass_error,
    )
