"""Seven-component shooting circuit; prescribed compressor pressures and flow."""

import math

from agent_hvac.components.compressor import evaluate_compressor
from agent_hvac.components.expansion_valve import evaluate_expansion_valve
from agent_hvac.components.heat_exchanger_1d import (
    HeatExchanger1DInput,
    HeatExchangerMode,
    evaluate_heat_exchanger_1d,
)
from agent_hvac.components.pipe import Pipe1DInput, Pipe1DResult, evaluate_pipe_1d
from agent_hvac.physics.state import ThermoState
from agent_hvac.properties.base import PropertyBackend
from agent_hvac.solvers.system_cycle.harness import _audit, _finite
from agent_hvac.solvers.system_cycle.models import (
    CircuitResult,
    ComponentTrace,
    LoopDiagnostics,
    PressureSample,
    SignedPressure,
    SyntheticScenario,
)
from agent_hvac.utils.exceptions import (
    ConvergenceError,
    InfeasibleDesignError,
    InvalidPropertyStateError,
)
from agent_hvac.utils.units import Power, Pressure, SpecificEnthalpy, TemperatureDifference


def _audit_pipe_pressure(pipe: Pipe1DResult, inlet: ThermoState) -> None:
    """Check P04's actual marching identity without subtracting two MPa endpoints.

    P04 uses p_next = p_current - dp_cell in binary64. Replaying those same
    subtractions is exact for its pressure trace, including the zero-length case.
    Compare summed cell losses to reported loss on the loss scale with the
    unchanged audit tolerance. No component or closure tolerance is relaxed.
    """
    if pipe.inlet_state != inlet:
        raise ConvergenceError("pipe inlet state differs from connected node")
    pressure = inlet.pressure.value
    for cell in pipe.cells:
        if cell.inlet_state.pressure.value != pressure:
            raise ConvergenceError("pipe pressure cell chain is discontinuous")
        pressure -= cell.pressure_drop.value
        if cell.outlet_state.pressure.value != pressure:
            raise ConvergenceError("pipe pressure cell marching identity violated")
    if pipe.outlet_state.pressure.value != pressure:
        raise ConvergenceError("pipe pressure outlet differs from marched cells")
    _audit(
        math.fsum(cell.pressure_drop.value for cell in pipe.cells),
        pipe.total_pressure_drop.value,
        1.0,
        "pipe cell pressure loss sum",
    )


