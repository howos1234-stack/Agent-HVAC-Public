"""P01 CoolProp adapter validation against documented NIST R744 points."""

import math

import pytest

from agent_hvac.properties.base import PropertyBackend
from agent_hvac.properties.coolprop_backend import CoolPropBackend
from agent_hvac.utils.exceptions import InvalidPropertyStateError
from agent_hvac.utils.units import Pressure, SpecificEnthalpy, SpecificEntropy, Temperature

PROPERTY_RTOL = 5e-5


@pytest.fixture
def backend() -> PropertyBackend:
    return CoolPropBackend()


@pytest.mark.parametrize(
    ("pressure_mpa", "temperature_k", "density", "enthalpy_kj_kg", "phase"),
    [
        (5.0, 270.0, 959.393695239, 191.049178616, "liquid"),
        (1.0, 300.0, 18.5793760380, 498.837884877, "gas"),
        (9.0, 320.0, 313.450801468, 400.559271680, "supercritical"),
    ],
)
def test_r744_pt_matches_nist_reference(
    backend: PropertyBackend,
    pressure_mpa: float,
    temperature_k: float,
    density: float,
    enthalpy_kj_kg: float,
    phase: str,
) -> None:
    state = backend.state_pt(
        "R744",
        Pressure(value=pressure_mpa, unit="MPa"),
        Temperature(value=temperature_k, unit="K"),
    )

    assert state.pressure.unit == "pascal"
    assert state.temperature.unit == "kelvin"
    assert state.enthalpy.unit == "joule / kilogram"
    assert state.density.unit == "kilogram / meter ** 3"
    assert state.entropy is not None
    assert state.entropy.unit == "joule / kelvin / kilogram"
    assert state.enthalpy.value == pytest.approx(enthalpy_kj_kg * 1_000, rel=PROPERTY_RTOL)
    assert state.density.value == pytest.approx(density, rel=PROPERTY_RTOL)
    assert state.phase == phase
    assert state.vapor_quality is None


@pytest.mark.parametrize(
    ("enthalpy_kj_kg", "density", "quality"),
    [
        (192.413428170, 945.826894738, 0.0),
        (432.556457629, 88.3735621676, 1.0),
    ],
)
def test_r744_ph_recovers_nist_saturation_endpoints(
    backend: PropertyBackend,
    enthalpy_kj_kg: float,
    density: float,
    quality: float,
) -> None:
    state = backend.state_ph(
        "CO2",
        Pressure(value=3.20334736808, unit="MPa"),
        SpecificEnthalpy(value=enthalpy_kj_kg, unit="kJ/kg"),
    )

    assert state.temperature.value == pytest.approx(270.0, abs=1e-6)
    assert state.density.value == pytest.approx(density, rel=PROPERTY_RTOL)
    assert state.phase == "twophase"
    assert state.vapor_quality == quality


@pytest.mark.parametrize(
    ("pressure_mpa", "temperature_k", "phase"),
    [
        (5.0, 270.0, "liquid"),
        (1.0, 300.0, "gas"),
        (9.0, 320.0, "supercritical"),
    ],
)
def test_r744_single_phase_pt_to_ph_round_trip(
    backend: PropertyBackend,
    pressure_mpa: float,
    temperature_k: float,
    phase: str,
) -> None:
    state_pt = backend.state_pt(
        "R744",
        Pressure(value=pressure_mpa, unit="MPa"),
        Temperature(value=temperature_k, unit="K"),
    )
    state_ph = backend.state_ph("R744", state_pt.pressure, state_pt.enthalpy)

    assert state_ph.temperature.value == pytest.approx(state_pt.temperature.value, abs=2e-6)
    assert state_ph.density.value == pytest.approx(state_pt.density.value, rel=1e-9)
    assert state_ph.phase == state_pt.phase == phase
    assert state_ph.vapor_quality is None
    assert state_pt.entropy is not None
    assert state_ph.entropy is not None
    assert state_ph.entropy.value == pytest.approx(state_pt.entropy.value, rel=1e-10)


@pytest.mark.parametrize(
    ("pressure_mpa", "temperature_k", "phase"),
    [
        (1.0, 300.0, "gas"),
        (9.0, 320.0, "supercritical"),
    ],
)
def test_r744_single_phase_pt_to_ps_round_trip(
    backend: PropertyBackend,
    pressure_mpa: float,
    temperature_k: float,
    phase: str,
) -> None:
    state_pt = backend.state_pt(
        "R744",
        Pressure(value=pressure_mpa, unit="MPa"),
        Temperature(value=temperature_k, unit="K"),
    )
    assert state_pt.entropy is not None

    state_ps = backend.state_ps("R744", state_pt.pressure, state_pt.entropy)

    assert state_ps.temperature.value == pytest.approx(state_pt.temperature.value, abs=2e-6)
    assert state_ps.enthalpy.value == pytest.approx(state_pt.enthalpy.value, rel=1e-10)
    assert state_ps.density.value == pytest.approx(state_pt.density.value, rel=1e-9)
    assert state_ps.phase == phase
    assert state_ps.entropy == state_pt.entropy


