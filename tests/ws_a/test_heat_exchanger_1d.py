import math

import pytest
from pydantic import ValidationError

from agent_hvac.components.heat_exchanger_1d import (
    HeatExchanger1DInput,
    HeatExchangerMode,
    SpecificHeatCapacity,
    ThermalConductance,
    evaluate_heat_exchanger_1d,
)
from agent_hvac.physics.state import ThermoState
from agent_hvac.properties.coolprop_backend import CoolPropBackend
from agent_hvac.utils.exceptions import ConvergenceError, InfeasibleDesignError
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
    def __init__(
        self,
        *,
        cp_j_kg_k: float = 1_000.0,
        density_kg_m3: float = 10.0,
        phase: str = "liquid",
    ) -> None:
        self.cp_j_kg_k = cp_j_kg_k
        self.density_kg_m3 = density_kg_m3
        self.phase = phase

    def _state(self, fluid: str, pressure: Pressure, enthalpy_j_kg: float) -> ThermoState:
        return ThermoState(
            fluid=fluid,
            pressure=pressure,
            temperature=Temperature(value=enthalpy_j_kg / self.cp_j_kg_k, unit="K"),
            enthalpy=SpecificEnthalpy(value=enthalpy_j_kg, unit="J/kg"),
            density=Density(value=self.density_kg_m3, unit="kg/m^3"),
            phase=self.phase,
            entropy=SpecificEntropy(value=1_000.0, unit="J/(kg*K)"),
        )

    def state_ph(self, fluid: str, p: Pressure, h: SpecificEnthalpy) -> ThermoState:
        return self._state(fluid, p, h.value)

    def state_pt(self, fluid: str, p: Pressure, temperature: Temperature) -> ThermoState:
        return self._state(fluid, p, self.cp_j_kg_k * temperature.value)

    def state_ps(self, fluid: str, p: Pressure, entropy: SpecificEntropy) -> ThermoState:
        return self._state(fluid, p, 300_000.0)


class PhaseAwareBackend(ConstantCpBackend):
    """Synthetic pure-fluid path with liquid, two-phase and vapor enthalpy zones."""

    def _state(self, fluid: str, pressure: Pressure, enthalpy_j_kg: float) -> ThermoState:
        quality: float | None = None
        if enthalpy_j_kg < 200_000.0:
            phase = "liquid"
            temperature_k = 300.0 + (enthalpy_j_kg - 200_000.0) / 1_000.0
        elif enthalpy_j_kg <= 270_000.0:
            phase = "twophase"
            temperature_k = 300.0
            quality = (enthalpy_j_kg - 200_000.0) / 70_000.0
        else:
            phase = "gas"
            temperature_k = 300.0 + (enthalpy_j_kg - 270_000.0) / 1_000.0
        return ThermoState(
            fluid=fluid,
            pressure=pressure,
            temperature=Temperature(value=temperature_k, unit="K"),
            enthalpy=SpecificEnthalpy(value=enthalpy_j_kg, unit="J/kg"),
            density=Density(value=10.0, unit="kg/m^3"),
            phase=phase,
            vapor_quality=quality,
            entropy=SpecificEntropy(value=1_000.0, unit="J/(kg*K)"),
        )


class PressureSensitiveBackend(ConstantCpBackend):
    """Synthetic backend that isolates pressure-driven temperature change."""

    def _state(self, fluid: str, pressure: Pressure, enthalpy_j_kg: float) -> ThermoState:
        pressure_temperature_shift_k = (1_000_000.0 - pressure.value) / 100_000.0
        return ThermoState(
            fluid=fluid,
            pressure=pressure,
            temperature=Temperature(
                value=enthalpy_j_kg / self.cp_j_kg_k + pressure_temperature_shift_k,
                unit="K",
            ),
            enthalpy=SpecificEnthalpy(value=enthalpy_j_kg, unit="J/kg"),
            density=Density(value=self.density_kg_m3, unit="kg/m^3"),
            phase=self.phase,
            entropy=SpecificEntropy(value=1_000.0, unit="J/(kg*K)"),
        )


