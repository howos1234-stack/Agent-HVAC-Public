"""Darcy friction-factor correlations for a straight circular single-phase pipe."""

from __future__ import annotations

import math
from dataclasses import dataclass

from agent_hvac.physics.correlations.registry import CorrelationMetadata, CorrelationRegistry
from agent_hvac.utils.exceptions import InfeasibleDesignError

_SINGLE_PHASE = frozenset({"single_phase"})


@dataclass(frozen=True)
class LaminarDarcyFrictionFactor:
    """Fully developed circular-pipe Darcy factor, f_D = 64 / Re."""

    metadata = CorrelationMetadata(
        name="laminar-fully-developed-circular-64-over-re",
        equation="f_D = 64 / Re",
        reference=(
            "Darcy-Weisbach laminar circular-pipe solution; documented for P04 in "
            "docs/workstreams/ws_a/P04_PIPE_1D_PLAN.md"
        ),
        applicability="steady, fully developed laminar internal flow with 0 < Re < 2300",
        refrigerant_range="single-phase Newtonian fluid with supplied dynamic viscosity",
        geometry_range="straight circular pipe; 0 <= relative roughness <= 0.05",
        phase_range=_SINGLE_PHASE,
        validation_cases=("P04 constant-density analytical pressure-drop case",),
    )

    def supports(
        self,
        reynolds_number: float,
        relative_roughness: float,
        phase_regime: str,
    ) -> bool:
        return (
            phase_regime in self.metadata.phase_range
            and 0.0 < reynolds_number < 2300.0
            and 0.0 <= relative_roughness <= 0.05
        )

    def evaluate(self, reynolds_number: float, relative_roughness: float) -> float:
        if not self.supports(reynolds_number, relative_roughness, "single_phase"):
            raise InfeasibleDesignError("laminar friction correlation is outside its range")
        return 64.0 / reynolds_number


@dataclass(frozen=True)
class HaalandDarcyFrictionFactor:
    """Haaland's explicit turbulent Darcy friction-factor approximation."""

    metadata = CorrelationMetadata(
        name="haaland-1983-darcy-friction",
        equation=("1/sqrt(f_D) = -1.8*log10((relative_roughness/3.7)^1.11 + 6.9/Re)"),
        reference=(
            "S. E. Haaland, Journal of Fluids Engineering 105(1), 89-90 (1983), "
            "doi:10.1115/1.3240948"
        ),
        applicability="steady turbulent internal flow with 4000 <= Re <= 1e8",
        refrigerant_range="single-phase Newtonian fluid with supplied dynamic viscosity",
        geometry_range="straight circular pipe; 0 <= relative roughness <= 0.05",
        phase_range=_SINGLE_PHASE,
        validation_cases=("P04 Haaland equation regression", "P04 R744 0.5 m pipe"),
    )

    def supports(
        self,
        reynolds_number: float,
        relative_roughness: float,
        phase_regime: str,
    ) -> bool:
        return (
            phase_regime in self.metadata.phase_range
            and 4000.0 <= reynolds_number <= 1.0e8
            and 0.0 <= relative_roughness <= 0.05
        )

    def evaluate(self, reynolds_number: float, relative_roughness: float) -> float:
        if not self.supports(reynolds_number, relative_roughness, "single_phase"):
            raise InfeasibleDesignError("Haaland friction correlation is outside its range")
        inverse_sqrt = -1.8 * math.log10((relative_roughness / 3.7) ** 1.11 + 6.9 / reynolds_number)
        friction_factor = inverse_sqrt**-2
        if not math.isfinite(friction_factor) or friction_factor <= 0.0:
            raise InfeasibleDesignError("Haaland friction factor must be finite and positive")
        return friction_factor


SINGLE_PHASE_FRICTION_REGISTRY = CorrelationRegistry(
    (LaminarDarcyFrictionFactor(), HaalandDarcyFrictionFactor())
)
