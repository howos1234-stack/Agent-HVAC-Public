"""Single-stage compressor calculation through the property-backend boundary."""

import math
from dataclasses import dataclass
from typing import Literal

from agent_hvac.physics.state import ThermoState
from agent_hvac.properties.base import PropertyBackend
from agent_hvac.utils.exceptions import InfeasibleDesignError, InvalidPropertyStateError
from agent_hvac.utils.units import Pressure, SpecificEnthalpy

_ALLOWED_SUCTION_PHASES = frozenset({"gas", "supercritical_gas", "supercritical"})


@dataclass(frozen=True)
class CompressorResult:
    isentropic_outlet: ThermoState
    outlet: ThermoState
    specific_work_j_kg: float

    @property
    def model_path(self) -> Literal["ISENTROPIC_EFFICIENCY"]:
        """Identify the P02 calculation path without changing result construction."""
        return "ISENTROPIC_EFFICIENCY"


def evaluate_compressor(
    backend: PropertyBackend,
    inlet: ThermoState,
    outlet_pressure: Pressure,
    isentropic_efficiency: float,
) -> CompressorResult:
    """Calculate an adiabatic compressor without hiding invalid inputs."""
    if inlet.phase not in _ALLOWED_SUCTION_PHASES or inlet.vapor_quality is not None:
        raise InfeasibleDesignError(
            "compressor inlet must be dry gas, supercritical gas, or supercritical fluid"
        )
    if inlet.entropy is None:
        raise InvalidPropertyStateError("compressor inlet state is missing entropy")
    if outlet_pressure.value <= inlet.pressure.value:
        raise InfeasibleDesignError("compressor outlet pressure must exceed inlet pressure")
    if not 0.0 < isentropic_efficiency <= 1.0:
        raise InfeasibleDesignError("compressor isentropic efficiency must be in (0, 1]")

    isentropic_outlet = backend.state_ps(inlet.fluid, outlet_pressure, inlet.entropy)
    if isentropic_outlet.entropy is None:
        raise InvalidPropertyStateError("isentropic compressor outlet is missing entropy")
    ideal_rise = isentropic_outlet.enthalpy.value - inlet.enthalpy.value
    if not math.isfinite(ideal_rise):
        raise InfeasibleDesignError("compressor isentropic enthalpy rise must be finite")
    if ideal_rise <= 0.0:
        raise InfeasibleDesignError("compressor isentropic enthalpy rise must be positive")

    actual_rise = ideal_rise / isentropic_efficiency
    if not math.isfinite(actual_rise):
        raise InfeasibleDesignError(
            "compressor specific work must be finite; "
            f"efficiency={isentropic_efficiency!r} caused numerical overflow"
        )
    if actual_rise <= 0.0:
        raise InfeasibleDesignError("compressor specific work must be positive")
    outlet_enthalpy = inlet.enthalpy.value + actual_rise
    if not math.isfinite(outlet_enthalpy):
        raise InfeasibleDesignError("compressor outlet enthalpy must be finite")
    outlet = backend.state_ph(
        inlet.fluid,
        outlet_pressure,
        SpecificEnthalpy(value=outlet_enthalpy, unit="J/kg"),
    )
    if outlet.entropy is None:
        raise InvalidPropertyStateError("compressor outlet state is missing entropy")
    return CompressorResult(
        isentropic_outlet=isentropic_outlet,
        outlet=outlet,
        specific_work_j_kg=actual_rise,
    )