class BiasedBackend(ConstantCpBackend):
    def __init__(self, *, pressure_bias_pa: float = 0.0, enthalpy_bias_j_kg: float = 0.0) -> None:
        super().__init__()
        self.pressure_bias_pa = pressure_bias_pa
        self.enthalpy_bias_j_kg = enthalpy_bias_j_kg

    def state_ph(self, fluid: str, p: Pressure, h: SpecificEnthalpy) -> ThermoState:
        return self._state(
            fluid,
            Pressure(value=p.value + self.pressure_bias_pa, unit="Pa"),
            h.value + self.enthalpy_bias_j_kg,
        )


def _input(
    backend: ConstantCpBackend,
    *,
    mode: HeatExchangerMode = HeatExchangerMode.EVAPORATOR,
    refrigerant_inlet_temperature_k: float = 300.0,
    secondary_inlet_temperature_k: float = 400.0,
    refrigerant_mass_flow_kg_s: float = 1.0,
    secondary_mass_flow_kg_s: float = 2.0,
    secondary_cp_j_kg_k: float = 1_000.0,
    conductance_w_k: float = 500.0,
    pressure_drop_pa: float = 1_000.0,
    cell_count: int = 20,
) -> HeatExchanger1DInput:
    inlet = backend.state_pt(
        "synthetic-fluid",
        Pressure(value=1_000_000.0, unit="Pa"),
        Temperature(value=refrigerant_inlet_temperature_k, unit="K"),
    )
    return HeatExchanger1DInput(
        mode=mode,
        refrigerant_inlet_state=inlet,
        refrigerant_mass_flow=MassFlow(value=refrigerant_mass_flow_kg_s, unit="kg/s"),
        secondary_inlet_temperature=Temperature(
            value=secondary_inlet_temperature_k,
            unit="K",
        ),
        secondary_mass_flow=MassFlow(value=secondary_mass_flow_kg_s, unit="kg/s"),
        secondary_specific_heat_capacity=SpecificHeatCapacity(
            value=secondary_cp_j_kg_k,
            unit="J/(kg*K)",
        ),
        total_thermal_conductance=ThermalConductance(value=conductance_w_k, unit="W/K"),
        refrigerant_pressure_drop=PressureDifference(value=pressure_drop_pa, unit="Pa"),
        cell_count=cell_count,
    )


def test_zero_ua_and_zero_pressure_drop_preserve_both_streams() -> None:
    backend = ConstantCpBackend()
    inputs = _input(backend, conductance_w_k=0.0, pressure_drop_pa=0.0, cell_count=5)

    result = evaluate_heat_exchanger_1d(backend, inputs)

    assert result.refrigerant_outlet_state == inputs.refrigerant_inlet_state
    assert result.secondary_outlet_temperature == inputs.secondary_inlet_temperature
    assert result.total_heat_to_refrigerant.value == pytest.approx(0.0, abs=1e-12)
    assert result.total_refrigerant_pressure_drop.value == pytest.approx(0.0, abs=1e-12)
    assert result.relative_refrigerant_energy_residual <= 1e-12
    assert result.relative_secondary_energy_residual <= 1e-12
    assert result.relative_pressure_residual <= 1e-12
    assert result.phase_profile == ("liquid",)


@pytest.mark.parametrize("secondary_inlet_temperature_k", [300.5, 301.0, 301.5])
def test_zero_ua_pressure_temperature_change_is_not_thermal_overshoot(
    secondary_inlet_temperature_k: float,
) -> None:
    backend = PressureSensitiveBackend()
    inputs = _input(
        backend,
        secondary_inlet_temperature_k=secondary_inlet_temperature_k,
        conductance_w_k=0.0,
        pressure_drop_pa=100_000.0,
        cell_count=1,
    )

    result = evaluate_heat_exchanger_1d(backend, inputs)

    assert result.total_heat_to_refrigerant.value == pytest.approx(0.0, abs=1e-12)
    assert result.refrigerant_outlet_state.temperature.value == pytest.approx(301.0)
    assert result.secondary_outlet_temperature.value == pytest.approx(secondary_inlet_temperature_k)
    assert result.relative_refrigerant_energy_residual <= 1e-12
    assert result.relative_secondary_energy_residual <= 1e-12
    assert result.relative_pressure_residual <= 1e-12


