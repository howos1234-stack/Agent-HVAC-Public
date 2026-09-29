"""Apply approved expansion-valve product maps without replacing isenthalpic expansion."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

import pint

from agent_hvac.components.performance_map import (
    MapEvaluation,
    OperatingEnvelope2D,
    PerformanceMapError,
    RegularGridMap,
    evaluate_regular_grid,
    require_envelope_contains,
)
from agent_hvac.components.product_adapter import (
    adapt_product_operating_envelope,
    adapt_product_performance_map,
)
from agent_hvac.properties.base import PropertyBackend
from agent_hvac.schemas.components import (
    CanonicalValueName,
    ComponentType,
    OperatingEnvelope,
    PerformanceMap,
    PerformanceMapKind,
    ProductRecord,
)
from agent_hvac.utils.units import Pressure, Quantity, Temperature

_UNITS: pint.UnitRegistry[float] = pint.UnitRegistry()
_SUPPORTED_INLET_PHASES = frozenset(
    {"gas", "liquid", "supercritical", "supercritical_gas", "supercritical_liquid"}
)


@dataclass(frozen=True)
class ExpansionValveMapInput:
    """One unit-bearing valve operating point and explicit product record IDs."""

    backend: PropertyBackend
    product: ProductRecord
    map_id: str
    envelope_id: str
    conditions: Mapping[str, Quantity]


@dataclass(frozen=True)
class ExpansionValveMapResult:
    """Valve map outputs and source identities used by the deterministic calculation."""

    model_path: Literal["PERFORMANCE_MAP"]
    product_id: str
    is_mock: bool
    map_id: str
    envelope_id: str
    inlet_phase: str
    conditions_si: Mapping[str, float]
    condition_units: Mapping[str, str]
    outputs: Mapping[str, float]
    output_units: Mapping[str, str]
    map_source_ids: tuple[str, ...]
    map_axis_source_ids: tuple[str, ...]
    map_fixed_condition_source_ids: Mapping[str, str]
    point_source_ids: tuple[str, ...]
    output_source_ids: Mapping[str, tuple[str, ...]]
    envelope_source_ids: tuple[str, ...]
    envelope_axis_source_ids: tuple[str, ...]
    envelope_fixed_condition_source_ids: Mapping[str, str]
    envelope_vertex_source_ids: tuple[str, ...]


def evaluate_expansion_valve_map(data: ExpansionValveMapInput) -> ExpansionValveMapResult:
    """Evaluate an eligible valve map inside its approved operating envelope.

    The inlet P-T state is validated with the configured property backend before map
    evaluation. The function does not calculate an outlet state, request saturation APIs,
    convert capacity to mass flow, extrapolate, clamp, or fall back to isenthalpic expansion.
    """
    product = data.product
    if product.component_type != ComponentType.EXPANSION_VALVE:
        raise PerformanceMapError(
            "expansion-valve map application requires an expansion-valve product"
        )

    performance_map = _performance_map(product, data.map_id)
    envelope = _operating_envelope(product, data.envelope_id)
    if performance_map.map_kind != PerformanceMapKind.EXPANSION_VALVE:
        raise PerformanceMapError("selected performance map is not an expansion-valve map")
    if performance_map.refrigerant != envelope.refrigerant:
        raise PerformanceMapError("valve map and operating envelope refrigerants differ")

    calculation_map = adapt_product_performance_map(product, data.map_id)
    calculation_envelope = adapt_product_operating_envelope(product, data.envelope_id)
    map_axis_names = tuple(axis.name for axis in calculation_map.axes)
    map_fixed_names = tuple(condition.name for condition in calculation_map.fixed_conditions)
    envelope_axis_names = (
        calculation_envelope.x_axis_name,
        calculation_envelope.y_axis_name,
    )
    envelope_fixed_names = tuple(
        condition.name for condition in calculation_envelope.fixed_conditions
    )
    expected_names = set(
        map_axis_names + map_fixed_names + envelope_axis_names + envelope_fixed_names
    )
    if set(data.conditions) != expected_names:
        raise PerformanceMapError(
            f"valve operating conditions must be exactly {sorted(expected_names)!r}"
        )
    expected_units = _expected_units(calculation_map, calculation_envelope)
    conditions_si = _canonical_conditions(data.conditions, expected_units)
    _validate_physical_conditions(conditions_si)

    inlet_pressure = conditions_si[CanonicalValueName.INLET_PRESSURE.value]
    outlet_pressure = conditions_si[CanonicalValueName.OUTLET_PRESSURE.value]
    inlet_temperature = conditions_si[CanonicalValueName.INLET_TEMPERATURE.value]
    if inlet_pressure <= 0.0 or outlet_pressure <= 0.0:
        raise PerformanceMapError("valve pressures must be positive absolute pressures")
    if inlet_pressure <= outlet_pressure:
        raise PerformanceMapError("valve inlet pressure must exceed outlet pressure")

    inlet_state = data.backend.state_pt(
        performance_map.refrigerant,
        Pressure(value=inlet_pressure, unit="Pa"),
        Temperature(value=inlet_temperature, unit="K"),
    )
    if inlet_state.phase not in _SUPPORTED_INLET_PHASES:
        raise PerformanceMapError(
            "valve inlet P-T state must be single-phase or supercritical; "
            f"received phase {inlet_state.phase!r}"
        )

    map_query = {name: conditions_si[name] for name in map_axis_names}
    map_fixed = {name: conditions_si[name] for name in map_fixed_names}
    envelope_fixed = {name: conditions_si[name] for name in envelope_fixed_names}
    require_envelope_contains(
        calculation_envelope,
        conditions_si[calculation_envelope.x_axis_name],
        conditions_si[calculation_envelope.y_axis_name],
        envelope_fixed,
    )
    evaluation = evaluate_regular_grid(calculation_map, map_query, map_fixed)
    _validate_valve_outputs(evaluation)

    return ExpansionValveMapResult(
        model_path="PERFORMANCE_MAP",
        product_id=product.product_id,
        is_mock=product.is_mock,
        map_id=evaluation.map_id,
        envelope_id=calculation_envelope.envelope_id,
        inlet_phase=inlet_state.phase,
        conditions_si=MappingProxyType(dict(conditions_si)),
        condition_units=MappingProxyType(dict(expected_units)),
        outputs=MappingProxyType(dict(evaluation.outputs)),
        output_units=MappingProxyType(dict(evaluation.output_units)),
        map_source_ids=evaluation.map_source_ids,
        map_axis_source_ids=tuple(axis.source_id for axis in performance_map.axes),
        map_fixed_condition_source_ids=MappingProxyType(
            {
                condition.canonical_name.value: condition.source_id
                for condition in performance_map.fixed_conditions
            }
        ),
        point_source_ids=evaluation.point_source_ids,
        output_source_ids=MappingProxyType(dict(evaluation.output_source_ids)),
        envelope_source_ids=calculation_envelope.source_ids,
        envelope_axis_source_ids=tuple(axis.source_id for axis in envelope.axes),
        envelope_fixed_condition_source_ids=MappingProxyType(
            {
                condition.canonical_name.value: condition.source_id
                for condition in envelope.fixed_conditions
            }
        ),
        envelope_vertex_source_ids=tuple(
            sorted({vertex.source_id for vertex in envelope.boundary_vertices})
        ),
    )


def _expected_units(
    calculation_map: RegularGridMap, calculation_envelope: OperatingEnvelope2D
) -> dict[str, str]:
    units: dict[str, str] = {}

    def register(name: str, unit: str) -> None:
        existing = units.get(name)
        if existing is not None and existing != unit:
            raise PerformanceMapError(
                f"condition {name!r} has inconsistent canonical units {existing!r} and {unit!r}"
            )
        units[name] = unit

    for axis in calculation_map.axes:
        register(axis.name, axis.unit)
    for condition in calculation_map.fixed_conditions:
        register(condition.name, condition.unit)
    register(calculation_envelope.x_axis_name, calculation_envelope.x_unit)
    register(calculation_envelope.y_axis_name, calculation_envelope.y_unit)
    for condition in calculation_envelope.fixed_conditions:
        register(condition.name, condition.unit)
    return units


def _canonical_conditions(
    actual: Mapping[str, Quantity], expected_units: Mapping[str, str]
) -> dict[str, float]:
    converted: dict[str, float] = {}
    for name, expected_unit in expected_units.items():
        value = actual[name]
        try:
            magnitude = float(_UNITS.Quantity(value.value, value.unit).to(expected_unit).magnitude)
        except (pint.errors.PintError, TypeError, ValueError) as exc:
            raise PerformanceMapError(
                f"condition {name!r} is incompatible with canonical unit {expected_unit!r}"
            ) from exc
        if not math.isfinite(magnitude):
            raise PerformanceMapError("valve operating conditions must be finite")
        converted[name] = magnitude
    return converted


def _validate_physical_conditions(conditions_si: Mapping[str, float]) -> None:
    inlet_temperature = conditions_si[CanonicalValueName.INLET_TEMPERATURE.value]
    if inlet_temperature <= 0.0:
        raise PerformanceMapError("valve inlet_temperature must be above absolute zero (0 K)")
    opening = conditions_si[CanonicalValueName.OPENING.value]
    if not 0.0 <= opening <= 1.0:
        raise PerformanceMapError("valve opening must be within the closed interval [0, 1]")


def _validate_valve_outputs(evaluation: MapEvaluation) -> None:
    outputs = evaluation.outputs
    units = evaluation.output_units
    if CanonicalValueName.INPUT_POWER.value in outputs:
        raise PerformanceMapError("expansion-valve map must not provide input_power")
    flow_name = CanonicalValueName.MASS_FLOW.value
    capacity_name = CanonicalValueName.COOLING_CAPACITY.value
    if flow_name not in outputs and capacity_name not in outputs:
        raise PerformanceMapError("expansion-valve map must provide mass_flow or cooling_capacity")
    if flow_name in outputs and (units.get(flow_name) != "kg/s" or outputs[flow_name] <= 0.0):
        raise PerformanceMapError("expansion-valve map mass_flow must be positive in 'kg/s'")
    if capacity_name in outputs and (
        units.get(capacity_name) != "W" or outputs[capacity_name] <= 0.0
    ):
        raise PerformanceMapError("expansion-valve map cooling_capacity must be positive in 'W'")


def _performance_map(product: ProductRecord, map_id: str) -> PerformanceMap:
    for performance_map in product.performance_maps:
        if performance_map.map_id == map_id:
            return performance_map
    raise PerformanceMapError(f"product does not contain map {map_id!r}")


def _operating_envelope(product: ProductRecord, envelope_id: str) -> OperatingEnvelope:
    for envelope in product.operating_envelopes:
        if envelope.envelope_id == envelope_id:
            return envelope
    raise PerformanceMapError(f"product does not contain operating envelope {envelope_id!r}")