def test_r744_ph_recovers_interior_two_phase_quality(
    backend: PropertyBackend,
) -> None:
    saturated_liquid_h = 192.413428170
    saturated_vapor_h = 432.556457629
    midpoint_h = (saturated_liquid_h + saturated_vapor_h) / 2

    state = backend.state_ph(
        "R744",
        Pressure(value=3.20334736808, unit="MPa"),
        SpecificEnthalpy(value=midpoint_h, unit="kJ/kg"),
    )

    assert state.temperature.value == pytest.approx(270.0, abs=1e-6)
    assert state.phase == "twophase"
    assert state.vapor_quality == pytest.approx(0.5, abs=1e-9)


@pytest.mark.parametrize(
    ("pressure_mpa", "temperature_k", "phase"),
    [
        (8.0, 300.0, "supercritical_liquid"),
        (7.0, 310.0, "supercritical_gas"),
        (7.377298373446752, 304.1282000029807, "critical_point"),
        (8.0, 310.0, "supercritical"),
    ],
)
def test_r744_critical_region_phase_classification(
    backend: PropertyBackend,
    pressure_mpa: float,
    temperature_k: float,
    phase: str,
) -> None:
    state = backend.state_pt(
        "R744",
        Pressure(value=pressure_mpa, unit="MPa"),
        Temperature(value=temperature_k, unit="K"),
    )

    assert state.phase == phase
    assert math.isfinite(state.enthalpy.value)
    assert math.isfinite(state.density.value)
    assert state.density.value > 0
    assert state.vapor_quality is None


def test_state_pt_normalizes_non_si_input_units(backend: PropertyBackend) -> None:
    state = backend.state_pt(
        "CarbonDioxide",
        Pressure(value=50.0, unit="bar"),
        Temperature(value=-3.15, unit="degC"),
    )

    assert state.pressure.value == pytest.approx(5_000_000.0)
    assert state.temperature.value == pytest.approx(270.0)
    assert state.enthalpy.value == pytest.approx(191_049.178616, rel=PROPERTY_RTOL)


def test_rejects_incompatible_pressure_unit_before_backend_call() -> None:
    with pytest.raises(ValueError, match="Invalid or incompatible unit"):
        Pressure(value=1.0, unit="K")


def test_rejects_temperature_difference_as_absolute_temperature() -> None:
    with pytest.raises(ValueError, match="temperature difference"):
        Temperature(value=10.0, unit="delta_degC")


@pytest.mark.parametrize(
    "fluid",
    ["", "NotAFluid", "R407C", "HEOS::R744", "R744[0.5]&Water[0.5]"],
)
def test_rejects_unknown_or_non_pure_fluid_inputs(
    backend: PropertyBackend,
    fluid: str,
) -> None:
    with pytest.raises(InvalidPropertyStateError):
        backend.state_pt(
            fluid,
            Pressure(value=1.0, unit="MPa"),
            Temperature(value=300.0, unit="K"),
        )


def test_translates_out_of_domain_state_to_service_error(
    backend: PropertyBackend,
) -> None:
    with pytest.raises(InvalidPropertyStateError, match="CoolProp rejected state"):
        backend.state_pt(
            "R744",
            Pressure(value=1.0, unit="Pa"),
            Temperature(value=1.0, unit="K"),
        )


def test_translates_invalid_ph_state_to_service_error(
    backend: PropertyBackend,
) -> None:
    with pytest.raises(InvalidPropertyStateError, match="CoolProp rejected state"):
        backend.state_ph(
            "R744",
            Pressure(value=1.0, unit="Pa"),
            SpecificEnthalpy(value=0.0, unit="J/kg"),
        )


def test_translates_invalid_ps_state_to_service_error(
    backend: PropertyBackend,
) -> None:
    with pytest.raises(InvalidPropertyStateError, match="CoolProp rejected state"):
        backend.state_ps(
            "R744",
            Pressure(value=1.0, unit="Pa"),
            SpecificEntropy(value=0.0, unit="J/(kg*K)"),
        )


def test_rejects_ambiguous_pt_state_at_saturation(
    backend: PropertyBackend,
) -> None:
    with pytest.raises(InvalidPropertyStateError, match="CoolProp rejected state"):
        backend.state_pt(
            "R744",
            Pressure(value=3.20334736808, unit="MPa"),
            Temperature(value=270.0, unit="K"),
        )
