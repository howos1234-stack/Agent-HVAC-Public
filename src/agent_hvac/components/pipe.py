"""Steady one-dimensional single-phase refrigerant-pipe model."""

from __future__ import annotations

import math
from dataclasses import dataclass

from pydantic import Field, model_validator

from agent_hvac.physics.correlations import (
    SINGLE_PHASE_FRICTION_REGISTRY,
    CorrelationRegistry,
)
from agent_hvac.physics.state import ThermoState
from agent_hvac.properties.base import PropertyBackend
from agent_hvac.schemas.base import ContractModel
from agent_hvac.utils.exceptions import ConvergenceError, InfeasibleDesignError
from agent_hvac.utils.units import (
    Length,
    MassFlow,
    Power,
    Pressure,
    PressureDifference,
    Quantity,
    SpecificEnthalpy,
    Temperature,
)

_SINGLE_PHASES = frozenset(
    {"gas", "liquid", "supercritical", "supercritical_gas", "supercritical_liquid"}
)
_MAX_RELATIVE_CLOSURE_RESIDUAL = 1.0e-12


class NonnegativeLength(Quantity):
    """Local P04 quantity for pipe length or roughness, including the zero limit."""

    canonical_unit = "m"

    @model_validator(mode="after")
    def nonnegative(self) -> NonnegativeLength:
        if self.value < 0.0:
            raise ValueError("length must be nonnegative")
        return self


class DynamicViscosity(Quantity):
    """Constant effective dynamic viscosity supplied for this P04 run."""

    canonical_unit = "Pa*s"
    positive = True


class LinearHeatTransferCoefficient(Quantity):
    """Overall conductance per pipe length, U-prime in W/(m*K)."""

    canonical_unit = "W/(m*K)"

    @model_validator(mode="after")
    def nonnegative(self) -> LinearHeatTransferCoefficient:
        if self.value < 0.0:
            raise ValueError("linear heat-transfer coefficient must be nonnegative")
        return self


class Pipe1DInput(ContractModel):
    """Explicit, unit-bearing boundary conditions for the P04 pipe model."""

    inlet_state: ThermoState
    mass_flow: MassFlow
    length: NonnegativeLength
    inner_diameter: Length
    roughness: NonnegativeLength
    dynamic_viscosity: DynamicViscosity
    ambient_temperature: Temperature
    linear_heat_transfer_coefficient: LinearHeatTransferCoefficient
    cell_count: int = Field(ge=1)


@dataclass(frozen=True)
class PipeCellResult:
    index: int
    axial_inlet_m: float
    axial_outlet_m: float
    inlet_state: ThermoState
    outlet_state: ThermoState
    mass_flow: MassFlow
    velocity_m_s: float
    reynolds_number: float
    darcy_friction_factor: float
    friction_correlation: str
    pressure_drop: PressureDifference
    heat_transfer: Power


@dataclass(frozen=True)
class Pipe1DResult:
    inlet_state: ThermoState
    outlet_state: ThermoState
    mass_flow: MassFlow
    cells: tuple[PipeCellResult, ...]
    total_pressure_drop: PressureDifference
    total_heat_transfer: Power
    relative_mass_residual: float
    relative_energy_residual: float
    relative_pressure_residual: float
    correlation_names: tuple[str, ...]


def _require_single_phase(state: ThermoState, location: str) -> None:
    if state.phase not in _SINGLE_PHASES or state.vapor_quality is not None:
        raise InfeasibleDesignError(
            f"{location} must be single phase; two-phase pipe correlations are not implemented"
        )


def _thermal_step_crossed_ambient(
    *,
    pressure_only_temperature_k: float,
    heated_temperature_k: float,
    ambient_temperature_k: float,
) -> bool:
    """Return whether heat transfer, isolated at one pressure, crossed ambient.

    Pressure loss can change refrigerant temperature even when enthalpy is unchanged.
    Comparing the cell inlet and outlet temperatures therefore confuses that pressure
    effect with a coarse heat-transfer step.  Both temperatures used here are at the
    same outlet pressure, so their difference isolates the thermal update.
    """

    return (
        pressure_only_temperature_k < ambient_temperature_k < heated_temperature_k
        or pressure_only_temperature_k > ambient_temperature_k > heated_temperature_k
    )