def traverse_network(
    backend: PropertyBackend,
    scenario: SyntheticScenario,
    h: SpecificEnthalpy | None,
    valve_pressure: Pressure,
) -> CircuitResult:
    """Evaluate actual forward states without forcing return pressure or enthalpy."""
    config = scenario.network
    assert config is not None
    nodes: dict[str, ThermoState] = {}
    traces: list[ComponentTrace] = []
    mass = scenario.refrigerant_mass_flow.value
    stage = "suction"

    def record(name: str, state: ThermoState) -> None:
        if state.fluid != scenario.refrigerant:
            raise InvalidPropertyStateError(f"{name}: backend changed refrigerant")
        nodes[name] = state

    def append(trace: ComponentTrace) -> None:
        delta = mass * (
            nodes[trace.outlet_node].enthalpy.value - nodes[trace.inlet_node].enthalpy.value
        )
        _audit(
            trace.heat_to_refrigerant.value + trace.work_to_refrigerant.value,
            delta,
            1.0,
            f"{trace.component} energy",
        )
        _audit(trace.refrigerant_mass_flow.value, mass, 1e-12, "component mass")
        traces.append(trace)

    try:
        suction = (
            backend.state_ph(scenario.refrigerant, scenario.suction_pressure, h)
            if h is not None
            else backend.state_pt(
                scenario.refrigerant, scenario.suction_pressure, scenario.trial_suction_temperature
            )
        )
        _audit(suction.pressure.value, scenario.suction_pressure.value, 1.0, "suction pressure")
        if h is not None:
            _audit(suction.enthalpy.value, h.value, 1.0, "trial enthalpy")
        else:
            _audit(
                suction.temperature.value,
                scenario.trial_suction_temperature.value,
                1.0,
                "trial temperature",
            )
        record("suction_trial", suction)
        stage = "compressor"
        comp = evaluate_compressor(
            backend,
            suction,
            scenario.discharge_pressure,
            scenario.compressor_isentropic_efficiency.value,
        )
        _audit(
            comp.outlet.pressure.value,
            scenario.discharge_pressure.value,
            1.0,
            "compressor pressure",
        )
        record("compressor_outlet", comp.outlet)
        append(
            ComponentTrace(
                component="compressor",
                model_path=comp.model_path,
                inlet_node="suction_trial",
                outlet_node="compressor_outlet",
                refrigerant_mass_flow=scenario.refrigerant_mass_flow,
                heat_to_refrigerant=Power(value=0, unit="W"),
                work_to_refrigerant=Power(value=mass * comp.specific_work_j_kg, unit="W"),
            )
        )
        current_name = "compressor_outlet"
        for stage, outlet_name in (
            ("discharge_pipe", "discharge_pipe_outlet"),
            (scenario.high_side_name, f"{scenario.high_side_name}_outlet"),
            ("high_side_pipe", "high_side_pipe_outlet"),
            ("valve", "valve_outlet"),
            ("evaporator", "evaporator_outlet"),
            ("suction_pipe", "suction_return"),
        ):
            inlet = nodes[current_name]
            if stage in {"discharge_pipe", "high_side_pipe", "suction_pipe"}:
                pipe_config = {
                    "discharge_pipe": config.discharge_pipe,
                    "high_side_pipe": config.high_side_pipe,
                    "suction_pipe": config.suction_pipe,
                }[stage]
                pipe = evaluate_pipe_1d(
                    backend,
                    Pipe1DInput(
                        inlet_state=inlet,
                        mass_flow=scenario.refrigerant_mass_flow,
                        **pipe_config.model_dump(exclude={"source_ref"}),
                    ),
                )
                record(outlet_name, pipe.outlet_state)
                _audit_pipe_pressure(pipe, inlet)
                append(
                    ComponentTrace(
                        component=(
                            "discharge_pipe"
                            if stage == "discharge_pipe"
                            else "high_side_pipe"
                            if stage == "high_side_pipe"
                            else "suction_pipe"
                        ),
                        model_path="P04_SINGLE_PHASE",
                        inlet_node=current_name,
                        outlet_node=outlet_name,
                        refrigerant_mass_flow=pipe.mass_flow,
                        heat_to_refrigerant=pipe.total_heat_transfer,
                        work_to_refrigerant=Power(value=0, unit="W"),
                        pipe=pipe,
                    )
                )
            elif stage == "valve":
                outlet = evaluate_expansion_valve(backend, inlet, valve_pressure)
                _audit(outlet.pressure.value, valve_pressure.value, 1.0, "valve pressure")
                record(outlet_name, outlet)
                append(
                    ComponentTrace(
                        component="valve",
                        model_path="ISENTHALPIC",
                        inlet_node=current_name,
                        outlet_node=outlet_name,
                        refrigerant_mass_flow=scenario.refrigerant_mass_flow,
                        heat_to_refrigerant=Power(value=0, unit="W"),
                        work_to_refrigerant=Power(value=0, unit="W"),
                    )
                )
            else:
                hx_config = (
                    scenario.high_side_hx
                    if stage == scenario.high_side_name
                    else scenario.evaporator
                )
                dp = (
                    config.high_side_pressure_drop
                    if stage == scenario.high_side_name
                    else config.evaporator_pressure_drop
                )
                hx = evaluate_heat_exchanger_1d(
                    backend,
                    HeatExchanger1DInput(
                        mode=HeatExchangerMode(scenario.high_side_name)
                        if stage == scenario.high_side_name
                        else HeatExchangerMode.EVAPORATOR,
                        refrigerant_inlet_state=inlet,
                        refrigerant_mass_flow=scenario.refrigerant_mass_flow,
                        refrigerant_pressure_drop=dp,
                        **hx_config.model_dump(exclude={"source_ref"}),
                    ),
                )
                record(outlet_name, hx.refrigerant_outlet_state)
                _audit(
                    inlet.pressure.value - hx.refrigerant_outlet_state.pressure.value,
                    dp.value,
                    1.0,
                    f"{stage} pressure drop",
                )
                _audit(hx.refrigerant_mass_flow.value, mass, 1e-12, "HX mass")
                append(
                    ComponentTrace(
                        component=scenario.high_side_name
                        if stage == scenario.high_side_name
                        else "evaporator",
                        model_path="CONSTANT_UA_CO_CURRENT",
                        inlet_node=current_name,
                        outlet_node=outlet_name,
                        refrigerant_mass_flow=hx.refrigerant_mass_flow,
                        heat_to_refrigerant=hx.total_heat_to_refrigerant,
                        work_to_refrigerant=Power(value=0, unit="W"),
                        heat_exchanger=hx,
                    )
                )
            current_name = outlet_name
        stage = "diagnostics"
        returned = nodes["suction_return"]
        dh = _finite(returned.enthalpy.value - suction.enthalpy.value, "enthalpy residual")
        net = _finite(
            math.fsum(t.heat_to_refrigerant.value + t.work_to_refrigerant.value for t in traces),
            "energy sum",
        )
        scale = max(
            1.0,
            *(abs(t.heat_to_refrigerant.value) for t in traces),
            *(abs(t.work_to_refrigerant.value) for t in traces),
        )
        error = _finite(net - mass * dh, "transfer energy")
        if abs(error) / scale > 1e-10:
            raise ConvergenceError("network energy transfer audit failed")
        by_name = {t.component: t for t in traces}
        diagnostics = LoopDiagnostics(
            enthalpy_return_minus_trial=SpecificEnthalpy(value=dh, unit="J/kg"),
            pressure_return_minus_trial=SignedPressure(
                value=returned.pressure.value - suction.pressure.value, unit="Pa"
            ),
            temperature_return_minus_trial=TemperatureDifference(
                value=returned.temperature.value - suction.temperature.value, unit="K"
            ),
            net_heat_and_work_to_refrigerant=Power(value=net, unit="W"),
            transported_enthalpy_difference=Power(value=mass * dh, unit="W"),
            transport_energy_error=Power(value=error, unit="W"),
            relative_transport_energy_error=abs(error) / scale,
            compressor_power=by_name["compressor"].work_to_refrigerant,
            evaporator_heat=by_name["evaporator"].heat_to_refrigerant,
            **{
                f"{scenario.high_side_name}_heat_rejection": Power(
                    value=-by_name[scenario.high_side_name].heat_to_refrigerant.value, unit="W"
                )
            },
        )
        return CircuitResult(
            scenario=scenario,
            trial_suction_enthalpy=h,
            status="evaluated",
            nodes=nodes,
            components=tuple(traces),
            diagnostics=diagnostics,
            message="Seven-component traversal; pressure and enthalpy are not forced closed.",
        )
    except (InvalidPropertyStateError, InfeasibleDesignError, ConvergenceError) as exc:
        return CircuitResult(
            scenario=scenario,
            trial_suction_enthalpy=h,
            status="invalid-property-state"
            if isinstance(exc, InvalidPropertyStateError)
            else "infeasible"
            if isinstance(exc, InfeasibleDesignError)
            else "component-numerical-failure",
            nodes=nodes,
            components=tuple(traces),
            failed_stage=stage,
            message=str(exc),
        )


