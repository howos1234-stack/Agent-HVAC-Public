import pytest

from agent_hvac.physics import cycle as cycle_module
from agent_hvac.physics.balances import (
    ENERGY_BALANCE_TOLERANCE,
    MASS_BALANCE_TOLERANCE,
    energy_balance_residual,
    mass_balance_residual,
    require_balances_within_tolerance,
)
from agent_hvac.physics.state import ThermoState
from agent_hvac.properties.coolprop_backend import CoolPropBackend
from agent_hvac.schemas.design import DesignSpecification
from agent_hvac.schemas.provenance import Parameter, Provenance, SourceType
from agent_hvac.schemas.requirements import HITLMode, UserRequirements
from agent_hvac.schemas.results import SolverStatus
from agent_hvac.solvers.baseline_cycle import BaselineCycleSolver
from agent_hvac.utils.exceptions import ConvergenceError, InvalidPropertyStateError
from agent_hvac.utils.units import (
    Density,
    MassFlow,
    Pressure,
    Quantity,
    SpecificEnthalpy,
    SpecificEntropy,
    Temperature,
)

LOW_PRESSURE = 3_000_000.0
HIGH_PRESSURE = 9_000_000.0
SOURCE = Provenance(
    source_type=SourceType.HUMAN_CONFIRMED,
    source_ref="P02 approved analytical test input",
)


def _state(
    pressure: float,
    enthalpy: float,
    *,
    phase: str,
    entropy: float | None,
    temperature: float = 300.0,
    quality: float | None = None,
) -> ThermoState:
    return ThermoState(
        fluid="R744",
        pressure=Pressure(value=pressure, unit="Pa"),
        temperature=Temperature(value=temperature, unit="K"),
        enthalpy=SpecificEnthalpy(value=enthalpy, unit="J/kg"),
        density=Density(value=20.0, unit="kg/m^3"),
        phase=phase,
        vapor_quality=quality,
        entropy=(SpecificEntropy(value=entropy, unit="J/(kg*K)") if entropy is not None else None),
    )


class AnalyticalBackend:
    def __init__(
        self,
        *,
        inlet_phase: str = "gas",
        inlet_quality: float | None = None,
        inlet_entropy: float | None = 1_000.0,
        heat_rejection_outlet_enthalpy: float = 250_000.0,
    ) -> None:
        self.inlet_phase = inlet_phase
        self.inlet_quality = inlet_quality
        self.inlet_entropy = inlet_entropy
        self.heat_rejection_outlet_enthalpy = heat_rejection_outlet_enthalpy

    def state_pt(self, fluid: str, p: Pressure, temperature: Temperature) -> ThermoState:
        assert fluid == "R744"
        if p.value == LOW_PRESSURE:
            return _state(
                p.value,
                400_000.0,
                phase=self.inlet_phase,
                entropy=self.inlet_entropy,
                temperature=temperature.value,
                quality=self.inlet_quality,
            )
        return _state(
            p.value,
            self.heat_rejection_outlet_enthalpy,
            phase="supercritical",
            entropy=900.0,
            temperature=temperature.value,
        )

    def state_ps(self, fluid: str, p: Pressure, entropy: SpecificEntropy) -> ThermoState:
        assert fluid == "R744"
        return _state(
            p.value,
            450_000.0,
            phase="supercritical_gas",
            entropy=entropy.value,
            temperature=315.0,
        )

    def state_ph(self, fluid: str, p: Pressure, h: SpecificEnthalpy) -> ThermoState:
        assert fluid == "R744"
        if p.value == HIGH_PRESSURE:
            return _state(
                p.value,
                h.value,
                phase="supercritical_gas",
                entropy=1_050.0,
                temperature=325.0,
            )
        return _state(
            p.value,
            h.value,
            phase="twophase",
            entropy=950.0,
            temperature=270.0,
            quality=0.25,
        )


class FailingBackend(AnalyticalBackend):
    def state_pt(self, fluid: str, p: Pressure, temperature: Temperature) -> ThermoState:
        raise InvalidPropertyStateError("synthetic property failure")


