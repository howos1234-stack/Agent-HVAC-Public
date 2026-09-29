import math

import pytest
from CoolProp.CoolProp import PropsSI
from pydantic import ValidationError

from agent_hvac.components.pipe import (
    DynamicViscosity,
    LinearHeatTransferCoefficient,
    NonnegativeLength,
    Pipe1DInput,
    evaluate_pipe_1d,
)
from agent_hvac.physics.correlations import (
    SINGLE_PHASE_FRICTION_REGISTRY,
    HaalandDarcyFrictionFactor,
    LaminarDarcyFrictionFactor,
)
from agent_hvac.physics.state import ThermoState
from agent_hvac.properties.coolprop_backend import CoolPropBackend
from agent_hvac.utils.exceptions import ConvergenceError, InfeasibleDesignError
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
    """Analytical single-phase backend with constant density and heat capacity."""

    def __init__(
        self,
        *,
        density_kg_m3: float = 1_000.0,
        cp_j_kg_k: float = 1_000.0,
        reference_temperature_k: float = 300.0,
        reference_enthalpy_j_kg: float = 100_000.0,
        outlet_phase: str = "liquid",
    ) -> None:
        self.density_kg_m3 = density_kg_m3
        self.cp_j_kg_k = cp_j_kg_k
        self.reference_temperature_k = reference_temperature_k
        self.reference_enthalpy_j_kg = reference_enthalpy_j_kg
        self.outlet_phase = outlet_phase

    def _state(self, fluid: str, p: Pressure, temperature_k: float, enthalpy: float) -> ThermoState:
        return ThermoState(
            fluid=fluid,
            pressure=p,
            temperature=Temperature(value=temperature_k, unit="K"),
            enthalpy=SpecificEnthalpy(value=enthalpy, unit="J/kg"),
            density=Density(value=self.density_kg_m3, unit="kg/m^3"),
            phase=self.outlet_phase,
            entropy=SpecificEntropy(value=1_000.0, unit="J/(kg*K)"),
        )

    def state_ph(self, fluid: str, p: Pressure, h: SpecificEnthalpy) -> ThermoState:
        temperature_k = (
            self.reference_temperature_k + (h.value - self.reference_enthalpy_j_kg) / self.cp_j_kg_k
        )
        return self._state(fluid, p, temperature_k, h.value)

    def state_pt(self, fluid: str, p: Pressure, temperature: Temperature) -> ThermoState:
        enthalpy = self.reference_enthalpy_j_kg + self.cp_j_kg_k * (
            temperature.value - self.reference_temperature_k
        )
        return self._state(fluid, p, temperature.value, enthalpy)

    def state_ps(self, fluid: str, p: Pressure, entropy: SpecificEntropy) -> ThermoState:
        return self._state(
            fluid,
            p,
            self.reference_temperature_k,
            self.reference_enthalpy_j_kg,
        )


class BiasedStateBackend(ConstantCpBackend):
    """Test double that violates a requested P-h state's closure."""

    def __init__(self, *, enthalpy_bias_j_kg: float = 0.0, pressure_bias_pa: float = 0.0) -> None:
        super().__init__()
        self.enthalpy_bias_j_kg = enthalpy_bias_j_kg
        self.pressure_bias_pa = pressure_bias_pa

    def state_ph(self, fluid: str, p: Pressure, h: SpecificEnthalpy) -> ThermoState:
        biased_pressure = Pressure(value=p.value + self.pressure_bias_pa, unit="Pa")
        biased_enthalpy = h.value + self.enthalpy_bias_j_kg
        temperature_k = (
            self.reference_temperature_k
            + (biased_enthalpy - self.reference_enthalpy_j_kg) / self.cp_j_kg_k
        )
        return self._state(fluid, biased_pressure, temperature_k, biased_enthalpy)


def _mass_flow_for_reynolds(
    reynolds_number: float,
    diameter_m: float,
    viscosity_pa_s: float,
) -> float:
    return reynolds_number * math.pi * diameter_m * viscosity_pa_s / 4.0