def evaluate_network(
    backend: PropertyBackend, scenario: SyntheticScenario, h: SpecificEnthalpy | None
) -> CircuitResult:
    """Solve return pressure for one enthalpy trial using a bounded valid bracket."""
    config = scenario.network
    assert config is not None
    history: list[PressureSample] = []
    last: CircuitResult | None = None

    def sample(p: float) -> float | None:
        nonlocal last
        pressure = Pressure(value=p, unit="Pa")
        last = traverse_network(backend, scenario, h, pressure)
        residual = last.diagnostics.pressure_return_minus_trial.value if last.diagnostics else None
        history.append(
            PressureSample(
                trial_valve_pressure=pressure,
                residual=SignedPressure(value=residual, unit="Pa")
                if residual is not None
                else None,
                status=last.status,
                failed_stage=last.failed_stage,
                message=last.message,
            )
        )
        return residual

    def finish(reason: str | None = None) -> CircuitResult:
        assert last is not None
        data = last.model_dump(mode="json")
        data["pressure_history"] = [entry.model_dump(mode="json") for entry in history]
        if reason is not None:
            data.update(
                status="component-numerical-failure",
                diagnostics=None,
                failed_stage="pressure-solve",
                message=reason,
            )
        return CircuitResult.model_validate(data)

    previous: tuple[float, float] | None = None
    bracket: tuple[float, float, float, float] | None = None
    lower, upper = config.valve_pressure_lower.value, config.valve_pressure_upper.value
    for index in range(config.pressure_scan_intervals + 1):
        p = lower + (upper - lower) * (index / config.pressure_scan_intervals)
        residual = sample(p)
        if residual is None:
            previous = None
            continue
        if abs(residual) <= config.pressure_tolerance.value:
            return finish()
        if previous is not None and ((previous[1] < 0) != (residual < 0)):
            bracket = previous[0], p, previous[1], residual
            break
        previous = p, residual
    if bracket is None:
        return finish("pressure-no-valid-bracket; inspect pressure_history for component failures")
    lo, hi, rlo, rhi = bracket
    for step in range(config.pressure_max_iterations):
        # Ratio form avoids multiplying a pressure by a residual. Periodic bisection
        # guarantees contraction even if a valid secant repeatedly hugs an endpoint.
        fraction = abs(rlo) / (abs(rlo) + abs(rhi))
        mid = lo + (hi - lo) * fraction if step % 4 != 3 else lo + (hi - lo) / 2
        if not lo < mid < hi:
            mid = lo + (hi - lo) / 2
        if mid == lo or mid == hi:
            return finish("pressure-floating-point-stagnation")
        residual = sample(mid)
        if residual is None:
            return finish("pressure-invalid-domain-in-bracket; inspect pressure_history")
        if abs(residual) <= config.pressure_tolerance.value:
            return finish()
        if (rlo < 0) == (residual < 0):
            lo, rlo = mid, residual
        else:
            hi, rhi = mid, residual
    return finish("pressure-max-iterations")
