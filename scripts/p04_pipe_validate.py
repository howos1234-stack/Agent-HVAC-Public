"""Reproduce the P04 analytical, grid-convergence, and R744 pipe checks."""

from __future__ import annotations

import json
import math
from typing import Any

from CoolProp.CoolProp import PropsSI

from agent_hvac.components.pipe import (
    DynamicViscosity,
    LinearHeatTransferCoefficient,
    NonnegativeLength,
    Pipe1DInput,
    evaluate_pipe_1d,
)
from agent_hvac.physics.state import ThermoState
from agent_hvac.properties.coolprop_backend import CoolPropBackend
from agent_hvac.utils.units import (
    Density,
    Length,
    MassFlow,
    Pressure,
    SpecificEnthalpy,
    SpecificEntropy,
    Temperature,
)


class ConstantCpBackend:
    """Synthetic property path for P04 closed-form validation only."""

    def __init__(self, density_kg_m3: float, cp_j_kg_k: float) -> None:
        self.density_kg_m3 = density_kg_m3
        self.cp_j_kg_k = cp_j_kg_k

    def _state(self, fluid: str, pressure: Pressure, temperature_k: float) -> ThermoState:
        return ThermoState(
            fluid=fluid,
            pressure=pressure,
            temperature=Temperature(value=temperature_k, unit="K"),
            enthalpy=SpecificEnthalpy(
                value=100_000.0 + self.cp_j_kg_k * (temperature_k - 300.0),
                unit="J/kg",
            ),
            density=Density(value=self.density_kg_m3, unit="kg/m^3"),
            phase="liquid",
            entropy=SpecificEntropy(value=1_000.0, unit="J/(kg*K)"),
        )

    def state_ph(self, fluid: str, p: Pressure, h: SpecificEnthalpy) -> ThermoState:
        temperature_k = 300.0 + (h.value - 100_000.0) / self.cp_j_kg_k
        return self._state(fluid, p, temperature_k)

    def state_pt(self, fluid: str, p: Pressure, temperature: Temperature) -> ThermoState:
        return self._state(fluid, p, temperature.value)

    def state_ps(self, fluid: str, p: Pressure, entropy: SpecificEntropy) -> ThermoState:
        return self._state(fluid, p, 300.0)


def _synthetic_inputs(
    backend: ConstantCpBackend,
    *,
    mass_flow_kg_s: float,
    length_m: float,
    diameter_m: float,
    viscosity_pa_s: float,
    ambient_temperature_k: float,
    conductance_w_m_k: float,
    cell_count: int,
) -> Pipe1DInput:
    return Pipe1DInput(
        inlet_state=backend.state_pt(
            "synthetic-fluid",
            Pressure(value=1_000_000.0, unit="Pa"),
            Temperature(value=300.0, unit="K"),
        ),
        mass_flow=MassFlow(value=mass_flow_kg_s, unit="kg/s"),
        length=NonnegativeLength(value=length_m, unit="m"),
        inner_diameter=Length(value=diameter_m, unit="m"),
        roughness=NonnegativeLength(value=0.0, unit="m"),
        dynamic_viscosity=DynamicViscosity(value=viscosity_pa_s, unit="Pa*s"),
        ambient_temperature=Temperature(value=ambient_temperature_k, unit="K"),
        linear_heat_transfer_coefficient=LinearHeatTransferCoefficient(
            value=conductance_w_m_k,
            unit="W/(m*K)",
        ),
        cell_count=cell_count,
    )


