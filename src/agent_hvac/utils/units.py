"""Explicit physical quantities at service boundaries; Pint performs unit conversion."""

import math
from typing import ClassVar, Self

import pint
from pydantic import model_validator

from agent_hvac.schemas.base import ContractModel, NonEmptyStr

_REGISTRY: pint.UnitRegistry[float] = pint.UnitRegistry()


class Quantity(ContractModel):
    """Finite scalar with a unit; normalized to SI when constructed.

    Absolute temperatures use Temperature; differences use TemperatureDifference.
    Generic quantities allow dimensionless metrics but never implicit units.
    """

    value: float
    unit: NonEmptyStr
    canonical_unit: ClassVar[str | None] = None
    positive: ClassVar[bool] = False

    @model_validator(mode="after")
    def normalize(self) -> Self:
        try:
            raw = _REGISTRY.Quantity(self.value, self.unit)
            converted = raw.to(self.canonical_unit) if self.canonical_unit else raw.to_base_units()
            value = float(converted.magnitude)
        except (pint.errors.PintError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid or incompatible unit: {self.unit}") from exc
        if not math.isfinite(value):
            raise ValueError("Quantity must be finite")
        if self.positive and value <= 0:
            raise ValueError("Quantity must be strictly positive")
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "unit", str(converted.units))
        return self


class Pressure(Quantity):
    """Absolute pressure; gauge values must be converted with explicit reference."""

    canonical_unit = "Pa"
    positive = True


class Temperature(Quantity):
    """Absolute thermodynamic temperature, strictly above zero kelvin."""

    canonical_unit = "K"
    positive = True

    @model_validator(mode="before")
    @classmethod
    def reject_delta(cls, data: object) -> object:
        if isinstance(data, dict) and "delta_" in str(data.get("unit", "")):
            raise ValueError("A temperature difference is not an absolute temperature")
        return data


class TemperatureDifference(Quantity):
    canonical_unit = "K"

    @model_validator(mode="before")
    @classmethod
    def reject_offset(cls, data: object) -> object:
        if isinstance(data, dict) and data.get("unit") not in (
            "K",
            "kelvin",
            "delta_degC",
            "delta_degree_Celsius",
            "delta_degF",
        ):
            raise ValueError("Use K or an explicit delta temperature unit")
        return data


class Length(Quantity):
    canonical_unit = "m"
    positive = True


class Power(Quantity):
    canonical_unit = "W"


class MassFlow(Quantity):
    canonical_unit = "kg/s"
    positive = True


class SpecificEnthalpy(Quantity):
    canonical_unit = "J/kg"


class SpecificEntropy(Quantity):
    """Finite mass-specific entropy; the backend decides state validity."""

    canonical_unit = "J/(kg*K)"


class Density(Quantity):
    canonical_unit = "kg/m^3"
    positive = True


class PressureDifference(Quantity):
    """Nonnegative pressure loss, including the zero-loss limit (not a signed delta)."""

    canonical_unit = "Pa"

    @model_validator(mode="after")
    def nonnegative_loss(self) -> Self:
        if self.value < 0:
            raise ValueError("Pressure drop must be nonnegative")
        return self