@pytest.mark.parametrize("secondary_inlet_temperature_k", [300.5, 301.0, 301.5])
def test_pressure_change_cannot_hide_heating_thermal_overshoot(
    secondary_inlet_temperature_k: float,
) -> None:
    backend = PressureSensitiveBackend()
    inputs = _input(
        backend,
        secondary_inlet_temperature_k=secondary_inlet_temperature_k,
        conductance_w_k=100_000.0,
        pressure_drop_pa=100_000.0,
        cell_count=1,
    )

    with pytest.raises(ConvergenceError, match="crossed the local stream temperatures"):
        evaluate_heat_exchanger_1d(backend, inputs)


def test_pressure_change_cannot_hide_cooling_thermal_overshoot() -> None:
    backend = PressureSensitiveBackend(phase="gas")
    inputs = _input(
        backend,
        mode=HeatExchangerMode.CONDENSER,
        secondary_inlet_temperature_k=299.5,
        conductance_w_k=100_000.0,
        pressure_drop_pa=100_000.0,
        cell_count=1,
    )

    with pytest.raises(ConvergenceError, match="crossed the local stream temperatures"):
        evaluate_heat_exchanger_1d(backend, inputs)


def test_subdivided_nonadiabatic_pressure_sensitive_case_succeeds() -> None:
    backend = PressureSensitiveBackend()
    inputs = _input(
        backend,
        secondary_inlet_temperature_k=400.0,
        conductance_w_k=500.0,
        pressure_drop_pa=100_000.0,
        cell_count=20,
    )

    result = evaluate_heat_exchanger_1d(backend, inputs)

    assert result.total_heat_to_refrigerant.value > 0.0
    assert result.refrigerant_outlet_state.temperature.value > 300.0
    assert result.secondary_outlet_temperature.value < 400.0
    assert result.relative_refrigerant_energy_residual <= 1e-12
    assert result.relative_secondary_energy_residual <= 1e-12
    assert result.relative_pressure_residual <= 1e-12


def test_constant_cp_co_current_grid_converges_to_analytical_solution() -> None:
    backend = ConstantCpBackend(cp_j_kg_k=1_000.0)
    refrigerant_capacity_rate_w_k = 1_000.0
    secondary_capacity_rate_w_k = 2_000.0
    conductance_w_k = 500.0
    inlet_difference_k = 100.0
    exact_heat_w = (
        inlet_difference_k
        * (
            1.0
            - math.exp(
                -conductance_w_k
                * (1.0 / refrigerant_capacity_rate_w_k + 1.0 / secondary_capacity_rate_w_k)
            )
        )
        / (1.0 / refrigerant_capacity_rate_w_k + 1.0 / secondary_capacity_rate_w_k)
    )
    exact_refrigerant_outlet_k = 300.0 + exact_heat_w / refrigerant_capacity_rate_w_k

    errors: list[float] = []
    for cell_count in (10, 20, 40, 80):
        result = evaluate_heat_exchanger_1d(
            backend,
            _input(backend, cell_count=cell_count, pressure_drop_pa=0.0),
        )
        errors.append(
            abs(result.refrigerant_outlet_state.temperature.value - exact_refrigerant_outlet_k)
        )
        assert result.relative_refrigerant_energy_residual <= 1e-12
        assert result.relative_secondary_energy_residual <= 1e-12
        assert result.relative_pressure_residual <= 1e-12

    assert errors == sorted(errors, reverse=True)
    for coarse_error, fine_error in zip(errors[:-1], errors[1:], strict=True):
        assert coarse_error / fine_error == pytest.approx(2.0, rel=0.1)
    assert errors[-1] / exact_refrigerant_outlet_k <= 5e-4