def run_validation() -> dict[str, Any]:
    backend = ConstantCpBackend(density_kg_m3=1_000.0, cp_j_kg_k=1_000.0)
    diameter_m = 0.02
    viscosity_pa_s = 0.001
    reynolds_number = 1_000.0
    mass_flow_kg_s = reynolds_number * math.pi * diameter_m * viscosity_pa_s / 4.0
    pressure_inputs = _synthetic_inputs(
        backend,
        mass_flow_kg_s=mass_flow_kg_s,
        length_m=10.0,
        diameter_m=diameter_m,
        viscosity_pa_s=viscosity_pa_s,
        ambient_temperature_k=300.0,
        conductance_w_m_k=0.0,
        cell_count=25,
    )
    pressure_result = evaluate_pipe_1d(backend, pressure_inputs)
    area_m2 = math.pi * diameter_m**2 / 4.0
    velocity_m_s = mass_flow_kg_s / (1_000.0 * area_m2)
    expected_pressure_drop_pa = (
        0.064 * (pressure_inputs.length.value / diameter_m) * 1_000.0 * velocity_m_s**2 / 2.0
    )
    pressure_relative_error = (
        abs(pressure_result.total_pressure_drop.value - expected_pressure_drop_pa)
        / expected_pressure_drop_pa
    )

    ambient_temperature_k = 400.0
    conductance_w_m_k = 100.0
    length_m = 5.0
    thermal_mass_flow_kg_s = 1.0
    exact_outlet_temperature_k = ambient_temperature_k - (ambient_temperature_k - 300.0) * math.exp(
        -conductance_w_m_k * length_m / (thermal_mass_flow_kg_s * backend.cp_j_kg_k)
    )
    grid: list[dict[str, float | int]] = []
    errors: list[float] = []
    for cell_count in (10, 20, 40, 80):
        result = evaluate_pipe_1d(
            backend,
            _synthetic_inputs(
                backend,
                mass_flow_kg_s=thermal_mass_flow_kg_s,
                length_m=length_m,
                diameter_m=0.1,
                viscosity_pa_s=viscosity_pa_s,
                ambient_temperature_k=ambient_temperature_k,
                conductance_w_m_k=conductance_w_m_k,
                cell_count=cell_count,
            ),
        )
        error_k = abs(result.outlet_state.temperature.value - exact_outlet_temperature_k)
        errors.append(error_k)
        grid.append(
            {
                "cell_count": cell_count,
                "outlet_temperature_k": result.outlet_state.temperature.value,
                "absolute_error_k": error_k,
                "relative_mass_residual": result.relative_mass_residual,
                "relative_energy_residual": result.relative_energy_residual,
                "relative_pressure_residual": result.relative_pressure_residual,
            }
        )
    error_ratios = [coarse / fine for coarse, fine in zip(errors[:-1], errors[1:], strict=True)]

    coolprop = CoolPropBackend()
    r744_inlet = coolprop.state_pt(
        "R744",
        Pressure(value=3_000_000.0, unit="Pa"),
        Temperature(value=280.0, unit="K"),
    )
    r744_viscosity_pa_s = float(PropsSI("VISCOSITY", "P", 3_000_000.0, "T", 280.0, "R744"))
    r744_result = evaluate_pipe_1d(
        coolprop,
        Pipe1DInput(
            inlet_state=r744_inlet,
            mass_flow=MassFlow(value=0.01, unit="kg/s"),
            length=NonnegativeLength(value=0.5, unit="m"),
            inner_diameter=Length(value=0.01, unit="m"),
            roughness=NonnegativeLength(value=1.0e-6, unit="m"),
            dynamic_viscosity=DynamicViscosity(value=r744_viscosity_pa_s, unit="Pa*s"),
            ambient_temperature=Temperature(value=280.0, unit="K"),
            linear_heat_transfer_coefficient=LinearHeatTransferCoefficient(
                value=0.0,
                unit="W/(m*K)",
            ),
            cell_count=20,
        ),
    )

    passed = (
        pressure_relative_error <= 1.0e-10
        and errors == sorted(errors, reverse=True)
        and all(1.8 <= ratio <= 2.2 for ratio in error_ratios)
        and errors[-1] / exact_outlet_temperature_k <= 5.0e-4
        and r744_result.total_pressure_drop.value > 0.0
        and r744_result.relative_mass_residual <= 1.0e-12
        and r744_result.relative_energy_residual <= 1.0e-12
        and r744_result.relative_pressure_residual <= 1.0e-12
    )
    return {
        "passed": passed,
        "analytical_pressure_drop": {
            "expected_pa": expected_pressure_drop_pa,
            "calculated_pa": pressure_result.total_pressure_drop.value,
            "relative_error": pressure_relative_error,
        },
        "grid_convergence": {
            "exact_outlet_temperature_k": exact_outlet_temperature_k,
            "cases": grid,
            "successive_error_ratios": error_ratios,
        },
        "r744_half_meter": {
            "dynamic_viscosity_pa_s": r744_viscosity_pa_s,
            "pressure_drop_pa": r744_result.total_pressure_drop.value,
            "outlet_pressure_pa": r744_result.outlet_state.pressure.value,
            "outlet_temperature_k": r744_result.outlet_state.temperature.value,
            "outlet_phase": r744_result.outlet_state.phase,
            "relative_mass_residual": r744_result.relative_mass_residual,
            "relative_energy_residual": r744_result.relative_energy_residual,
            "relative_pressure_residual": r744_result.relative_pressure_residual,
            "correlations": r744_result.correlation_names,
        },
    }


def main() -> int:
    report = run_validation()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
