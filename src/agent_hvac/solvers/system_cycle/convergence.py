"""Bounded enthalpy root search around the existing single-pass circuit."""

import math

from agent_hvac.components.compressor import evaluate_compressor
from agent_hvac.properties.base import PropertyBackend
from agent_hvac.solvers.system_cycle.convergence_models import (
    ConvergenceRequest,
    ConvergenceResult,
    CyclePerformance,
    IterationSample,
)
from agent_hvac.solvers.system_cycle.harness import evaluate_circuit
from agent_hvac.solvers.system_cycle.models import CircuitResult
from agent_hvac.utils.exceptions import (
    ConvergenceError,
    InfeasibleDesignError,
    InvalidPropertyStateError,
)
from agent_hvac.utils.units import SpecificEnthalpy


def _closure(
    backend: PropertyBackend, request: ConvergenceRequest, circuit: CircuitResult
) -> tuple[CyclePerformance | None, str]:
    """Recompute whole-cycle conservation from component traces, not a root flag."""
    start, returned = circuit.nodes["suction_trial"], circuit.nodes["suction_return"]
    settings = request.settings
    if abs(returned.enthalpy.value - start.enthalpy.value) > settings.enthalpy_tolerance.value:
        return None, "enthalpy residual exceeded tolerance"
    if abs(returned.pressure.value - start.pressure.value) > settings.pressure_tolerance.value:
        return None, "pressure residual exceeded tolerance"
    if (
        abs(returned.temperature.value - start.temperature.value)
        > settings.temperature_tolerance.value
    ):
        return None, "temperature residual exceeded tolerance"
    if start.fluid != request.scenario.refrigerant or returned.fluid != start.fluid:
        return None, "refrigerant identity changed"
    traces = circuit.components
    expected = ["compressor", request.scenario.high_side_name, "valve", "evaporator"]
    if request.scenario.network is not None:
        expected = [
            "compressor",
            "discharge_pipe",
            request.scenario.high_side_name,
            "high_side_pipe",
            "valve",
            "evaporator",
            "suction_pipe",
        ]
    if [t.component for t in traces] != expected:
        return None, "component order changed"
    mass_values = [request.scenario.refrigerant_mass_flow.value]
    mass_values.extend(t.refrigerant_mass_flow.value for t in traces)
    mass_values.extend(
        t.heat_exchanger.refrigerant_mass_flow.value for t in traces if t.heat_exchanger is not None
    )
    mass_values.extend(t.pipe.mass_flow.value for t in traces if t.pipe is not None)
    mass_error = (max(mass_values) - min(mass_values)) / max(mass_values)
    try:
        net = math.fsum(t.heat_to_refrigerant.value + t.work_to_refrigerant.value for t in traces)
    except OverflowError:
        return None, "whole-cycle energy sum overflowed"
    scale = max(
        1.0,
        *(abs(t.heat_to_refrigerant.value) for t in traces),
        *(abs(t.work_to_refrigerant.value) for t in traces),
    )
    energy_error = abs(net) / scale
    if not math.isfinite(energy_error) or energy_error > settings.relative_energy_tolerance:
        return None, "whole-cycle energy residual exceeded tolerance"
    if mass_error > settings.relative_mass_tolerance:
        return None, "whole-cycle mass residual exceeded tolerance"
    by_name = {t.component: t for t in traces}
    work = by_name["compressor"].work_to_refrigerant.value
    heat = by_name["evaporator"].heat_to_refrigerant.value
    rejection = -by_name[request.scenario.high_side_name].heat_to_refrigerant.value
    if min(work, heat, rejection) <= 0:
        return None, "cooling cycle requires positive work, cooling and heat rejection"
    cop = heat / work
    if not math.isfinite(cop):
        return None, "cooling COP is non-finite"
    # Check that the returned state can actually feed the same compressor again.
    try:
        evaluate_compressor(
            backend,
            returned,
            request.scenario.discharge_pressure,
            request.scenario.compressor_isentropic_efficiency.value,
        )
    except (InfeasibleDesignError, InvalidPropertyStateError, ConvergenceError) as exc:
        return None, f"return state cannot feed compressor: {exc}"
    return CyclePerformance(
        cooling_cop=cop, relative_energy_error=energy_error, relative_mass_error=mass_error
    ), "all closure checks passed"