def _pipe_input(
    backend: ConstantCpBackend,
    *,
    mass_flow_kg_s: float,
    length_m: float = 10.0,
    diameter_m: float = 0.02,
    roughness_m: float = 0.0,
    viscosity_pa_s: float = 0.001,
    ambient_temperature_k: float = 300.0,
    conductance_w_m_k: float = 0.0,
    cell_count: int = 10,
) -> Pipe1DInput:
    inlet = backend.state_pt(
        "synthetic-fluid",
        Pressure(value=1_000_000.0, unit="Pa"),
        Temperature(value=300.0, unit="K"),
    )
    return Pipe1DInput(
        inlet_state=inlet,
        mass_flow=MassFlow(value=mass_flow_kg_s, unit="kg/s"),
        length=NonnegativeLength(value=length_m, unit="m"),
        inner_diameter=Length(value=diameter_m, unit="m"),
        roughness=NonnegativeLength(value=roughness_m, unit="m"),
        dynamic_viscosity=DynamicViscosity(value=viscosity_pa_s, unit="Pa*s"),
        ambient_temperature=Temperature(value=ambient_temperature_k, unit="K"),
        linear_heat_transfer_coefficient=LinearHeatTransferCoefficient(
            value=conductance_w_m_k,
            unit="W/(m*K)",
        ),
        cell_count=cell_count,
    )


def test_correlation_registry_preserves_required_metadata() -> None:
    metadata = SINGLE_PHASE_FRICTION_REGISTRY.metadata

    assert {item.name for item in metadata} == {
        "laminar-fully-developed-circular-64-over-re",
        "haaland-1983-darcy-friction",
    }
    for item in metadata:
        assert item.equation
        assert item.reference
        assert item.applicability
        assert item.refrigerant_range
        assert item.geometry_range
        assert item.phase_range == frozenset({"single_phase"})
        assert item.validation_cases


def test_laminar_and_haaland_friction_values() -> None:
    laminar = LaminarDarcyFrictionFactor()
    turbulent = HaalandDarcyFrictionFactor()

    assert laminar.evaluate(1_000.0, 0.0) == pytest.approx(0.064, rel=1e-15)
    assert turbulent.evaluate(100_000.0, 0.0001) == pytest.approx(
        0.018265053014793857,
        rel=1e-12,
    )


@pytest.mark.parametrize("reynolds_number", [2300.0, 3000.0, 3999.999])
def test_transition_reynolds_range_is_not_silently_interpolated(
    reynolds_number: float,
) -> None:
    with pytest.raises(InfeasibleDesignError, match="no registered"):
        SINGLE_PHASE_FRICTION_REGISTRY.select_darcy_friction(
            reynolds_number=reynolds_number,
            relative_roughness=0.0,
            phase_regime="single_phase",
        )


def test_two_phase_and_haaland_outside_range_are_rejected() -> None:
    with pytest.raises(InfeasibleDesignError, match="phase_regime='two_phase'"):
        SINGLE_PHASE_FRICTION_REGISTRY.select_darcy_friction(
            reynolds_number=10_000.0,
            relative_roughness=0.0,
            phase_regime="two_phase",
        )
    with pytest.raises(InfeasibleDesignError, match="no registered"):
        SINGLE_PHASE_FRICTION_REGISTRY.select_darcy_friction(
            reynolds_number=1.0e8 + 1.0,
            relative_roughness=0.0,
            phase_regime="single_phase",
        )
    with pytest.raises(InfeasibleDesignError, match="no registered"):
        SINGLE_PHASE_FRICTION_REGISTRY.select_darcy_friction(
            reynolds_number=10_000.0,
            relative_roughness=0.050001,
            phase_regime="single_phase",
        )


def test_zero_length_limit_preserves_state_and_has_no_losses() -> None:
    backend = ConstantCpBackend()
    inputs = _pipe_input(
        backend,
        mass_flow_kg_s=_mass_flow_for_reynolds(3_000.0, 0.02, 0.001),
        length_m=0.0,
    )

    result = evaluate_pipe_1d(backend, inputs)

    assert result.outlet_state == inputs.inlet_state
    assert result.cells == ()
    assert result.total_pressure_drop.value == pytest.approx(0.0, abs=1e-12)
    assert result.total_heat_transfer.value == pytest.approx(0.0, abs=1e-12)
    assert result.relative_mass_residual == pytest.approx(0.0, abs=1e-12)
    assert result.relative_energy_residual == pytest.approx(0.0, abs=1e-12)
    assert result.relative_pressure_residual == pytest.approx(0.0, abs=1e-12)


