"""One explicit circuit traversal using unchanged P02/P05 component models."""

import math

from agent_hvac.components.compressor import evaluate_compressor
from agent_hvac.components.expansion_valve import evaluate_expansion_valve
from agent_hvac.components.heat_exchanger_1d import (
    HeatExchanger1DInput,
    HeatExchangerMode,
    evaluate_heat_exchanger_1d,
)
from agent_hvac.physics.state import ThermoState
from agent_hvac.properties.base import PropertyBackend
from agent_hvac.solvers.system_cycle.models import (
    CircuitResult,
    CircuitStatus,
    ComponentTrace,
    LoopDiagnostics,
    SignedPressure,
    SyntheticScenario,
)
from agent_hvac.utils.exceptions import (
    ConvergenceError,
    InfeasibleDesignError,
    InvalidPropertyStateError,
)
from agent_hvac.utils.units import (
    Power,
    PressureDifference,
    SpecificEnthalpy,
    TemperatureDifference,
)

# Roundoff audit of already evaluated component transfers, not a loop convergence limit.
# Matches the order of P02's energy-balance audit; P05 retains its own tighter checks.
_TRANSFER_RELATIVE_TOLERANCE = 1e-10


def _finite(value: float, context: str) -> float:
    if not math.isfinite(value):
        raise ConvergenceError(f"{context} is non-finite")
    return value


def _audit(actual: float, expected: float, floor: float, context: str) -> None:
    difference = _finite(actual - expected, context)
    if abs(difference) / max(abs(actual), abs(expected), floor) > _TRANSFER_RELATIVE_TOLERANCE:
        raise ConvergenceError(f"{context} violated: actual={actual}, expected={expected}")