def solve_circuit(backend: PropertyBackend, request: ConvergenceRequest) -> ConvergenceResult:
    """Find the first sampled valid bracket, then bisect without domain bridging.

    The finite scan does not prove global absence/uniqueness of a root. An invalid
    midpoint terminates this search; it is never removed to invent continuity.
    Width alone is not a convergence criterion. No temperature or outlet state is
    overwritten. The scenario's S1 trial temperature is not a fixed S2 boundary.
    """
    request = ConvergenceRequest.model_validate(request.model_dump(mode="json"))
    settings = request.settings
    history: list[IterationSample] = []
    last: CircuitResult | None = None
    iterations = 0

    def finish(
        reason: str, message: str, performance: CyclePerformance | None = None
    ) -> ConvergenceResult:
        return ConvergenceResult(
            request=request,
            cycle_converged=performance is not None,
            status="converged" if performance is not None else "unconverged",
            reason=reason,
            message=message,
            bisection_iterations=iterations,
            history=tuple(history),
            last_evaluation=last,
            performance=performance,
        )

    def sample(enthalpy: float, *, bisect: bool) -> float | None:
        nonlocal last
        trial = SpecificEnthalpy(value=enthalpy, unit="J/kg")
        last = evaluate_circuit(backend, request.scenario, trial_suction_enthalpy=trial)
        residual = (
            last.nodes["suction_return"].enthalpy.value - last.nodes["suction_trial"].enthalpy.value
            if last.status == "evaluated"
            else None
        )
        history.append(
            IterationSample(
                pressure_history=last.pressure_history,
                evaluation=len(history) + 1,
                phase="bisection" if bisect else "scan",
                trial_enthalpy=trial,
                status=last.status,
                residual=SpecificEnthalpy(value=residual, unit="J/kg")
                if residual is not None
                else None,
                failed_stage=last.failed_stage,
                message=last.message,
            )
        )
        return residual

    def accept(residual: float) -> ConvergenceResult | None:
        assert last is not None
        performance, message = _closure(backend, request, last)
        if (
            performance is None
            and residual != 0
            and message
            in {
                "temperature residual exceeded tolerance",
                "whole-cycle energy residual exceeded tolerance",
            }
        ):
            return None  # Continue refining until every tolerance passes.
        return finish(
            "closure-satisfied" if performance else "closure-check-failed", message, performance
        )

    previous: tuple[float, float] | None = None
    bracket: tuple[float, float, float] | None = None
    lower, upper = settings.lower_enthalpy.value, settings.upper_enthalpy.value
    for index in range(settings.scan_intervals + 1):
        h = lower + (upper - lower) * (index / settings.scan_intervals)
        residual = sample(h, bisect=False)
        if residual is None:
            previous = None
            continue
        if abs(residual) <= settings.enthalpy_tolerance.value:
            accepted = accept(residual)
            if accepted is not None:
                return accepted
        if previous is not None and ((previous[1] < 0) != (residual < 0)):
            bracket = previous[0], h, previous[1]
            break
        previous = h, residual
    if bracket is None:
        reason = (
            "no-valid-evaluations" if all(s.residual is None for s in history) else "no-bracket"
        )
        return finish(
            reason,
            "No adjacent valid sign-changing samples in the specified bounds; "
            "this does not prove that no physical root exists.",
        )

    lo, hi, rlo = bracket
    for step in range(1, settings.max_iterations + 1):
        iterations = step
        mid = lo + (hi - lo) / 2.0
        if mid == lo or mid == hi:
            return finish(
                "floating-point-stagnation", "Bracket cannot be reduced at float precision."
            )
        residual = sample(mid, bisect=True)
        if residual is None:
            assert last is not None
            return finish("invalid-domain-in-bracket", f"{last.failed_stage}: {last.message}")
        if abs(residual) <= settings.enthalpy_tolerance.value:
            accepted = accept(residual)
            if accepted is not None:
                return accepted
        if (rlo < 0) == (residual < 0):
            lo, rlo = mid, residual
        else:
            hi = mid
    return finish(
        "max-iterations", "Iteration budget exhausted without satisfying closure tolerances."
    )