def test_constant_density_laminar_pressure_drop_matches_darcy_weisbach() -> None:
    backend = ConstantCpBackend(density_kg_m3=1_000.0)
    diameter_m = 0.02
    viscosity_pa_s = 0.001
    mass_flow_kg_s = _mass_flow_for_reynolds(1_000.0, diameter_m, viscosity_pa_s)
    inputs = _pipe_input(
        backend,
        mass_flow_kg_s=mass_flow_kg_s,
        diameter_m=diameter_m,
        viscosity_pa_s=viscosity_pa_s,
        cell_count=25,
    )

    result = evaluate_pipe_1d(backend, inputs)

    area_m2 = math.pi * diameter_m**2 / 4.0
    velocity_m_s = mass_flow_kg_s / (1_000.0 * area_m2)
    expected_pa = 0.064 * (inputs.length.value / diameter_m) * 1_000.0 * velocity_m_s**2 / 2.0
    assert result.total_pressure_drop.value == pytest.approx(expected_pa, rel=1e-10)
    assert result.outlet_state.enthalpy == inputs.inlet_state.enthalpy
    assert result.total_heat_transfer.value == pytest.approx(0.0, abs=1e-12)
    assert result.relative_mass_residual <= 1e-12
    assert result.relative_energy_residual <= 1e-12
    assert result.relative_pressure_residual <= 1e-12
    assert all(cell.mass_flow == inputs.mass_flow for cell in result.cells)
    assert {cell.friction_correlation for cell in result.cells} == {
        "laminar-fully-developed-circular-64-over-re"
    }


def test_heat_leak_grid_converges_to_constant_cp_analytical_solution() -> None:
    cp_j_kg_k = 1_000.0
    backend = ConstantCpBackend(cp_j_kg_k=cp_j_kg_k)
    mass_flow_kg_s = 1.0
    length_m = 5.0
    conductance_w_m_k = 100.0
    ambient_temperature_k = 400.0
    exact_outlet_k = ambient_temperature_k - (ambient_temperature_k - 300.0) * math.exp(
        -conductance_w_m_k * length_m / (mass_flow_kg_s * cp_j_kg_k)
    )

    errors: list[float] = []
    for cell_count in (10, 20, 40, 80):
        result = evaluate_pipe_1d(
            backend,
            _pipe_input(
                backend,
                mass_flow_kg_s=mass_flow_kg_s,
                length_m=length_m,
                diameter_m=0.1,
                ambient_temperature_k=ambient_temperature_k,
                conductance_w_m_k=conductance_w_m_k,
                cell_count=cell_count,
            ),
        )
        errors.append(abs(result.outlet_state.temperature.value - exact_outlet_k))
        assert result.relative_mass_residual <= 1e-12
        assert result.relative_energy_residual <= 1e-12
        assert result.relative_pressure_residual <= 1e-12
        assert all(
            cell.outlet_state.pressure.value < cell.inlet_state.pressure.value
            for cell in result.cells
        )

    assert errors == sorted(errors, reverse=True)
    for coarse_error, fine_error in zip(errors[:-1], errors[1:], strict=True):
        assert coarse_error / fine_error == pytest.approx(2.0, rel=0.1)
    assert errors[-1] / exact_outlet_k <= 5e-4


@pytest.mark.parametrize("ambient_temperature_k", [200.0, 400.0])
def test_coarse_heat_transfer_cell_rejects_ambient_temperature_overshoot(
    ambient_temperature_k: float,
) -> None:
    backend = ConstantCpBackend(cp_j_kg_k=1_000.0)
    inputs = _pipe_input(
        backend,
        mass_flow_kg_s=1.0,
        length_m=1.0,
        diameter_m=0.1,
        ambient_temperature_k=ambient_temperature_k,
        conductance_w_m_k=2_000.0,
        cell_count=1,
    )

    with pytest.raises(ConvergenceError, match="crossed the ambient temperature"):
        evaluate_pipe_1d(backend, inputs)


