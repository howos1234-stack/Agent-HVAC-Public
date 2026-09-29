"""Property backend contract. Implementations arrive in P01."""

from typing import Protocol

from agent_hvac.physics.state import ThermoState
from agent_hvac.utils.units import Pressure, SpecificEnthalpy, SpecificEntropy, Temperature


class PropertyBackend(Protocol):
    def state_ph(self, fluid: str, p: Pressure, h: SpecificEnthalpy) -> ThermoState: ...

    def state_pt(self, fluid: str, p: Pressure, temperature: Temperature) -> ThermoState: ...

    def state_ps(self, fluid: str, p: Pressure, entropy: SpecificEntropy) -> ThermoState: ...
