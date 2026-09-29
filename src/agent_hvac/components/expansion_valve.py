"""Isenthalpic expansion-valve calculation."""

from agent_hvac.physics.state import ThermoState
from agent_hvac.properties.base import PropertyBackend
from agent_hvac.utils.exceptions import InfeasibleDesignError, InvalidPropertyStateError
from agent_hvac.utils.units import Pressure


def evaluate_expansion_valve(
    backend: PropertyBackend,
    inlet: ThermoState,
    outlet_pressure: Pressure,
) -> ThermoState:
    """Return the outlet at unchanged specific enthalpy."""
    if outlet_pressure.value >= inlet.pressure.value:
        raise InfeasibleDesignError("expansion-valve outlet pressure must be below inlet pressure")
    outlet = backend.state_ph(inlet.fluid, outlet_pressure, inlet.enthalpy)
    if outlet.entropy is None:
        raise InvalidPropertyStateError("expansion-valve outlet state is missing entropy")
    return outlet
