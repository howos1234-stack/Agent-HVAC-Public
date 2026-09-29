"""Steady co-current one-dimensional refrigerant heat-exchanger model."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from pydantic import Field, model_validator

from agent_hvac.physics.state import ThermoState
from agent_hvac.properties.base import PropertyBackend
from agent_hvac.schemas.base import ContractModel
from agent_hvac.utils.exceptions import ConvergenceError, InfeasibleDesignError
from agent_hvac.utils.units import (
    MassFlow,
    Power,
    Pressure,
    PressureDifference,
    Quantity,
    SpecificEnthalpy,
    Temperature,
)

_MAX_RELATIVE_CLOSURE_RESIDUAL = 1.0e-12
_EVAPORATOR_CONDENSER_PHASES = frozenset({"gas", "supercritical_gas", "liquid", "twophase"})
_GAS_COOLER_PHASES = frozenset({"supercritical", "supercritical_liquid"})


class HeatExchangerMode(StrEnum):
    """Physical duty expected from the shared P05 marching kernel."""

    EVAPORATOR = "evaporator"
    CONDENSER = "condenser"
    GAS_COOLER = "gas_cooler"


class ThermalConductance(Quantity):
    """Total heat-exchanger conductance, UA, including the zero-duty limit."""

    canonical_unit = "W/K"

    @model_validator(mode="after")
    def nonnegative(self) -> ThermalConductance:
        if self.value < 0.0:
            raise ValueError("thermal conductance must be nonnegative")
        return self


class SpecificHeatCapacity(Quantity):
    """Constant effective heat capacity of the dry secondary stream."""

    canonical_unit = "J/(kg*K)"
    positive = True


class HeatExchanger1DInput(ContractModel):
    """Explicit, unit-bearing boundary conditions for the P05 model."""

    mode: HeatExchangerMode
    refrigerant_inlet_state: ThermoState
    refrigerant_mass_flow: MassFlow
    secondary_inlet_temperature: Temperature
    secondary_mass_flow: MassFlow
    secondary_specific_heat_capacity: SpecificHeatCapacity
    total_thermal_conductance: ThermalConductance
    refrigerant_pressure_drop: PressureDifference
    cell_count: int = Field(ge=1)


@dataclass(frozen=True)
class HeatExchangerCellResult:
    index: int
    normalized_inlet: float
    normalized_outlet: float
    refrigerant_inlet_state: ThermoState
    refrigerant_outlet_state: ThermoState
    secondary_inlet_temperature: Temperature
    secondary_outlet_temperature: Temperature
    heat_to_refrigerant: Power
    pressure_drop: PressureDifference


@dataclass(frozen=True)
class HeatExchanger1DResult:
    mode: HeatExchangerMode
    refrigerant_inlet_state: ThermoState
    refrigerant_outlet_state: ThermoState
    refrigerant_mass_flow: MassFlow
    secondary_inlet_temperature: Temperature
    secondary_outlet_temperature: Temperature
    secondary_mass_flow: MassFlow
    cells: tuple[HeatExchangerCellResult, ...]
    total_heat_to_refrigerant: Power
    total_refrigerant_pressure_drop: PressureDifference
    relative_refrigerant_energy_residual: float
    relative_secondary_energy_residual: float
    relative_pressure_residual: float
    phase_profile: tuple[str, ...]


def _require_mode_phase(mode: HeatExchangerMode, state: ThermoState, location: str) -> None:
    if state.phase == "twophase":
        if state.vapor_quality is None:
            raise InfeasibleDesignError(f"{location} has a two-phase state without vapor quality")
    elif state.vapor_quality is not None:
        raise InfeasibleDesignError(f"{location} has vapor quality outside a two-phase state")

    if mode is HeatExchangerMode.GAS_COOLER:
        if state.phase not in _GAS_COOLER_PHASES:
            raise InfeasibleDesignError(
                f"{location} must remain in the quality-free high-pressure region for "
                "gas_cooler mode"
            )
    elif state.phase not in _EVAPORATOR_CONDENSER_PHASES:
        raise InfeasibleDesignError(
            f"{location} phase {state.phase!r} cannot be treated as {mode.value}"
        )


def _require_driving_direction(
    mode: HeatExchangerMode,
    secondary_temperature_k: float,
    refrigerant_temperature_k: float,
    location: str,
) -> None:
    difference_k = secondary_temperature_k - refrigerant_temperature_k
    if mode is HeatExchangerMode.EVAPORATOR and difference_k <= 0.0:
        raise InfeasibleDesignError(
            f"{location} requires the secondary stream to be hotter than the refrigerant"
        )
    if mode in {HeatExchangerMode.CONDENSER, HeatExchangerMode.GAS_COOLER} and difference_k >= 0.0:
        raise InfeasibleDesignError(
            f"{location} requires the secondary stream to be colder than the refrigerant"
        )


def _append_phase(profile: list[str], phase: str) -> None:
    if not profile or profile[-1] != phase:
        profile.append(phase)


def _state_ph_with_closure(
    backend: PropertyBackend,
    *,
    fluid: str,
    pressure_pa: float,
    enthalpy_j_kg: float,
    mode: HeatExchangerMode,
    location: str,
) -> ThermoState:
    state = backend.state_ph(
        fluid,
        Pressure(value=pressure_pa, unit="Pa"),
        SpecificEnthalpy(value=enthalpy_j_kg, unit="J/kg"),
    )
    if state.fluid != fluid:
        raise ConvergenceError(f"{location} property backend changed the fluid")
    _require_mode_phase(mode, state, location)

    pressure_error_pa = abs(state.pressure.value - pressure_pa)
    enthalpy_error_j_kg = abs(state.enthalpy.value - enthalpy_j_kg)
    pressure_scale_pa = max(abs(pressure_pa), 1.0)
    enthalpy_scale_j_kg = max(abs(enthalpy_j_kg), 1.0)
    if pressure_error_pa / pressure_scale_pa > _MAX_RELATIVE_CLOSURE_RESIDUAL:
        raise ConvergenceError(
            f"{location} property pressure closure exceeded {_MAX_RELATIVE_CLOSURE_RESIDUAL:.6g}"
        )
    if enthalpy_error_j_kg / enthalpy_scale_j_kg > _MAX_RELATIVE_CLOSURE_RESIDUAL:
        raise ConvergenceError(
            f"{location} property enthalpy closure exceeded {_MAX_RELATIVE_CLOSURE_RESIDUAL:.6g}"
        )
    return state


def evaluate_heat_exchanger_1d(
    backend: PropertyBackend,
    inputs: HeatExchanger1DInput,
) -> HeatExchanger1DResult:
    """March a constant-UA co-current heat exchanger through equal-UA cells.

    Positive heat is transferred into the refrigerant. The secondary stream has a
    caller-supplied constant effective heat capacity. No empirical heat-transfer or
    pressure-drop correlation and no product data are inferred by this function.
    """

    inlet = inputs.refrigerant_inlet_state
    _require_mode_phase(inputs.mode, inlet, "heat-exchanger inlet")
    if inputs.total_thermal_conductance.value > 0.0:
        _require_driving_direction(
            inputs.mode,
            inputs.secondary_inlet_temperature.value,
            inlet.temperature.value,
            "heat-exchanger inlet",
        )

    pressure_drop_per_cell_pa = inputs.refrigerant_pressure_drop.value / inputs.cell_count
    conductance_per_cell_w_k = inputs.total_thermal_conductance.value / inputs.cell_count
    secondary_capacity_rate_w_k = (
        inputs.secondary_mass_flow.value * inputs.secondary_specific_heat_capacity.value
    )
    if not math.isfinite(secondary_capacity_rate_w_k) or secondary_capacity_rate_w_k <= 0.0:
        raise InfeasibleDesignError("secondary heat-capacity rate must be finite and positive")

    current_refrigerant = inlet
    current_secondary_temperature_k = inputs.secondary_inlet_temperature.value
    cell_results: list[HeatExchangerCellResult] = []
    phase_profile: list[str] = []
    _append_phase(phase_profile, inlet.phase)
    total_heat_w = 0.0
    total_pressure_drop_pa = 0.0

    for index in range(inputs.cell_count):
        local_difference_k = current_secondary_temperature_k - current_refrigerant.temperature.value
        try:
            heat_to_refrigerant_w = conductance_per_cell_w_k * local_difference_k
            next_enthalpy_j_kg = (
                current_refrigerant.enthalpy.value
                + heat_to_refrigerant_w / inputs.refrigerant_mass_flow.value
            )
            next_secondary_temperature_k = (
                current_secondary_temperature_k
                - heat_to_refrigerant_w / secondary_capacity_rate_w_k
            )
        except OverflowError as exc:
            raise ConvergenceError(
                f"heat-exchanger cell {index} thermal update overflowed"
            ) from exc

        next_pressure_pa = current_refrigerant.pressure.value - pressure_drop_per_cell_pa
        if not all(
            math.isfinite(value)
            for value in (
                heat_to_refrigerant_w,
                next_enthalpy_j_kg,
                next_secondary_temperature_k,
                next_pressure_pa,
            )
        ):
            raise ConvergenceError(f"heat-exchanger cell {index} produced a nonfinite state")
        if next_pressure_pa <= 0.0:
            raise ConvergenceError(
                f"heat-exchanger cell {index} pressure drop produced nonpositive pressure"
            )
        if next_secondary_temperature_k <= 0.0:
            raise ConvergenceError(
                f"heat-exchanger cell {index} produced nonpositive secondary temperature"
            )
        if inputs.mode is HeatExchangerMode.EVAPORATOR and heat_to_refrigerant_w < 0.0:
            raise ConvergenceError(f"evaporator cell {index} reversed heat-flow direction")
        if (
            inputs.mode in {HeatExchangerMode.CONDENSER, HeatExchangerMode.GAS_COOLER}
            and heat_to_refrigerant_w > 0.0
        ):
            raise ConvergenceError(f"{inputs.mode.value} cell {index} reversed heat-flow direction")

        pressure_only_refrigerant = _state_ph_with_closure(
            backend,
            fluid=current_refrigerant.fluid,
            pressure_pa=next_pressure_pa,
            enthalpy_j_kg=current_refrigerant.enthalpy.value,
            mode=inputs.mode,
            location=f"heat-exchanger cell {index} pressure-only outlet",
        )
        if heat_to_refrigerant_w == 0.0:
            next_refrigerant = pressure_only_refrigerant
        else:
            next_refrigerant = _state_ph_with_closure(
                backend,
                fluid=current_refrigerant.fluid,
                pressure_pa=next_pressure_pa,
                enthalpy_j_kg=next_enthalpy_j_kg,
                mode=inputs.mode,
                location=f"heat-exchanger cell {index} outlet",
            )

        if heat_to_refrigerant_w == 0.0:
            thermal_only_refrigerant = current_refrigerant
        else:
            thermal_only_refrigerant = _state_ph_with_closure(
                backend,
                fluid=current_refrigerant.fluid,
                pressure_pa=current_refrigerant.pressure.value,
                enthalpy_j_kg=next_enthalpy_j_kg,
                mode=inputs.mode,
                location=f"heat-exchanger cell {index} thermal-only outlet",
            )
        thermal_only_difference_k = (
            next_secondary_temperature_k - thermal_only_refrigerant.temperature.value
        )
        if local_difference_k * thermal_only_difference_k < 0.0:
            raise ConvergenceError(
                f"heat-exchanger cell {index} crossed the local stream temperatures; "
                "increase cell_count"
            )

        secondary_inlet = Temperature(value=current_secondary_temperature_k, unit="K")
        secondary_outlet = Temperature(value=next_secondary_temperature_k, unit="K")
        cell_results.append(
            HeatExchangerCellResult(
                index=index,
                normalized_inlet=index / inputs.cell_count,
                normalized_outlet=(index + 1) / inputs.cell_count,
                refrigerant_inlet_state=current_refrigerant,
                refrigerant_outlet_state=next_refrigerant,
                secondary_inlet_temperature=secondary_inlet,
                secondary_outlet_temperature=secondary_outlet,
                heat_to_refrigerant=Power(value=heat_to_refrigerant_w, unit="W"),
                pressure_drop=PressureDifference(value=pressure_drop_per_cell_pa, unit="Pa"),
            )
        )
        next_total_heat_w = total_heat_w + heat_to_refrigerant_w
        next_total_pressure_drop_pa = total_pressure_drop_pa + pressure_drop_per_cell_pa
        if not math.isfinite(next_total_heat_w) or not math.isfinite(next_total_pressure_drop_pa):
            raise ConvergenceError("heat-exchanger cumulative result is nonfinite")
        total_heat_w = next_total_heat_w
        total_pressure_drop_pa = next_total_pressure_drop_pa
        current_refrigerant = next_refrigerant
        current_secondary_temperature_k = next_secondary_temperature_k
        _append_phase(phase_profile, current_refrigerant.phase)

    refrigerant_energy_change_w = inputs.refrigerant_mass_flow.value * (
        current_refrigerant.enthalpy.value - inlet.enthalpy.value
    )
    secondary_energy_loss_w = secondary_capacity_rate_w_k * (
        inputs.secondary_inlet_temperature.value - current_secondary_temperature_k
    )
    energy_scale_w = max(
        abs(total_heat_w),
        abs(refrigerant_energy_change_w),
        abs(secondary_energy_loss_w),
        1.0,
    )
    relative_refrigerant_energy_residual = (
        abs(refrigerant_energy_change_w - total_heat_w) / energy_scale_w
    )
    relative_secondary_energy_residual = (
        abs(secondary_energy_loss_w - total_heat_w) / energy_scale_w
    )
    actual_pressure_drop_pa = inlet.pressure.value - current_refrigerant.pressure.value
    pressure_scale_pa = max(
        abs(inlet.pressure.value),
        abs(current_refrigerant.pressure.value),
        abs(total_pressure_drop_pa),
        1.0,
    )
    relative_pressure_residual = (
        abs(actual_pressure_drop_pa - total_pressure_drop_pa) / pressure_scale_pa
    )
    residuals = (
        relative_refrigerant_energy_residual,
        relative_secondary_energy_residual,
        relative_pressure_residual,
    )
    if not all(math.isfinite(value) for value in residuals):
        raise ConvergenceError("heat-exchanger closure residual is nonfinite")
    if relative_refrigerant_energy_residual > _MAX_RELATIVE_CLOSURE_RESIDUAL:
        raise ConvergenceError(
            "refrigerant energy closure residual "
            f"{relative_refrigerant_energy_residual:.6g} exceeds "
            f"{_MAX_RELATIVE_CLOSURE_RESIDUAL:.6g}"
        )
    if relative_secondary_energy_residual > _MAX_RELATIVE_CLOSURE_RESIDUAL:
        raise ConvergenceError(
            "secondary energy closure residual "
            f"{relative_secondary_energy_residual:.6g} exceeds "
            f"{_MAX_RELATIVE_CLOSURE_RESIDUAL:.6g}"
        )
    if relative_pressure_residual > _MAX_RELATIVE_CLOSURE_RESIDUAL:
        raise ConvergenceError(
            "heat-exchanger pressure closure residual "
            f"{relative_pressure_residual:.6g} exceeds "
            f"{_MAX_RELATIVE_CLOSURE_RESIDUAL:.6g}"
        )

    return HeatExchanger1DResult(
        mode=inputs.mode,
        refrigerant_inlet_state=inlet,
        refrigerant_outlet_state=current_refrigerant,
        refrigerant_mass_flow=inputs.refrigerant_mass_flow,
        secondary_inlet_temperature=inputs.secondary_inlet_temperature,
        secondary_outlet_temperature=Temperature(
            value=current_secondary_temperature_k,
            unit="K",
        ),
        secondary_mass_flow=inputs.secondary_mass_flow,
        cells=tuple(cell_results),
        total_heat_to_refrigerant=Power(value=total_heat_w, unit="W"),
        total_refrigerant_pressure_drop=PressureDifference(
            value=total_pressure_drop_pa,
            unit="Pa",
        ),
        relative_refrigerant_energy_residual=relative_refrigerant_energy_residual,
        relative_secondary_energy_residual=relative_secondary_energy_residual,
        relative_pressure_residual=relative_pressure_residual,
        phase_profile=tuple(phase_profile),
    )
