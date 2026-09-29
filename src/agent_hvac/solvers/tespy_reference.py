"""Independent TESPy network path for P03 cross-validation of the P02 cycle."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, ClassVar

from tespy.components import (  # type: ignore[import-untyped]
    Compressor,
    CycleCloser,
    SimpleHeatExchanger,
    Valve,
)
from tespy.connections import Connection  # type: ignore[import-untyped]
from tespy.networks import Network  # type: ignore[import-untyped]

from agent_hvac.physics.balances import energy_balance_residual, mass_balance_residual
from agent_hvac.physics.cycle import (
    BaselineCycleInputs,
    BaselineCycleSolution,
    solve_baseline_cycle,
)
from agent_hvac.properties.coolprop_backend import CoolPropBackend
from agent_hvac.utils.exceptions import HVACError, InfeasibleDesignError

P03_RELATIVE_TOLERANCE = 1e-7
_STATE_NAMES = (
    "compressor_inlet",
    "compressor_outlet",
    "heat_rejection_outlet",
    "expansion_valve_outlet",
)
_ABSOLUTE_TOLERANCES = {
    "T": 1e-6,
    "p": 1e-3,
    "h": 1e-3,
    "m": 1e-12,
    "compressor_power": 1e-3,
    "evaporator_capacity": 1e-3,
    "heat_rejection": 1e-3,
    "cop": 1e-9,
    "energy_balance_error": 1e-10,
    "mass_balance_error": 1e-12,
}


class TespyCrossValidationError(HVACError):
    """The independent reference path could not produce a comparable finite result."""


@dataclass(frozen=True)
class TespyStatePoint:
    temperature_k: float
    pressure_pa: float
    enthalpy_j_kg: float
    mass_flow_kg_s: float


@dataclass(frozen=True)
class TespyCycleResult:
    converged: bool
    state_points: dict[str, TespyStatePoint]
    compressor_power_w: float
    evaporator_capacity_w: float
    heat_rejection_w: float
    cop: float
    energy_balance_error: float
    mass_balance_error: float


@dataclass(frozen=True)
class ComparisonMetric:
    p02_value: float
    tespy_value: float
    absolute_error: float
    relative_error: float
    allowed_error: float
    within_tolerance: bool


@dataclass(frozen=True)
class TespyCrossValidationReport:
    state_names: ClassVar[tuple[str, ...]] = _STATE_NAMES
    p02: BaselineCycleSolution
    tespy: TespyCycleResult
    metrics: dict[str, ComparisonMetric]

    @property
    def all_within_tolerance(self) -> bool:
        return all(metric.within_tolerance for metric in self.metrics.values())

    @property
    def max_relative_error(self) -> float:
        # Balance residuals are expected near zero and use absolute tolerances;
        # a relative error against a zero baseline is not a meaningful summary.
        return max(
            metric.relative_error
            for name, metric in self.metrics.items()
            if name not in {"energy_balance_error", "mass_balance_error"}
        )


def _finite(name: str, raw: Any) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise TespyCrossValidationError(f"TESPy {name} must be numeric") from exc
    if not math.isfinite(value):
        raise TespyCrossValidationError(f"TESPy {name} must be finite")
    return value


def _positive(name: str, value: float) -> float:
    if value <= 0.0:
        raise TespyCrossValidationError(f"TESPy {name} must be positive")
    return value


def solve_tespy_reference(inputs: BaselineCycleInputs) -> TespyCycleResult:
    """Solve the frozen P03 R744 case with an independent TESPy network."""
    if inputs.fluid != "R744":
        raise InfeasibleDesignError("P03 TESPy reference currently supports R744 only")
    if inputs.high_side_pressure.value <= inputs.evaporator_pressure.value:
        raise InfeasibleDesignError("high_side_pressure must exceed evaporator_pressure")
    if not 0.0 < inputs.compressor_isentropic_efficiency <= 1.0:
        raise InfeasibleDesignError("compressor isentropic efficiency must be in (0, 1]")

    network = Network(iterinfo=False)
    closer = CycleCloser("cycle closer")
    compressor = Compressor("compressor")
    heat_rejection = SimpleHeatExchanger("heat rejection")
    valve = Valve("expansion valve")
    evaporator = SimpleHeatExchanger("evaporator")

    closer_inlet = Connection(evaporator, "out1", closer, "in1", label="cycle closer inlet")
    state_1 = Connection(closer, "out1", compressor, "in1", label="compressor inlet")
    state_2 = Connection(compressor, "out1", heat_rejection, "in1", label="compressor outlet")
    state_3 = Connection(
        heat_rejection,
        "out1",
        valve,
        "in1",
        label="heat rejection outlet",
    )
    state_4 = Connection(valve, "out1", evaporator, "in1", label="expansion valve outlet")
    network.add_conns(closer_inlet, state_1, state_2, state_3, state_4)

    compressor.set_attr(eta_s=inputs.compressor_isentropic_efficiency)
    heat_rejection.set_attr(pr=1.0)
    evaporator.set_attr(pr=1.0)
    state_1.set_attr(
        fluid={inputs.fluid: 1.0},
        p=inputs.evaporator_pressure.value,
        T=inputs.compressor_inlet_temperature.value,
        m=inputs.refrigerant_mass_flow.value,
    )
    state_3.set_attr(
        p=inputs.high_side_pressure.value,
        T=inputs.heat_rejection_outlet_temperature.value,
    )

    try:
        network.solve("design", print_results=False)
    except (RuntimeError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise TespyCrossValidationError(f"TESPy solve failed: {exc}") from exc
    if not network.converged:
        raise TespyCrossValidationError("TESPy network did not converge")

    connections = dict(zip(_STATE_NAMES, (state_1, state_2, state_3, state_4), strict=True))
    states = {
        name: TespyStatePoint(
            temperature_k=_finite(f"{name} temperature", connection.T.val),
            pressure_pa=_finite(f"{name} pressure", connection.p.val),
            enthalpy_j_kg=_finite(f"{name} enthalpy", connection.h.val),
            mass_flow_kg_s=_finite(f"{name} mass flow", connection.m.val),
        )
        for name, connection in connections.items()
    }
    compressor_power = _positive("compressor power", _finite("compressor power", compressor.P.val))
    evaporator_capacity = _positive(
        "evaporator capacity",
        _finite("evaporator capacity", evaporator.Q.val),
    )
    # TESPy Q is positive into a component. The high-side exchanger rejects heat,
    # so the P02 positive heat-rejection convention requires this explicit sign change.
    rejected_heat = _positive(
        "heat rejection",
        -_finite("heat-rejection component heat", heat_rejection.Q.val),
    )
    cop = _positive("COP", _finite("COP", evaporator_capacity / compressor_power))
    state_mass_flows = tuple(state.mass_flow_kg_s for state in states.values())
    return TespyCycleResult(
        converged=True,
        state_points=states,
        compressor_power_w=compressor_power,
        evaporator_capacity_w=evaporator_capacity,
        heat_rejection_w=rejected_heat,
        cop=cop,
        energy_balance_error=energy_balance_residual(
            heat_rejection_w=rejected_heat,
            evaporator_capacity_w=evaporator_capacity,
            compressor_power_w=compressor_power,
        ),
        mass_balance_error=mass_balance_residual(state_mass_flows),
    )


def _metric(
    name: str,
    p02_value: float,
    tespy_value: float,
    absolute_tolerance: float,
) -> tuple[str, ComparisonMetric]:
    p02_finite = _finite(f"P02 {name}", p02_value)
    tespy_finite = _finite(name, tespy_value)
    absolute_error = abs(p02_finite - tespy_finite)
    scale = max(abs(p02_finite), abs(tespy_finite))
    relative_error = absolute_error / scale if scale else 0.0
    allowed_error = max(absolute_tolerance, P03_RELATIVE_TOLERANCE * scale)
    return name, ComparisonMetric(
        p02_value=p02_finite,
        tespy_value=tespy_finite,
        absolute_error=absolute_error,
        relative_error=relative_error,
        allowed_error=allowed_error,
        within_tolerance=absolute_error <= allowed_error,
    )


def compare_cycle_results(
    p02: BaselineCycleSolution,
    tespy: TespyCycleResult,
) -> TespyCrossValidationReport:
    """Compare every Master Plan V4 metric against pre-frozen tolerances."""
    if not tespy.converged:
        raise TespyCrossValidationError("TESPy comparison requires a converged result")
    metrics: dict[str, ComparisonMetric] = {}
    for state_name in _STATE_NAMES:
        p02_state = p02.state_points[state_name]
        tespy_state = tespy.state_points[state_name]
        state_values = {
            "T": (p02_state.temperature.value, tespy_state.temperature_k),
            "p": (p02_state.pressure.value, tespy_state.pressure_pa),
            "h": (p02_state.enthalpy.value, tespy_state.enthalpy_j_kg),
            "m": (p02.mass_flow_kg_s, tespy_state.mass_flow_kg_s),
        }
        for field, (p02_value, tespy_value) in state_values.items():
            metric_name, metric = _metric(
                f"{state_name}.{field}",
                p02_value,
                tespy_value,
                _ABSOLUTE_TOLERANCES[field],
            )
            metrics[metric_name] = metric

    result_values = {
        "compressor_power": (p02.compressor_power_w, tespy.compressor_power_w),
        "evaporator_capacity": (p02.evaporator_capacity_w, tespy.evaporator_capacity_w),
        "heat_rejection": (p02.heat_rejection_w, tespy.heat_rejection_w),
        "cop": (p02.cop, tespy.cop),
        "energy_balance_error": (p02.energy_balance_error, tespy.energy_balance_error),
        "mass_balance_error": (p02.mass_balance_error, tespy.mass_balance_error),
    }
    for name, (p02_value, tespy_value) in result_values.items():
        metric_name, metric = _metric(
            name,
            p02_value,
            tespy_value,
            _ABSOLUTE_TOLERANCES[name],
        )
        metrics[metric_name] = metric
    return TespyCrossValidationReport(p02=p02, tespy=tespy, metrics=metrics)


def run_p03_cross_validation(inputs: BaselineCycleInputs) -> TespyCrossValidationReport:
    """Run P02 and the independent TESPy network under identical inputs."""
    p02 = solve_baseline_cycle(CoolPropBackend(), inputs)
    tespy = solve_tespy_reference(inputs)
    return compare_cycle_results(p02, tespy)
