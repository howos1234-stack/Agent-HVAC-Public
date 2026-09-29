"""Thermodynamic state data only; no property calculations."""

from pydantic import Field

from agent_hvac.schemas.base import ContractModel, NonEmptyStr
from agent_hvac.utils.units import (
    Density,
    Pressure,
    SpecificEnthalpy,
    SpecificEntropy,
    Temperature,
)


class ThermoState(ContractModel):
    fluid: NonEmptyStr
    pressure: Pressure
    temperature: Temperature
    enthalpy: SpecificEnthalpy
    density: Density
    phase: NonEmptyStr
    vapor_quality: float | None = Field(default=None, ge=0, le=1)
    entropy: SpecificEntropy | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