def test_two_phase_inlet_and_phase_crossing_are_explicitly_rejected() -> None:
    two_phase_backend = ConstantCpBackend(outlet_phase="twophase")
    two_phase_inlet = two_phase_backend.state_pt(
        "synthetic-fluid",
        Pressure(value=1_000_000.0, unit="Pa"),
        Temperature(value=300.0, unit="K"),
    )
    two_phase_data = two_phase_inlet.model_dump()
    two_phase_data["vapor_quality"] = 0.5
    two_phase_inlet = ThermoState.model_validate(two_phase_data)
    inputs = _pipe_input(two_phase_backend, mass_flow_kg_s=0.1)
    inputs = Pipe1DInput.model_validate({**inputs.model_dump(), "inlet_state": two_phase_inlet})

    with pytest.raises(InfeasibleDesignError, match="two-phase pipe correlations"):
        evaluate_pipe_1d(two_phase_backend, inputs)

    crossing_backend = ConstantCpBackend(outlet_phase="twophase")
    crossing_inputs = _pipe_input(crossing_backend, mass_flow_kg_s=0.1)
    crossing_data = crossing_inputs.inlet_state.model_dump()
    crossing_data["phase"] = "liquid"
    crossing_inputs = Pipe1DInput.model_validate(
        {**crossing_inputs.model_dump(), "inlet_state": crossing_data}
    )
    with pytest.raises(InfeasibleDesignError, match="two-phase pipe correlations"):
        evaluate_pipe_1d(crossing_backend, crossing_inputs)


def test_nonphysical_inputs_and_excessive_pressure_drop_are_rejected() -> None:
    backend = ConstantCpBackend()
    base = _pipe_input(backend, mass_flow_kg_s=0.1)

    with pytest.raises(ValidationError, match="length must be nonnegative"):
        NonnegativeLength(value=-1.0, unit="m")
    with pytest.raises(ValidationError, match="strictly positive"):
        DynamicViscosity(value=0.0, unit="Pa*s")
    with pytest.raises(ValidationError, match="heat-transfer coefficient"):
        LinearHeatTransferCoefficient(value=-1.0, unit="W/(m*K)")
    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        Pipe1DInput.model_validate({**base.model_dump(), "cell_count": 0})

    excessive = _pipe_input(
        backend,
        mass_flow_kg_s=_mass_flow_for_reynolds(1.0e8, 0.001, 1.0e-6),
        length_m=10_000.0,
        diameter_m=0.001,
        viscosity_pa_s=1.0e-6,
        cell_count=1,
    )
    with pytest.raises(ConvergenceError, match="nonpositive or nonfinite pressure"):
        evaluate_pipe_1d(backend, excessive)

    underflow_area = _pipe_input(
        backend,
        mass_flow_kg_s=0.1,
        diameter_m=1.0e-300,
    )
    with pytest.raises(InfeasibleDesignError, match="cross-sectional area"):
        evaluate_pipe_1d(backend, underflow_area)


def test_extremely_large_finite_diameter_is_reported_as_infeasible() -> None:
    backend = ConstantCpBackend()
    overflow_area = _pipe_input(
        backend,
        mass_flow_kg_s=0.1,
        diameter_m=1.0e200,
    )
    with pytest.raises(InfeasibleDesignError, match="cross-sectional area overflowed"):
        evaluate_pipe_1d(backend, overflow_area)


def test_energy_closure_above_existing_limit_is_rejected() -> None:
    backend = BiasedStateBackend(enthalpy_bias_j_kg=1.0)
    inputs = _pipe_input(backend, mass_flow_kg_s=0.1, length_m=1.0, cell_count=1)

    with pytest.raises(ConvergenceError, match="energy closure residual"):
        evaluate_pipe_1d(backend, inputs)


