"""ACR-0004 consistency checks, not independent mixture/manufacturer validation."""

import pytest
from CoolProp.CoolProp import PropsSI

from agent_hvac.properties.coolprop_backend import CoolPropBackend
from agent_hvac.utils.exceptions import InvalidPropertyStateError
from agent_hvac.utils.units import Pressure, SpecificEnthalpy, Temperature


@pytest.mark.parametrize("pressure,temperature,phase", [(1e6, 290, "gas"), (2.8e6, 305, "liquid")])
def test_r410a_pt_ph_ps_roundtrip(pressure, temperature, phase):
    backend = CoolPropBackend()
    state = backend.state_pt(
        "R410A", Pressure(value=pressure, unit="Pa"), Temperature(value=temperature, unit="K")
    )
    assert state.phase == phase and state.fluid == "R410A"
    for recovered in [
        backend.state_ph("R410A", state.pressure, state.enthalpy),
        backend.state_ps("R410A", state.pressure, state.entropy),
    ]:
        assert recovered.temperature.value == pytest.approx(temperature, abs=2e-6)
        assert recovered.enthalpy.value == pytest.approx(state.enthalpy.value, abs=0.01)
        assert recovered.density.value == pytest.approx(state.density.value, rel=1e-7)


@pytest.mark.parametrize("quality", [0.1, 0.5, 0.9])
def test_r410a_two_phase_ph_ps(quality):
    # Direct CoolProp is a consistency oracle, not an independent EOS reference.
    h = PropsSI("Hmass", "P", 1e6, "Q", quality, "R410A")
    backend = CoolPropBackend()
    state = backend.state_ph(
        "R410A", Pressure(value=1e6, unit="Pa"), SpecificEnthalpy(value=h, unit="J/kg")
    )
    assert state.phase == "twophase"
    assert state.vapor_quality == pytest.approx(quality, abs=1e-8)
    recovered = backend.state_ps("R410A", state.pressure, state.entropy)
    assert recovered.enthalpy.value == pytest.approx(h, abs=0.01)
    assert recovered.vapor_quality == pytest.approx(quality, abs=1e-6)


@pytest.mark.parametrize(
    "fluid", ["R407C", "R410a", "R-410 A", "HEOS::R410A", "R32[0.5]&R125[0.5]"]
)
def test_limit_is_exact_identifier(fluid):
    with pytest.raises(InvalidPropertyStateError):
        CoolPropBackend().state_pt(
            fluid, Pressure(value=1e6, unit="Pa"), Temperature(value=290, unit="K")
        )


def test_r410a_saturation_band_and_invalid_temperature_fail():
    bubble = PropsSI("T", "P", 1e6, "Q", 0, "R410A")
    dew = PropsSI("T", "P", 1e6, "Q", 1, "R410A")
    for t in [(bubble + dew) / 2, 100]:
        with pytest.raises(InvalidPropertyStateError):
            CoolPropBackend().state_pt(
                "R410A", Pressure(value=1e6, unit="Pa"), Temperature(value=t, unit="K")
            )