class MissingEntropyBackend(AnalyticalBackend):
    def __init__(self, missing_at: str) -> None:
        super().__init__()
        self.missing_at = missing_at

    @staticmethod
    def _without_entropy(state: ThermoState) -> ThermoState:
        data = state.model_dump()
        data["entropy"] = None
        return ThermoState.model_validate(data)

    def state_pt(self, fluid: str, p: Pressure, temperature: Temperature) -> ThermoState:
        state = super().state_pt(fluid, p, temperature)
        target = "compressor_inlet" if p.value == LOW_PRESSURE else "heat_rejection_outlet"
        return self._without_entropy(state) if self.missing_at == target else state

    def state_ps(self, fluid: str, p: Pressure, entropy: SpecificEntropy) -> ThermoState:
        state = super().state_ps(fluid, p, entropy)
        return self._without_entropy(state) if self.missing_at == "isentropic_outlet" else state

    def state_ph(self, fluid: str, p: Pressure, h: SpecificEnthalpy) -> ThermoState:
        state = super().state_ph(fluid, p, h)
        target = "compressor_outlet" if p.value == HIGH_PRESSURE else "valve_outlet"
        return self._without_entropy(state) if self.missing_at == target else state


def _parameter(name: str, value: Quantity | str) -> Parameter:
    return Parameter(name=name, value=value, provenance=SOURCE)


def _design(
    *,
    low_pressure: Quantity | None = None,
    high_pressure: Quantity | None = None,
    efficiency: float = 0.8,
    mass_flow: float = 0.1,
    omit: str | None = None,
    is_mock: bool = False,
) -> DesignSpecification:
    values = {
        "evaporator_pressure": low_pressure or Pressure(value=LOW_PRESSURE, unit="Pa"),
        "high_side_pressure": high_pressure or Pressure(value=HIGH_PRESSURE, unit="Pa"),
        "compressor_inlet_temperature": Temperature(value=280.0, unit="K"),
        "heat_rejection_outlet_temperature": Temperature(value=310.0, unit="K"),
        "refrigerant_mass_flow": MassFlow(value=mass_flow, unit="kg/s"),
        "compressor_isentropic_efficiency": Quantity(value=efficiency, unit="dimensionless"),
    }
    if omit is not None:
        del values[omit]
    return DesignSpecification(
        design_id="P02-analytical",
        requirements=UserRequirements(
            raw_prompt="P02 explicit four-state baseline inputs",
            hitl_mode=HITLMode.AUTO,
        ),
        refrigerant=_parameter("refrigerant", "R744"),
        topology=_parameter("topology", "single-stage-baseline"),
        boundary_conditions=tuple(_parameter(name, value) for name, value in values.items()),
        is_mock=is_mock,
    )


def test_analytical_four_state_cycle_matches_closed_form_values() -> None:
    result = BaselineCycleSolver(AnalyticalBackend()).simulate(_design())

    assert result.status == SolverStatus.CONVERGED
    # The P02 route remains explicitly distinct from the P06 product-map route.
    compressor = cycle_module.evaluate_compressor(
        AnalyticalBackend(),
        _state(LOW_PRESSURE, 400_000.0, phase="gas", entropy=1_000.0),
        Pressure(value=HIGH_PRESSURE, unit="Pa"),
        0.8,
    )
    assert compressor.model_path == "ISENTROPIC_EFFICIENCY"
    assert tuple(result.state_points) == (
        "compressor_inlet",
        "compressor_outlet",
        "heat_rejection_outlet",
        "expansion_valve_outlet",
    )
    assert result.state_points["compressor_outlet"].enthalpy.value == pytest.approx(462_500.0)
    assert result.state_points["expansion_valve_outlet"].enthalpy.value == pytest.approx(250_000.0)
    assert result.compressor_power is not None
    assert result.evaporator_capacity is not None
    assert result.heat_rejection is not None
    assert result.compressor_power.value == pytest.approx(6_250.0, rel=1e-12)
    assert result.evaporator_capacity.value == pytest.approx(15_000.0, rel=1e-12)
    assert result.heat_rejection.value == pytest.approx(21_250.0, rel=1e-12)
    assert result.cop == pytest.approx(2.4, rel=1e-12)
    assert result.energy_balance_error == pytest.approx(0.0, abs=1e-15)
    assert result.mass_balance_error == pytest.approx(0.0, abs=1e-15)


def test_solver_preserves_design_mock_flag() -> None:
    result = BaselineCycleSolver(AnalyticalBackend()).simulate(_design(is_mock=True))

    assert result.status == SolverStatus.CONVERGED
    assert result.is_mock