def evaluate_circuit(
    backend: PropertyBackend,
    scenario: SyntheticScenario,
    *,
    trial_suction_enthalpy: SpecificEnthalpy | None = None,
) -> CircuitResult:
    """Evaluate a trial once. Even zero loop residual never means solver convergence.

    Positive Q and W enter the refrigerant. For this zero-loss single traversal,
    W + Q_gc + Q_ev = m_dot * (h_return - h_trial). Report both the actual loop
    imbalance and this transfer audit; do not force the return state to the trial.
    """
    scenario = SyntheticScenario.model_validate(scenario.model_dump(mode="json"))
    if scenario.network is not None:
        from agent_hvac.solvers.system_cycle.network import evaluate_network

        return evaluate_network(backend, scenario, trial_suction_enthalpy)
    nodes: dict[str, ThermoState] = {}
    traces: list[ComponentTrace] = []
    mass = scenario.refrigerant_mass_flow.value
    stage = "suction"

    def record(name: str, state: ThermoState, pressure: float) -> None:
        if state.fluid != scenario.refrigerant:
            raise InvalidPropertyStateError(f"{name}: property backend changed refrigerant")
        _audit(state.pressure.value, pressure, 1.0, f"{name} pressure [Pa]")
        nodes[name] = state

    def trace(name: str, outlet: str, heat: float, work: float, path: str) -> ComponentTrace:
        inlet_name = {"compressor": "suction_trial", "valve": f"{scenario.high_side_name}_outlet"}[
            name
        ]
        transfer = _finite(heat + work, f"{name} transfer [W]")
        delta = _finite(
            mass * (nodes[outlet].enthalpy.value - nodes[inlet_name].enthalpy.value),
            f"{name} enthalpy transfer [W]",
        )
        _audit(transfer, delta, 1.0, f"{name} energy [W]")
        return ComponentTrace(
            component="compressor" if name == "compressor" else "valve",
            model_path=path,
            inlet_node=inlet_name,
            outlet_node=outlet,
            refrigerant_mass_flow=scenario.refrigerant_mass_flow,
            heat_to_refrigerant=Power(value=heat, unit="W"),
            work_to_refrigerant=Power(value=work, unit="W"),
        )

    try:
        if trial_suction_enthalpy is None:
            suction = backend.state_pt(
                scenario.refrigerant, scenario.suction_pressure, scenario.trial_suction_temperature
            )
            _audit(
                suction.temperature.value,
                scenario.trial_suction_temperature.value,
                1.0,
                "suction trial temperature [K]",
            )
        else:
            trial_suction_enthalpy = SpecificEnthalpy.model_validate(
                trial_suction_enthalpy.model_dump(mode="json")
            )
            suction = backend.state_ph(
                scenario.refrigerant, scenario.suction_pressure, trial_suction_enthalpy
            )
            _audit(
                suction.enthalpy.value,
                trial_suction_enthalpy.value,
                1.0,
                "suction trial enthalpy [J/kg]",
            )
        record("suction_trial", suction, scenario.suction_pressure.value)
        stage = "compressor"
        compressor = evaluate_compressor(
            backend,
            suction,
            scenario.discharge_pressure,
            scenario.compressor_isentropic_efficiency.value,
        )
        record("compressor_outlet", compressor.outlet, scenario.discharge_pressure.value)
        power = _finite(mass * compressor.specific_work_j_kg, "compressor power [W]")
        traces.append(trace(stage, "compressor_outlet", 0.0, power, compressor.model_path))

        for name, config, mode, inlet_name, outlet_name, pressure in (
            (
                scenario.high_side_name,
                scenario.high_side_hx,
                HeatExchangerMode(scenario.high_side_name),
                "compressor_outlet",
                f"{scenario.high_side_name}_outlet",
                scenario.discharge_pressure,
            ),
            (
                "evaporator",
                scenario.evaporator,
                HeatExchangerMode.EVAPORATOR,
                "valve_outlet",
                "suction_return",
                scenario.suction_pressure,
            ),
        ):
            stage = name
            hx = evaluate_heat_exchanger_1d(
                backend,
                HeatExchanger1DInput(
                    mode=mode,
                    refrigerant_inlet_state=nodes[inlet_name],
                    refrigerant_mass_flow=scenario.refrigerant_mass_flow,
                    secondary_inlet_temperature=config.secondary_inlet_temperature,
                    secondary_mass_flow=config.secondary_mass_flow,
                    secondary_specific_heat_capacity=config.secondary_specific_heat_capacity,
                    total_thermal_conductance=config.total_thermal_conductance,
                    refrigerant_pressure_drop=PressureDifference(value=0.0, unit="Pa"),
                    cell_count=config.cell_count,
                ),
            )
            record(outlet_name, hx.refrigerant_outlet_state, pressure.value)
            _audit(
                hx.total_heat_to_refrigerant.value,
                _finite(
                    mass * (nodes[outlet_name].enthalpy.value - nodes[inlet_name].enthalpy.value),
                    f"{name} enthalpy transfer [W]",
                ),
                1.0,
                f"{name} energy [W]",
            )
            traces.append(
                ComponentTrace(
                    component=scenario.high_side_name
                    if name == scenario.high_side_name
                    else "evaporator",
                    model_path="CONSTANT_UA_CO_CURRENT",
                    inlet_node=inlet_name,
                    outlet_node=outlet_name,
                    refrigerant_mass_flow=scenario.refrigerant_mass_flow,
                    heat_to_refrigerant=hx.total_heat_to_refrigerant,
                    work_to_refrigerant=Power(value=0.0, unit="W"),
                    heat_exchanger=hx,
                )
            )
            if name == scenario.high_side_name:
                stage = "valve"
                valve = evaluate_expansion_valve(
                    backend, nodes[outlet_name], scenario.suction_pressure
                )
                record("valve_outlet", valve, scenario.suction_pressure.value)
                traces.append(trace(stage, "valve_outlet", 0.0, 0.0, "ISENTHALPIC"))

        stage = "diagnostics"
        returned = nodes["suction_return"]
        dh = _finite(returned.enthalpy.value - suction.enthalpy.value, "loop enthalpy [J/kg]")
        net = _finite(
            sum(t.heat_to_refrigerant.value + t.work_to_refrigerant.value for t in traces),
            "net heat and work [W]",
        )
        transport = _finite(mass * dh, "transported enthalpy [W]")
        audit_error = _finite(net - transport, "transfer error [W]")
        scale = max(1.0, *(abs(t.heat_to_refrigerant.value) for t in traces), abs(power))
        relative = abs(audit_error) / scale
        if relative > _TRANSFER_RELATIVE_TOLERANCE:
            raise ConvergenceError("whole-traversal energy transfer audit failed")
        diagnostics = LoopDiagnostics(
            enthalpy_return_minus_trial=SpecificEnthalpy(value=dh, unit="J/kg"),
            pressure_return_minus_trial=SignedPressure(
                value=returned.pressure.value - suction.pressure.value, unit="Pa"
            ),
            temperature_return_minus_trial=TemperatureDifference(
                value=returned.temperature.value - suction.temperature.value, unit="K"
            ),
            net_heat_and_work_to_refrigerant=Power(value=net, unit="W"),
            transported_enthalpy_difference=Power(value=transport, unit="W"),
            transport_energy_error=Power(value=audit_error, unit="W"),
            relative_transport_energy_error=relative,
            compressor_power=Power(value=power, unit="W"),
            evaporator_heat=traces[3].heat_to_refrigerant,
            **{
                f"{scenario.high_side_name}_heat_rejection": Power(
                    value=-traces[1].heat_to_refrigerant.value, unit="W"
                )
            },
        )
        return CircuitResult(
            scenario=scenario,
            trial_suction_enthalpy=trial_suction_enthalpy,
            status="evaluated",
            nodes=nodes,
            components=tuple(traces),
            diagnostics=diagnostics,
            message="Single traversal evaluated; loop not solved. No system COP reported.",
        )
    except (InvalidPropertyStateError, InfeasibleDesignError, ConvergenceError) as exc:
        status: CircuitStatus = (
            "invalid-property-state"
            if isinstance(exc, InvalidPropertyStateError)
            else "infeasible"
            if isinstance(exc, InfeasibleDesignError)
            else "component-numerical-failure"
        )
        return CircuitResult(
            scenario=scenario,
            trial_suction_enthalpy=trial_suction_enthalpy,
            status=status,
            nodes=nodes,
            components=tuple(traces),
            failed_stage=stage,
            message=str(exc),
        )
