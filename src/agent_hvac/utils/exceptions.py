"""Service exceptions; adapters translate them to explicit structured outcomes."""


class HVACError(Exception):
    """Base exception for deterministic services."""


class InvalidPropertyStateError(HVACError):
    """Requested state is outside the property backend's valid domain."""


class ConvergenceError(HVACError):
    """Numerical iteration did not converge."""


class InfeasibleDesignError(HVACError):
    """No design satisfies hard constraints."""


class ComponentEnvelopeError(HVACError):
    """Operating point lies outside the documented product envelope."""


class DatabaseValidationError(HVACError):
    """Workbook or source metadata failed validation."""
