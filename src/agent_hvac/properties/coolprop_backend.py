"""CoolProp implementation of the frozen P01 property backend contract."""

from __future__ import annotations

import math
from collections.abc import Callable

from CoolProp.CoolProp import (
    PhaseSI,
    PropsSI,
    get_fluid_param_string,
)

from agent_hvac.physics.state import ThermoState
from agent_hvac.utils.exceptions import InvalidPropertyStateError
from agent_hvac.utils.units import (
    Density,
    Pressure,
    SpecificEnthalpy,
    SpecificEntropy,
    Temperature,
)

_ALLOWED_PHASES = frozenset(
    {
        "critical_point",
        "gas",
        "liquid",
        "supercritical",
        "supercritical_gas",
        "supercritical_liquid",
        "twophase",
    }
)
_DISALLOWED_FLUID_TOKENS = ("::", "&", "[", "]")
_QUALITY_ENDPOINT_TOLERANCE = 1e-10


class CoolPropBackend:
    """PropertyBackend adapter using CoolProp mass-specific SI values.

    The frozen contract carries only a fluid identifier, not composition or backend
    provenance. This adapter therefore accepts CoolProp pure-fluid identifiers and
    aliases, plus exactly R410A under approved ACR-0004. Other mixtures remain pending.
    """

    def state_ph(
        self,
        fluid: str,
        p: Pressure,
        h: SpecificEnthalpy,
    ) -> ThermoState:
        """Evaluate a pure-fluid state from pressure and specific enthalpy."""
        checked_fluid = self._validate_fluid(fluid)
        context = f"fluid={checked_fluid!r}, P={p.value} Pa, Hmass={h.value} J/kg"
        temperature = self._property("T", "P", p.value, "Hmass", h.value, checked_fluid, context)
        density = self._property("Dmass", "P", p.value, "Hmass", h.value, checked_fluid, context)
        entropy = self._property("Smass", "P", p.value, "Hmass", h.value, checked_fluid, context)
        phase = self._phase("P", p.value, "Hmass", h.value, checked_fluid, context)
        quality = self._quality(phase, "P", p.value, "Hmass", h.value, checked_fluid, context)
        return ThermoState(
            fluid=fluid,
            pressure=p,
            temperature=Temperature(value=temperature, unit="K"),
            enthalpy=h,
            density=Density(value=density, unit="kg/m^3"),
            phase=phase,
            vapor_quality=quality,
            entropy=SpecificEntropy(value=entropy, unit="J/(kg*K)"),
        )

    def state_pt(
        self,
        fluid: str,
        p: Pressure,
        temperature: Temperature,
    ) -> ThermoState:
        """Evaluate a pure-fluid state from pressure and temperature."""
        checked_fluid = self._validate_fluid(fluid)
        context = f"fluid={checked_fluid!r}, P={p.value} Pa, T={temperature.value} K"
        enthalpy = self._property(
            "Hmass", "P", p.value, "T", temperature.value, checked_fluid, context
        )
        density = self._property(
            "Dmass", "P", p.value, "T", temperature.value, checked_fluid, context
        )
        entropy = self._property(
            "Smass", "P", p.value, "T", temperature.value, checked_fluid, context
        )
        phase = self._phase("P", p.value, "T", temperature.value, checked_fluid, context)
        quality = self._quality(phase, "P", p.value, "T", temperature.value, checked_fluid, context)
        return ThermoState(
            fluid=fluid,
            pressure=p,
            temperature=temperature,
            enthalpy=SpecificEnthalpy(value=enthalpy, unit="J/kg"),
            density=Density(value=density, unit="kg/m^3"),
            phase=phase,
            vapor_quality=quality,
            entropy=SpecificEntropy(value=entropy, unit="J/(kg*K)"),
        )

    def state_ps(
        self,
        fluid: str,
        p: Pressure,
        entropy: SpecificEntropy,
    ) -> ThermoState:
        """Evaluate a pure-fluid state from pressure and mass-specific entropy."""
        checked_fluid = self._validate_fluid(fluid)
        context = f"fluid={checked_fluid!r}, P={p.value} Pa, Smass={entropy.value} J/(kg*K)"
        temperature = self._property(
            "T", "P", p.value, "Smass", entropy.value, checked_fluid, context
        )
        enthalpy = self._property(
            "Hmass", "P", p.value, "Smass", entropy.value, checked_fluid, context
        )
        density = self._property(
            "Dmass", "P", p.value, "Smass", entropy.value, checked_fluid, context
        )
        phase = self._phase("P", p.value, "Smass", entropy.value, checked_fluid, context)
        quality = self._quality(phase, "P", p.value, "Smass", entropy.value, checked_fluid, context)
        return ThermoState(
            fluid=fluid,
            pressure=p,
            temperature=Temperature(value=temperature, unit="K"),
            enthalpy=SpecificEnthalpy(value=enthalpy, unit="J/kg"),
            density=Density(value=density, unit="kg/m^3"),
            phase=phase,
            vapor_quality=quality,
            entropy=entropy,
        )

    @staticmethod
    def _validate_fluid(fluid: str) -> str:
        if (
            not isinstance(fluid, str)
            or not fluid
            or fluid != fluid.strip()
            or any(token in fluid for token in _DISALLOWED_FLUID_TOKENS)
        ):
            raise InvalidPropertyStateError(
                "fluid must be an unprefixed CoolProp pure-fluid identifier"
            )
        try:
            is_pure = get_fluid_param_string(fluid, "pure").lower() == "true"
        except (RuntimeError, TypeError, ValueError) as exc:
            raise InvalidPropertyStateError(
                f"unknown CoolProp fluid identifier: {fluid!r}"
            ) from exc
        if not is_pure and fluid != "R410A":
            raise InvalidPropertyStateError(
                "mixture and pseudo-pure inputs require an approved contract extension"
            )
        return fluid

    @staticmethod
    def _call(
        operation: Callable[[], float | str],
        context: str,
    ) -> float | str:
        try:
            return operation()
        except (RuntimeError, TypeError, ValueError, OverflowError) as exc:
            raise InvalidPropertyStateError(f"CoolProp rejected state: {context}") from exc

    @classmethod
    def _property(
        cls,
        output: str,
        name1: str,
        value1: float,
        name2: str,
        value2: float,
        fluid: str,
        context: str,
    ) -> float:
        raw = cls._call(
            lambda: PropsSI(output, name1, value1, name2, value2, fluid),
            context,
        )
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise InvalidPropertyStateError(
                f"CoolProp returned a non-numeric {output}: {context}"
            ) from exc
        if not math.isfinite(value):
            raise InvalidPropertyStateError(f"CoolProp returned a non-finite {output}: {context}")
        return value

    @classmethod
    def _phase(
        cls,
        name1: str,
        value1: float,
        name2: str,
        value2: float,
        fluid: str,
        context: str,
    ) -> str:
        raw = cls._call(
            lambda: PhaseSI(name1, value1, name2, value2, fluid),
            context,
        )
        phase = str(raw)
        if phase not in _ALLOWED_PHASES:
            raise InvalidPropertyStateError(
                f"CoolProp returned unsupported phase {phase!r}: {context}"
            )
        return phase

    @classmethod
    def _quality(
        cls,
        phase: str,
        name1: str,
        value1: float,
        name2: str,
        value2: float,
        fluid: str,
        context: str,
    ) -> float | None:
        if phase != "twophase":
            return None
        quality = cls._property("Q", name1, value1, name2, value2, fluid, context)
        if abs(quality) <= _QUALITY_ENDPOINT_TOLERANCE:
            return 0.0
        if abs(1.0 - quality) <= _QUALITY_ENDPOINT_TOLERANCE:
            return 1.0
        if 0.0 < quality < 1.0:
            return quality
        raise InvalidPropertyStateError(
            f"CoolProp returned vapor quality outside [0, 1]: {context}"
        )
