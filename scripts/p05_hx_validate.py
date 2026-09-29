"""Emit deterministic P05 analytical and R744 gas-cooler validation evidence."""

from __future__ import annotations

import json
import math

from agent_hvac.components.heat_exchanger_1d import (
    HeatExchanger1DInput,
    HeatExchangerMode,
    SpecificHeatCapacity,
    ThermalConductance,
    evaluate_heat_exchanger_1d,
)
from agent_hvac.physics.state import ThermoState
from agent_hvac.properties.coolprop_backend import CoolPropBackend
from agent_hvac.utils.units import (
    Density,
    MassFlow,
    Pressure,
    PressureDifference,
    SpecificEnthalpy,
    SpecificEntropy,
    Temperature,
)


class ConstantCpBackend:
    """Analytical backend used only for the constant-cp validation limit."""

    def _state(self, fluid: str, pressure: Pressure, enthalpy_j_kg: float) -> ThermoState:
        return ThermoState(
            fluid=fluid,
            pressure=pressure,
            temperature=Temperature(value=enthalpy_j_kg / 1_000.0, unit="K"),
            enthalpy=SpecificEnthalpy(value=enthalpy_j_kg, unit="J/kg"),
            density=Density(value=10.0, unit="kg/m^3"),
            phase="liquid",
            entropy=SpecificEntropy(value=1_000.0, unit="J/(kg*K)"),
        )

    def state_ph(self, fluid: str, p: Pressure, h: SpecificEnthalpy) -> ThermoState:
        return self._state(fluid, p, h.value)

    def state_pt(self, fluid: str, p: Pressure, temperature: Temperature) -> ThermoState:
        return self._state(fluid, p, 1_000.0 * temperature.value)

    def state_ps(self, fluid: str, p: Pressure, entropy: SpecificEntropy) -> ThermoState:
        return self._state(fluid, p, 300_000.0)


def _analytical_case() -> dict[str, object]:
    backend = ConstantCpBackend()
    inlet = backend.state_pt(
        "synthetic-fluid",
        Pressure(value=1_000_000.0, unit="Pa"),
        Temperature(value=300.0, unit="K"),
    )
    conductance_w_k = 500.0
    refrigerant_capacity_rate_w_k = 1_000.0
    secondary_capacity_rate_w_k = 2_000.0
    exact_heat_w = (
        100.0
        * (
            1.0
            - math.exp(
                -conductance_w_k
                * (1.0 / refrigerant_capacity_rate_w_k + 1.0 / secondary_capacity_rate_w_k)
            )
        )
        / (1.0 / refrigerant_capacity_rate_w_k + 1.0 / secondary_capacity_rate_w_k)
    )
    exact_outlet_k = 300.0 + exact_heat_w / refrigerant_capacity_rate_w_k
    rows: list[dict[str, float | int]] = []
    errors: list[float] = []
    for cell_count in (10, 20, 40, 80):
        result = evaluate_heat_exchanger_1d(
            backend,
            HeatExchanger1DInput(
                mode=HeatExchangerMode.EVAPORATOR,
                refrigerant_inlet_state=inlet,
                refrigerant_mass_flow=MassFlow(value=1.0, unit="kg/s"),
                secondary_inlet_temperature=Temperature(value=400.0, unit="K"),
                secondary_mass_flow=MassFlow(value=2.0, unit="kg/s"),
                secondary_specific_heat_capacity=SpecificHeatCapacity(
                    value=1_000.0,
                    unit="J/(kg*K)",
                ),
                total_thermal_conductance=ThermalConductance(
                    value=conductance_w_k,
                    unit="W/K",
                ),
                refrigerant_pressure_drop=PressureDifference(value=0.0, unit="Pa"),
                cell_count=cell_count,
            ),
        )
        error_k = abs(result.refrigerant_outlet_state.temperature.value - exact_outlet_k)
        errors.append(error_k)
        rows.append(
            {
                "cell_count": cell_count,
                "outlet_temperature_k": result.refrigerant_outlet_state.temperature.value,
                "absolute_error_k": error_k,
                "refrigerant_energy_residual": result.relative_refrigerant_energy_residual,
                "secondary_energy_residual": result.relative_secondary_energy_residual,
            }
        )
    error_ratios = [coarse / fine for coarse, fine in zip(errors[:-1], errors[1:], strict=True)]
    assert errors == sorted(errors, reverse=True)
    assert all(1.8 <= ratio <= 2.2 for ratio in error_ratios)
    assert errors[-1] / exact_outlet_k <= 5.0e-4
    return {
        "exact_heat_w": exact_heat_w,
        "exact_outlet_temperature_k": exact_outlet_k,
        "rows": rows,
        "error_ratios": error_ratios,
    }


def _r744_case() -> dict[str, object]:
    backend = CoolPropBackend()
    inlet = backend.state_pt(
        "R744",
        Pressure(value=9_000_000.0, unit="Pa"),
        Temperature(value=375.6681128305702, unit="K"),
    )
    result = evaluate_heat_exchanger_1d(
        backend,
        HeatExchanger1DInput(
            mode=HeatExchangerMode.GAS_COOLER,
            refrigerant_inlet_state=inlet,
            refrigerant_mass_flow=MassFlow(value=0.1, unit="kg/s"),
            secondary_inlet_temperature=Temperature(value=290.0, unit="K"),
            secondary_mass_flow=MassFlow(value=1.0, unit="kg/s"),
            secondary_specific_heat_capacity=SpecificHeatCapacity(
                value=1_000.0,
                unit="J/(kg*K)",
            ),
            total_thermal_conductance=ThermalConductance(value=200.0, unit="W/K"),
            refrigerant_pressure_drop=PressureDifference(value=0.0, unit="Pa"),
            cell_count=80,
        ),
    )
    assert result.total_heat_to_refrigerant.value < 0.0
    assert result.phase_profile == ("supercritical",)
    assert result.relative_refrigerant_energy_residual <= 1.0e-12
    assert result.relative_secondary_energy_residual <= 1.0e-12
    assert result.relative_pressure_residual <= 1.0e-12
    return {
        "inlet_temperature_k": inlet.temperature.value,
        "outlet_temperature_k": result.refrigerant_outlet_state.temperature.value,
        "outlet_enthalpy_j_kg": result.refrigerant_outlet_state.enthalpy.value,
        "secondary_outlet_temperature_k": result.secondary_outlet_temperature.value,
        "heat_to_refrigerant_w": result.total_heat_to_refrigerant.value,
        "phase_profile": result.phase_profile,
        "refrigerant_energy_residual": result.relative_refrigerant_energy_residual,
        "secondary_energy_residual": result.relative_secondary_energy_residual,
        "pressure_residual": result.relative_pressure_residual,
    }


def main() -> None:
    print(
        json.dumps(
            {"analytical_co_current": _analytical_case(), "r744_gas_cooler": _r744_case()},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