def test_evaporator_preserves_two_phase_to_vapor_profile() -> None:
    backend = PhaseAwareBackend()
    inlet = backend.state_ph(
        "synthetic-fluid",
        Pressure(value=1_000_000.0, unit="Pa"),
        SpecificEnthalpy(value=250_000.0, unit="J/kg"),
    )
    base = _input(
        backend,
        refrigerant_mass_flow_kg_s=0.1,
        secondary_mass_flow_kg_s=1.0,
        secondary_inlet_temperature_k=330.0,
        conductance_w_k=1_000.0,
        pressure_drop_pa=0.0,
        cell_count=100,
    )
    inputs = HeatExchanger1DInput.model_validate(
        {**base.model_dump(), "refrigerant_inlet_state": inlet}
    )

    result = evaluate_heat_exchanger_1d(backend, inputs)

    assert result.total_heat_to_refrigerant.value > 0.0
    assert result.phase_profile == ("twophase", "gas")
    assert result.refrigerant_outlet_state.phase == "gas"
    assert result.refrigerant_outlet_state.vapor_quality is None
    assert all(
        cell.refrigerant_outlet_state.enthalpy.value >= cell.refrigerant_inlet_state.enthalpy.value
        for cell in result.cells
    )


def test_condenser_cools_a_subcritical_vapor() -> None:
    backend = ConstantCpBackend(phase="gas")
    inputs = _input(
        backend,
        mode=HeatExchangerMode.CONDENSER,
        refrigerant_inlet_temperature_k=400.0,
        secondary_inlet_temperature_k=300.0,
        conductance_w_k=200.0,
    )

    result = evaluate_heat_exchanger_1d(backend, inputs)

    assert result.total_heat_to_refrigerant.value < 0.0
    assert result.refrigerant_outlet_state.temperature.value < 400.0
    assert result.secondary_outlet_temperature.value > 300.0


def test_wrong_driving_direction_and_wrong_mode_phase_are_rejected() -> None:
    liquid = ConstantCpBackend(phase="liquid")
    with pytest.raises(InfeasibleDesignError, match="hotter than the refrigerant"):
        evaluate_heat_exchanger_1d(
            liquid,
            _input(liquid, secondary_inlet_temperature_k=299.0),
        )
    with pytest.raises(InfeasibleDesignError, match="high-pressure region"):
        evaluate_heat_exchanger_1d(
            liquid,
            _input(
                liquid,
                mode=HeatExchangerMode.GAS_COOLER,
                refrigerant_inlet_temperature_k=400.0,
                secondary_inlet_temperature_k=300.0,
            ),
        )

    supercritical = ConstantCpBackend(phase="supercritical")
    with pytest.raises(InfeasibleDesignError, match="cannot be treated as condenser"):
        evaluate_heat_exchanger_1d(
            supercritical,
            _input(
                supercritical,
                mode=HeatExchangerMode.CONDENSER,
                refrigerant_inlet_temperature_k=400.0,
                secondary_inlet_temperature_k=300.0,
            ),
        )

    critical_point = ConstantCpBackend(phase="critical_point")
    with pytest.raises(InfeasibleDesignError, match="critical_point"):
        evaluate_heat_exchanger_1d(
            critical_point,
            _input(critical_point),
        )


def test_phase_and_quality_must_be_consistent() -> None:
    backend = ConstantCpBackend(phase="gas")
    base = _input(backend)
    gas_with_quality = ThermoState.model_validate(
        {**base.refrigerant_inlet_state.model_dump(), "vapor_quality": 0.5}
    )
    with pytest.raises(InfeasibleDesignError, match="outside a two-phase state"):
        evaluate_heat_exchanger_1d(
            backend,
            HeatExchanger1DInput.model_validate(
                {**base.model_dump(), "refrigerant_inlet_state": gas_with_quality}
            ),
        )

    two_phase_without_quality = ThermoState.model_validate(
        {**base.refrigerant_inlet_state.model_dump(), "phase": "twophase"}
    )
    with pytest.raises(InfeasibleDesignError, match="without vapor quality"):
        evaluate_heat_exchanger_1d(
            backend,
            HeatExchanger1DInput.model_validate(
                {**base.model_dump(), "refrigerant_inlet_state": two_phase_without_quality}
            ),
        )


def test_coarse_cell_temperature_crossing_is_not_clamped() -> None:
    backend = ConstantCpBackend()
    inputs = _input(
        backend,
        conductance_w_k=1_000.0,
        pressure_drop_pa=0.0,
        cell_count=1,
    )

    with pytest.raises(ConvergenceError, match="crossed the local stream temperatures"):
        evaluate_heat_exchanger_1d(backend, inputs)


