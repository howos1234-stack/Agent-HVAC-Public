"""Correlation metadata and applicability-based selection for WS-A physics models."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from agent_hvac.utils.exceptions import InfeasibleDesignError


@dataclass(frozen=True)
class CorrelationMetadata:
    """Traceable engineering-correlation identity and validity limits."""

    name: str
    equation: str
    reference: str
    applicability: str
    refrigerant_range: str
    geometry_range: str
    phase_range: frozenset[str]
    validation_cases: tuple[str, ...]


class DarcyFrictionCorrelation(Protocol):
    metadata: CorrelationMetadata

    def supports(
        self,
        reynolds_number: float,
        relative_roughness: float,
        phase_regime: str,
    ) -> bool: ...

    def evaluate(self, reynolds_number: float, relative_roughness: float) -> float: ...


class CorrelationRegistry:
    """Select one correlation only when its documented range applies."""

    def __init__(self, correlations: tuple[DarcyFrictionCorrelation, ...] = ()) -> None:
        self._correlations: dict[str, DarcyFrictionCorrelation] = {}
        for correlation in correlations:
            self.register(correlation)

    @property
    def metadata(self) -> tuple[CorrelationMetadata, ...]:
        return tuple(correlation.metadata for correlation in self._correlations.values())

    def register(self, correlation: DarcyFrictionCorrelation) -> None:
        name = correlation.metadata.name
        if name in self._correlations:
            raise ValueError(f"correlation {name!r} is already registered")
        self._correlations[name] = correlation

    def select_darcy_friction(
        self,
        *,
        reynolds_number: float,
        relative_roughness: float,
        phase_regime: str,
    ) -> DarcyFrictionCorrelation:
        if not math.isfinite(reynolds_number) or reynolds_number <= 0.0:
            raise InfeasibleDesignError("Reynolds number must be finite and positive")
        if not math.isfinite(relative_roughness) or relative_roughness < 0.0:
            raise InfeasibleDesignError("relative roughness must be finite and nonnegative")

        matches = tuple(
            correlation
            for correlation in self._correlations.values()
            if correlation.supports(reynolds_number, relative_roughness, phase_regime)
        )
        if not matches:
            raise InfeasibleDesignError(
                "no registered Darcy friction correlation applies to "
                f"phase_regime={phase_regime!r}, Re={reynolds_number:.12g}, "
                f"relative_roughness={relative_roughness:.12g}"
            )
        if len(matches) > 1:
            names = ", ".join(correlation.metadata.name for correlation in matches)
            raise InfeasibleDesignError(
                f"ambiguous Darcy friction correlation applicability: {names}"
            )
        return matches[0]