@pytest.mark.parametrize(
    ("phase", "quality"),
    [
        ("liquid", None),
        ("supercritical_liquid", None),
        ("twophase", 0.25),
        ("gas", 0.25),
    ],
)
def test_rejects_liquid_or_wet_compressor_suction(phase: str, quality: float | None) -> None:
    backend = AnalyticalBackend(inlet_phase=phase, inlet_quality=quality)

    result = BaselineCycleSolver(backend).simulate(_design())

    assert result.status == SolverStatus.INFEASIBLE
    assert "compressor inlet" in result.messages[0]


def test_missing_backend_entropy_is_invalid_property_state() -> None:
    result = BaselineCycleSolver(AnalyticalBackend(inlet_entropy=None)).simulate(_design())

    assert result.status == SolverStatus.INVALID_PROPERTY_STATE
    assert "entropy" in result.messages[0]


@pytest.mark.parametrize(
    "missing_at",
    ["isentropic_outlet", "compressor_outlet", "heat_rejection_outlet", "valve_outlet"],
)
def test_missing_entropy_from_each_property_path_is_invalid(missing_at: str) -> None:
    result = BaselineCycleSolver(MissingEntropyBackend(missing_at)).simulate(_design())

    assert result.status == SolverStatus.INVALID_PROPERTY_STATE
    assert "entropy" in result.messages[0]


def test_backend_property_failure_is_invalid_property_state() -> None:
    result = BaselineCycleSolver(FailingBackend()).simulate(_design())

    assert result.status == SolverStatus.INVALID_PROPERTY_STATE
    assert "synthetic property failure" in result.messages[0]


@pytest.mark.parametrize("efficiency", [0.0, -0.1, 1.0001])
def test_rejects_invalid_compressor_efficiency(efficiency: float) -> None:
    result = BaselineCycleSolver(AnalyticalBackend()).simulate(_design(efficiency=efficiency))

    assert result.status == SolverStatus.INFEASIBLE
    assert "efficiency" in result.messages[0]


def test_extremely_small_efficiency_returns_explained_failure() -> None:
    result = BaselineCycleSolver(AnalyticalBackend()).simulate(_design(efficiency=1e-320))

    assert result.status == SolverStatus.INFEASIBLE
    assert "efficiency" in result.messages[0]
    assert "finite" in result.messages[0]


def test_nonfinite_derived_power_returns_explained_failure() -> None:
    result = BaselineCycleSolver(AnalyticalBackend()).simulate(_design(mass_flow=1e308))

    assert result.status == SolverStatus.INFEASIBLE
    assert "compressor power" in result.messages[0]
    assert "finite" in result.messages[0]


def test_rejects_reversed_cycle_pressures() -> None:
    result = BaselineCycleSolver(AnalyticalBackend()).simulate(
        _design(
            low_pressure=Pressure(value=10.0, unit="MPa"),
            high_pressure=Pressure(value=9.0, unit="MPa"),
        )
    )

    assert result.status == SolverStatus.INFEASIBLE
    assert "high_side_pressure" in result.messages[0]


def test_rejects_missing_or_wrong_dimension_input() -> None:
    missing = BaselineCycleSolver(AnalyticalBackend()).simulate(
        _design(omit="refrigerant_mass_flow")
    )
    wrong_dimension = BaselineCycleSolver(AnalyticalBackend()).simulate(
        _design(low_pressure=Quantity(value=280.0, unit="K"))
    )

    assert missing.status == SolverStatus.INFEASIBLE
    assert "refrigerant_mass_flow" in missing.messages[0]
    assert wrong_dimension.status == SolverStatus.INFEASIBLE
    assert "evaporator_pressure" in wrong_dimension.messages[0]


def test_rejects_nonpositive_cycle_duty_without_abs_or_clamp() -> None:
    result = BaselineCycleSolver(
        AnalyticalBackend(heat_rejection_outlet_enthalpy=420_000.0)
    ).simulate(_design())

    assert result.status == SolverStatus.INFEASIBLE
    assert "evaporator capacity" in result.messages[0]