def test_coarse_condenser_cell_temperature_crossing_is_not_clamped() -> None:
    backend = ConstantCpBackend(phase="gas")
    inputs = _input(
        backend,
        mode=HeatExchangerMode.CONDENSER,
        refrigerant_inlet_temperature_k=400.0,
        secondary_inlet_temperature_k=300.0,
        conductance_w_k=1_000.0,
        pressure_drop_pa=0.0,
        cell_count=1,
    )

    with pytest.raises(ConvergenceError, match="crossed the local stream temperatures"):
        evaluate_heat_exchanger_1d(backend, inputs)


def test_invalid_inputs_pressure_and_backend_closure_are_rejected() -> None:
    backend = ConstantCpBackend()
    with pytest.raises(ValidationError, match="thermal conductance"):
        ThermalConductance(value=-1.0, unit="W/K")
    with pytest.raises(ValidationError, match="strictly positive"):
        SpecificHeatCapacity(value=0.0, unit="J/(kg*K)")

    excessive_drop = _input(backend, pressure_drop_pa=1_000_000.0, cell_count=1)
    with pytest.raises(ConvergenceError, match="nonpositive pressure"):
        evaluate_heat_exchanger_1d(backend, excessive_drop)

    with pytest.raises(ConvergenceError, match="property pressure closure"):
        evaluate_heat_exchanger_1d(
            BiasedBackend(pressure_bias_pa=1.0),
            _input(BiasedBackend(pressure_bias_pa=1.0), cell_count=1),
        )
    with pytest.raises(ConvergenceError, match="property enthalpy closure"):
        evaluate_heat_exchanger_1d(
            BiasedBackend(enthalpy_bias_j_kg=1.0),
            _input(BiasedBackend(enthalpy_bias_j_kg=1.0), cell_count=1),
        )


def test_r744_gas_cooler_is_deterministic_supercritical_and_conservative() -> None:
    backend = CoolPropBackend()
    inlet = backend.state_pt(
        "R744",
        Pressure(value=9_000_000.0, unit="Pa"),
        Temperature(value=375.6681128305702, unit="K"),
    )
    inputs = HeatExchanger1DInput(
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
    )

    first = evaluate_heat_exchanger_1d(backend, inputs)
    second = evaluate_heat_exchanger_1d(backend, inputs)

    assert first == second
    assert first.total_heat_to_refrigerant.value < 0.0
    assert first.refrigerant_outlet_state.temperature.value < inlet.temperature.value
    assert first.secondary_outlet_temperature.value > inputs.secondary_inlet_temperature.value
    assert first.phase_profile == ("supercritical",)
    assert all(
        cell.refrigerant_outlet_state.temperature.value
        < cell.refrigerant_inlet_state.temperature.value
        for cell in first.cells
    )
    assert first.relative_refrigerant_energy_residual <= 1e-12
    assert first.relative_secondary_energy_residual <= 1e-12
    assert first.relative_pressure_residual <= 1e-12


def test_r744_subcritical_superheated_vapor_is_condenser_not_gas_cooler() -> None:
    backend = CoolPropBackend()
    inlet = backend.state_pt(
        "R744",
        Pressure(value=3_000_000.0, unit="Pa"),
        Temperature(value=350.0, unit="K"),
    )
    base = HeatExchanger1DInput(
        mode=HeatExchangerMode.CONDENSER,
        refrigerant_inlet_state=inlet,
        refrigerant_mass_flow=MassFlow(value=0.1, unit="kg/s"),
        secondary_inlet_temperature=Temperature(value=300.0, unit="K"),
        secondary_mass_flow=MassFlow(value=1.0, unit="kg/s"),
        secondary_specific_heat_capacity=SpecificHeatCapacity(
            value=1_000.0,
            unit="J/(kg*K)",
        ),
        total_thermal_conductance=ThermalConductance(value=50.0, unit="W/K"),
        refrigerant_pressure_drop=PressureDifference(value=0.0, unit="Pa"),
        cell_count=20,
    )

    result = evaluate_heat_exchanger_1d(backend, base)

    assert inlet.phase == "supercritical_gas"
    assert result.total_heat_to_refrigerant.value < 0.0
    with pytest.raises(InfeasibleDesignError, match="high-pressure region"):
        evaluate_heat_exchanger_1d(
            backend,
            HeatExchanger1DInput.model_validate(
                {**base.model_dump(), "mode": HeatExchangerMode.GAS_COOLER}
            ),
        )


