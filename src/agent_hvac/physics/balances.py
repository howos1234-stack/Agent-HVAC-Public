"""Independent conservation checks for thermodynamic cycle results."""

import math
from collections.abc import Sequence

from agent_hvac.utils.exceptions import ConvergenceError

ENERGY_BALANCE_TOLERANCE = 1e-10
MASS_BALANCE_TOLERANCE = 1e-12
_MINIMUM_SCALE = 1e-30


def energy_balance_residual(
    *,
    heat_rejection_w: float,
    evaporator_capacity_w: float,
    compressor_power_w: float,
) -> float:
    """Return the normalized first-law closure error."""
    values = (heat_rejection_w, evaporator_capacity_w, compressor_power_w)
    if not all(math.isfinite(value) for value in values):
        raise ConvergenceError("energy balance inputs must be finite")
    scale = max(abs(heat_rejection_w), 1.0)
    return abs(heat_rejection_w - evaporator_capacity_w - compressor_power_w) / scale


def mass_balance_residual(mass_flows_kg_s: Sequence[float]) -> float:
    """Return the relative spread among component mass-flow values."""
    if not mass_flows_kg_s:
        raise ConvergenceError("mass balance requires at least one mass-flow value")
    if not all(math.isfinite(value) for value in mass_flows_kg_s):
        raise ConvergenceError("mass balance inputs must be finite")
    highest = max(mass_flows_kg_s)
    lowest = min(mass_flows_kg_s)
    scale = max(abs(highest), _MINIMUM_SCALE)
    return (highest - lowest) / scale


def require_balances_within_tolerance(
    energy_error: float,
    mass_error: float,
    *,
    energy_tolerance: float = ENERGY_BALANCE_TOLERANCE,
    mass_tolerance: float = MASS_BALANCE_TOLERANCE,
) -> None:
    """Reject results that do not independently close conservation balances."""
    if not all(
        math.isfinite(value) and value >= 0
        for value in (energy_error, mass_error, energy_tolerance, mass_tolerance)
    ):
        raise ConvergenceError("balance residuals and tolerances must be finite and nonnegative")
    if energy_error > energy_tolerance:
        raise ConvergenceError(
            f"energy balance residual {energy_error:.6g} exceeds {energy_tolerance:.6g}"
        )
    if mass_error > mass_tolerance:
        raise ConvergenceError(
            f"mass balance residual {mass_error:.6g} exceeds {mass_tolerance:.6g}"
        )