def test_independent_balance_checks_reject_injected_imbalances() -> None:
    energy_error = energy_balance_residual(
        heat_rejection_w=21_000.0,
        evaporator_capacity_w=15_000.0,
        compressor_power_w=5_000.0,
    )
    mass_error = mass_balance_residual((0.10, 0.09, 0.10, 0.10))

    assert energy_error == pytest.approx(1_000.0 / 21_000.0)
    assert mass_error == pytest.approx(0.1)
    with pytest.raises(ConvergenceError, match="energy balance"):
        require_balances_within_tolerance(
            energy_error,
            0.0,
            energy_tolerance=ENERGY_BALANCE_TOLERANCE,
            mass_tolerance=MASS_BALANCE_TOLERANCE,
        )
    with pytest.raises(ConvergenceError, match="mass balance"):
        require_balances_within_tolerance(
            0.0,
            mass_error,
            energy_tolerance=ENERGY_BALANCE_TOLERANCE,
            mass_tolerance=MASS_BALANCE_TOLERANCE,
        )


@pytest.mark.parametrize(
    ("function_name", "residual", "message"),
    [
        ("energy_balance_residual", ENERGY_BALANCE_TOLERANCE * 2.0, "energy balance"),
        ("mass_balance_residual", MASS_BALANCE_TOLERANCE * 2.0, "mass balance"),
    ],
)
def test_solver_maps_balance_failure_to_unconverged(
    monkeypatch: pytest.MonkeyPatch,
    function_name: str,
    residual: float,
    message: str,
) -> None:
    monkeypatch.setattr(cycle_module, function_name, lambda *args, **kwargs: residual)

    result = BaselineCycleSolver(AnalyticalBackend()).simulate(_design())

    assert result.status == SolverStatus.UNCONVERGED
    assert message in result.messages[0]


def test_basic_r744_cycle_is_deterministic_and_conservative() -> None:
    solver = BaselineCycleSolver(CoolPropBackend())
    design = _design()

    first = solver.simulate(design)
    second = solver.simulate(design)

    assert first == second
    assert first.status == SolverStatus.CONVERGED
    assert first.compressor_power is not None and first.compressor_power.value > 0
    assert first.evaporator_capacity is not None and first.evaporator_capacity.value > 0
    assert first.heat_rejection is not None and first.heat_rejection.value > 0
    assert first.cop is not None and first.cop > 0
    assert first.energy_balance_error is not None
    assert first.energy_balance_error <= ENERGY_BALANCE_TOLERANCE
    assert first.mass_balance_error is not None
    assert first.mass_balance_error <= MASS_BALANCE_TOLERANCE
    assert {name: state.phase for name, state in first.state_points.items()} == {
        "compressor_inlet": "gas",
        "compressor_outlet": "supercritical",
        "heat_rejection_outlet": "supercritical",
        "expansion_valve_outlet": "twophase",
    }
    assert all(state.entropy is not None for state in first.state_points.values())

    expected_states = {
        "compressor_inlet": (280.0, 451_819.6561833148, 72.80511370945847, 1_941.9704216021107),
        "compressor_outlet": (
            375.6681128305702,
            515_706.56490777474,
            161.68158117945936,
            1_976.3944755759276,
        ),
        "heat_rejection_outlet": (
            310.0,
            311_097.4821809954,
            614.8734814218916,
            1_355.177005712615,
        ),
        "expansion_valve_outlet": (
            267.5978703862791,
            311_097.4821809954,
            150.0102114933525,
            1_417.5780186373793,
        ),
    }
    for name, (temperature, enthalpy, density, entropy) in expected_states.items():
        state = first.state_points[name]
        assert state.temperature.value == pytest.approx(temperature, rel=1e-9)
        assert state.enthalpy.value == pytest.approx(enthalpy, rel=1e-9)
        assert state.density.value == pytest.approx(density, rel=1e-9)
        assert state.entropy is not None
        assert state.entropy.value == pytest.approx(entropy, rel=1e-9)

    assert first.compressor_power.value == pytest.approx(6_388.690872445994, rel=1e-9)
    assert first.evaporator_capacity.value == pytest.approx(14_072.21740023194, rel=1e-9)
    assert first.heat_rejection.value == pytest.approx(20_460.908272677934, rel=1e-9)
    assert first.cop == pytest.approx(2.2026762103836477, rel=1e-9)
    assert first.state_points["expansion_valve_outlet"].vapor_quality == pytest.approx(
        0.5037076458107905, rel=1e-9
    )