@pytest.mark.parametrize(
    ("inlet_temperature_k", "expected_phase"),
    [(350.0, "supercritical"), (300.0, "supercritical_liquid")],
)
def test_r744_high_pressure_gas_cooler_accepts_both_sides_of_critical_temperature(
    inlet_temperature_k: float,
    expected_phase: str,
) -> None:
    backend = CoolPropBackend()
    inlet = backend.state_pt(
        "R744",
        Pressure(value=9_000_000.0, unit="Pa"),
        Temperature(value=inlet_temperature_k, unit="K"),
    )
    inputs = HeatExchanger1DInput(
        mode=HeatExchangerMode.GAS_COOLER,
        refrigerant_inlet_state=inlet,
        refrigerant_mass_flow=MassFlow(value=0.1, unit="kg/s"),
        secondary_inlet_temperature=Temperature(value=290.0, unit="K"),
        secondary_mass_flow=MassFlow(value=1.0, unit="kg/s"),
        secondary_specific_heat_capacity=SpecificHeatCapacity(
            value=1_000.0,
            unit="J/(kg*K)",
        ),
        total_thermal_conductance=ThermalConductance(value=100.0, unit="W/K"),
        refrigerant_pressure_drop=PressureDifference(value=0.0, unit="Pa"),
        cell_count=20,
    )

    result = evaluate_heat_exchanger_1d(backend, inputs)

    assert inlet.phase == expected_phase
    assert result.total_heat_to_refrigerant.value < 0.0


def test_r744_gas_cooler_rejects_pressure_drop_out_of_high_pressure_region() -> None:
    backend = CoolPropBackend()
    inlet = backend.state_pt(
        "R744",
        Pressure(value=8_000_000.0, unit="Pa"),
        Temperature(value=350.0, unit="K"),
    )
    inputs = HeatExchanger1DInput(
        mode=HeatExchangerMode.GAS_COOLER,
        refrigerant_inlet_state=inlet,
        refrigerant_mass_flow=MassFlow(value=0.1, unit="kg/s"),
        secondary_inlet_temperature=Temperature(value=300.0, unit="K"),
        secondary_mass_flow=MassFlow(value=1.0, unit="kg/s"),
        secondary_specific_heat_capacity=SpecificHeatCapacity(
            value=1_000.0,
            unit="J/(kg*K)",
        ),
        total_thermal_conductance=ThermalConductance(value=0.0, unit="W/K"),
        refrigerant_pressure_drop=PressureDifference(value=1_000_000.0, unit="Pa"),
        cell_count=1,
    )

    with pytest.raises(InfeasibleDesignError, match="high-pressure region"):
        evaluate_heat_exchanger_1d(backend, inputs)


def test_r744_condenser_tracks_gas_two_phase_liquid_path() -> None:
    backend = CoolPropBackend()
    inlet = backend.state_pt(
        "R744",
        Pressure(value=3_000_000.0, unit="Pa"),
        Temperature(value=280.0, unit="K"),
    )
    inputs = HeatExchanger1DInput(
        mode=HeatExchangerMode.CONDENSER,
        refrigerant_inlet_state=inlet,
        refrigerant_mass_flow=MassFlow(value=0.1, unit="kg/s"),
        secondary_inlet_temperature=Temperature(value=220.0, unit="K"),
        secondary_mass_flow=MassFlow(value=2.0, unit="kg/s"),
        secondary_specific_heat_capacity=SpecificHeatCapacity(
            value=1_000.0,
            unit="J/(kg*K)",
        ),
        total_thermal_conductance=ThermalConductance(value=1_000.0, unit="W/K"),
        refrigerant_pressure_drop=PressureDifference(value=0.0, unit="Pa"),
        cell_count=200,
    )

    result = evaluate_heat_exchanger_1d(backend, inputs)

    assert result.phase_profile == ("gas", "twophase", "liquid")
    assert result.refrigerant_outlet_state.phase == "liquid"