def evaluate_pipe_1d(
    backend: PropertyBackend,
    inputs: Pipe1DInput,
    *,
    friction_registry: CorrelationRegistry = SINGLE_PHASE_FRICTION_REGISTRY,
) -> Pipe1DResult:
    """March pressure and enthalpy through a straight circular pipe.

    Each cell applies Darcy-Weisbach pressure loss and q=U' dx (T_ambient-T_fluid).
    Positive heat is transferred into the refrigerant. Dynamic viscosity and U' are
    explicit inputs because the frozen PropertyBackend does not expose transport data.
    """

    _require_single_phase(inputs.inlet_state, "pipe inlet")
    if inputs.length.value == 0.0:
        return Pipe1DResult(
            inlet_state=inputs.inlet_state,
            outlet_state=inputs.inlet_state,
            mass_flow=inputs.mass_flow,
            cells=(),
            total_pressure_drop=PressureDifference(value=0.0, unit="Pa"),
            total_heat_transfer=Power(value=0.0, unit="W"),
            relative_mass_residual=0.0,
            relative_energy_residual=0.0,
            relative_pressure_residual=0.0,
            correlation_names=(),
        )

    diameter_m = inputs.inner_diameter.value
    relative_roughness = inputs.roughness.value / diameter_m
    try:
        area_m2 = math.pi * diameter_m**2 / 4.0
    except OverflowError as exc:
        raise InfeasibleDesignError("pipe cross-sectional area overflowed") from exc
    if not math.isfinite(area_m2) or area_m2 <= 0.0:
        raise InfeasibleDesignError("pipe cross-sectional area must be finite and positive")
    cell_length_m = inputs.length.value / inputs.cell_count
    current = inputs.inlet_state
    cell_results: list[PipeCellResult] = []
    total_pressure_drop_pa = 0.0
    total_heat_transfer_w = 0.0
    correlation_names: list[str] = []

    for index in range(inputs.cell_count):
        density_kg_m3 = current.density.value
        velocity_m_s = inputs.mass_flow.value / (density_kg_m3 * area_m2)
        if not math.isfinite(velocity_m_s) or velocity_m_s <= 0.0:
            raise ConvergenceError(f"pipe cell {index} velocity is nonfinite or nonpositive")
        reynolds_number = density_kg_m3 * velocity_m_s * diameter_m / inputs.dynamic_viscosity.value
        correlation = friction_registry.select_darcy_friction(
            reynolds_number=reynolds_number,
            relative_roughness=relative_roughness,
            phase_regime="single_phase",
        )
        friction_factor = correlation.evaluate(reynolds_number, relative_roughness)
        try:
            pressure_drop_pa = (
                friction_factor
                * (cell_length_m / diameter_m)
                * density_kg_m3
                * velocity_m_s**2
                / 2.0
            )
        except OverflowError as exc:
            raise ConvergenceError(f"pipe cell {index} pressure loss overflowed") from exc
        heat_transfer_w = (
            inputs.linear_heat_transfer_coefficient.value
            * cell_length_m
            * (inputs.ambient_temperature.value - current.temperature.value)
        )
        next_pressure_pa = current.pressure.value - pressure_drop_pa
        next_enthalpy_j_kg = current.enthalpy.value + heat_transfer_w / inputs.mass_flow.value
        if (
            not math.isfinite(pressure_drop_pa)
            or pressure_drop_pa < 0.0
            or not math.isfinite(next_pressure_pa)
            or next_pressure_pa <= 0.0
        ):
            raise ConvergenceError(
                f"pipe cell {index} pressure loss produced a nonpositive or nonfinite pressure"
            )
        if not math.isfinite(heat_transfer_w) or not math.isfinite(next_enthalpy_j_kg):
            raise ConvergenceError(f"pipe cell {index} heat transfer produced nonfinite enthalpy")

        pressure_only_state: ThermoState | None = None
        if heat_transfer_w != 0.0:
            pressure_only_state = backend.state_ph(
                current.fluid,
                Pressure(value=next_pressure_pa, unit="Pa"),
                current.enthalpy,
            )
            if pressure_only_state.fluid != current.fluid:
                raise ConvergenceError(
                    f"pipe cell {index} property backend changed the fluid in the "
                    "pressure-only reference state"
                )
            _require_single_phase(
                pressure_only_state,
                f"pipe cell {index} pressure-only reference",
            )

        next_state = backend.state_ph(
            current.fluid,
            Pressure(value=next_pressure_pa, unit="Pa"),
            SpecificEnthalpy(value=next_enthalpy_j_kg, unit="J/kg"),
        )
        if next_state.fluid != current.fluid:
            raise ConvergenceError(f"pipe cell {index} property backend changed the fluid")
        _require_single_phase(next_state, f"pipe cell {index} outlet")
        if pressure_only_state is not None and _thermal_step_crossed_ambient(
            pressure_only_temperature_k=pressure_only_state.temperature.value,
            heated_temperature_k=next_state.temperature.value,
            ambient_temperature_k=inputs.ambient_temperature.value,
        ):
            raise ConvergenceError(
                f"pipe cell {index} heat-transfer step crossed the ambient temperature; "
                "increase cell_count"
            )

        cell_results.append(
            PipeCellResult(
                index=index,
                axial_inlet_m=index * cell_length_m,
                axial_outlet_m=(index + 1) * cell_length_m,
                inlet_state=current,
                outlet_state=next_state,
                mass_flow=inputs.mass_flow,
                velocity_m_s=velocity_m_s,
                reynolds_number=reynolds_number,
                darcy_friction_factor=friction_factor,
                friction_correlation=correlation.metadata.name,
                pressure_drop=PressureDifference(value=pressure_drop_pa, unit="Pa"),
                heat_transfer=Power(value=heat_transfer_w, unit="W"),
            )
        )
        next_total_pressure_drop_pa = total_pressure_drop_pa + pressure_drop_pa
        next_total_heat_transfer_w = total_heat_transfer_w + heat_transfer_w
        if not math.isfinite(next_total_pressure_drop_pa):
            raise ConvergenceError("total pipe pressure loss is nonfinite")
        if not math.isfinite(next_total_heat_transfer_w):
            raise ConvergenceError("total pipe heat transfer is nonfinite")
        total_pressure_drop_pa = next_total_pressure_drop_pa
        total_heat_transfer_w = next_total_heat_transfer_w
        if correlation.metadata.name not in correlation_names:
            correlation_names.append(correlation.metadata.name)
        current = next_state

    refrigerant_energy_change_w = inputs.mass_flow.value * (
        current.enthalpy.value - inputs.inlet_state.enthalpy.value
    )
    imbalance_w = refrigerant_energy_change_w - total_heat_transfer_w
    energy_scale_w = max(abs(refrigerant_energy_change_w), abs(total_heat_transfer_w), 1.0)
    relative_energy_residual = abs(imbalance_w) / energy_scale_w
    if not math.isfinite(relative_energy_residual):
        raise ConvergenceError("pipe energy residual is nonfinite")
    if relative_energy_residual > _MAX_RELATIVE_CLOSURE_RESIDUAL:
        raise ConvergenceError(
            "pipe energy closure residual "
            f"{relative_energy_residual:.6g} exceeds {_MAX_RELATIVE_CLOSURE_RESIDUAL:.6g}"
        )
    actual_pressure_drop_pa = inputs.inlet_state.pressure.value - current.pressure.value
    # Normalize closure against absolute pressure. Subtracting two O(MPa) states to
    # recover an O(Pa) loss has unavoidable cancellation at binary64 precision.
    pressure_scale_pa = max(
        abs(inputs.inlet_state.pressure.value),
        abs(current.pressure.value),
        abs(total_pressure_drop_pa),
        1.0,
    )
    relative_pressure_residual = (
        abs(actual_pressure_drop_pa - total_pressure_drop_pa) / pressure_scale_pa
    )
    if not math.isfinite(relative_pressure_residual):
        raise ConvergenceError("pipe pressure residual is nonfinite")
    if relative_pressure_residual > _MAX_RELATIVE_CLOSURE_RESIDUAL:
        raise ConvergenceError(
            "pipe pressure closure residual "
            f"{relative_pressure_residual:.6g} exceeds {_MAX_RELATIVE_CLOSURE_RESIDUAL:.6g}"
        )

    return Pipe1DResult(
        inlet_state=inputs.inlet_state,
        outlet_state=current,
        mass_flow=inputs.mass_flow,
        cells=tuple(cell_results),
        total_pressure_drop=PressureDifference(value=total_pressure_drop_pa, unit="Pa"),
        total_heat_transfer=Power(value=total_heat_transfer_w, unit="W"),
        relative_mass_residual=0.0,
        relative_energy_residual=relative_energy_residual,
        relative_pressure_residual=relative_pressure_residual,
        correlation_names=tuple(correlation_names),
    )