def test_pressure_closure_above_existing_limit_is_rejected() -> None:
    backend = BiasedStateBackend(pressure_bias_pa=1.0)
    inputs = _pipe_input(backend, mass_flow_kg_s=0.1, length_m=1.0, cell_count=1)

    with pytest.raises(ConvergenceError, match="pressure closure residual"):
        evaluate_pipe_1d(backend, inputs)


def _r744_pipe_input(
    backend: CoolPropBackend,
    *,
    ambient_temperature_k: float,
    conductance_w_m_k: float,
) -> Pipe1DInput:
    inlet = backend.state_pt(
        "R744",
        Pressure(value=3_000_000.0, unit="Pa"),
        Temperature(value=280.0, unit="K"),
    )
    viscosity_pa_s = float(PropsSI("VISCOSITY", "P", 3_000_000.0, "T", 280.0, "R744"))
    return Pipe1DInput(
        inlet_state=inlet,
        mass_flow=MassFlow(value=0.01, unit="kg/s"),
        length=NonnegativeLength(value=0.5, unit="m"),
        inner_diameter=Length(value=0.01, unit="m"),
        roughness=NonnegativeLength(value=1.0e-6, unit="m"),
        dynamic_viscosity=DynamicViscosity(value=viscosity_pa_s, unit="Pa*s"),
        ambient_temperature=Temperature(value=ambient_temperature_k, unit="K"),
        linear_heat_transfer_coefficient=LinearHeatTransferCoefficient(
            value=conductance_w_m_k,
            unit="W/(m*K)",
        ),
        cell_count=20,
    )


def test_r744_half_meter_adiabatic_pipe_is_deterministic_and_single_phase() -> None:
    backend = CoolPropBackend()
    inputs = _r744_pipe_input(
        backend,
        ambient_temperature_k=280.0,
        conductance_w_m_k=0.0,
    )
    inlet = inputs.inlet_state

    first = evaluate_pipe_1d(backend, inputs)
    second = evaluate_pipe_1d(backend, inputs)

    assert first == second
    assert first.total_pressure_drop.value > 0.0
    assert first.total_heat_transfer.value == pytest.approx(0.0, abs=1e-12)
    assert first.outlet_state.enthalpy.value == pytest.approx(
        inlet.enthalpy.value,
        rel=1e-12,
    )
    assert first.relative_mass_residual <= 1e-12
    assert first.relative_energy_residual <= 1e-12
    assert first.relative_pressure_residual <= 1e-12
    assert first.correlation_names == ("haaland-1983-darcy-friction",)
    assert all(cell.outlet_state.phase == "gas" for cell in first.cells)
    assert all(
        cell.outlet_state.pressure.value < cell.inlet_state.pressure.value for cell in first.cells
    )


def test_r744_adiabatic_result_is_independent_of_ambient_temperature() -> None:
    backend = CoolPropBackend()
    at_inlet_temperature = evaluate_pipe_1d(
        backend,
        _r744_pipe_input(
            backend,
            ambient_temperature_k=280.0,
            conductance_w_m_k=0.0,
        ),
    )
    just_below_inlet_temperature = evaluate_pipe_1d(
        backend,
        _r744_pipe_input(
            backend,
            ambient_temperature_k=279.999,
            conductance_w_m_k=0.0,
        ),
    )

    assert just_below_inlet_temperature == at_inlet_temperature


def test_r744_nonadiabatic_pressure_drop_does_not_trigger_false_overshoot() -> None:
    backend = CoolPropBackend()
    ambient_temperature_k = 279.999
    result = evaluate_pipe_1d(
        backend,
        _r744_pipe_input(
            backend,
            ambient_temperature_k=ambient_temperature_k,
            conductance_w_m_k=0.01,
        ),
    )

    assert result.total_pressure_drop.value > 0.0
    assert result.total_heat_transfer.value != pytest.approx(0.0, abs=1e-12)
    assert any(
        (cell.inlet_state.temperature.value - ambient_temperature_k)
        * (cell.outlet_state.temperature.value - ambient_temperature_k)
        < 0.0
        for cell in result.cells
    )
    assert result.relative_energy_residual <= 1e-12
    assert result.relative_pressure_residual <= 1e-12
