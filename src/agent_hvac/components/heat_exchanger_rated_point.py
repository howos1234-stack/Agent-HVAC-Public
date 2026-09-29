"""Connect one explicitly selected HX rated point to the P05 constant-UA model."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import pint

from agent_hvac.components.heat_exchanger_1d import (
    HeatExchanger1DInput,
    HeatExchanger1DResult,
    HeatExchangerMode,
    SpecificHeatCapacity,
    ThermalConductance,
    evaluate_heat_exchanger_1d,
)
from agent_hvac.physics.state import ThermoState
from agent_hvac.properties.base import PropertyBackend
from agent_hvac.schemas.components import (
    AutomaticSelectionStatus,
    CanonicalValueName,
    ComponentType,
    OperatingMode,
    ProductDataValue,
    ProductRecord,
    ProductTopology,
    RatedPoint,
)
from agent_hvac.utils.exceptions import InfeasibleDesignError
from agent_hvac.utils.units import MassFlow, PressureDifference, Quantity, Temperature

_UNITS: pint.UnitRegistry[float] = pint.UnitRegistry()
_HX_COMPONENT_MODES = {
    ComponentType.EVAPORATOR: HeatExchangerMode.EVAPORATOR,
    ComponentType.CONDENSER: HeatExchangerMode.CONDENSER,
    ComponentType.GAS_COOLER: HeatExchangerMode.GAS_COOLER,
}
_REQUIRED_REFRIGERANT_CONDITIONS = frozenset(
    {
        CanonicalValueName.INLET_PRESSURE.value,
        CanonicalValueName.INLET_TEMPERATURE.value,
        CanonicalValueName.MASS_FLOW.value,
    }
)


class HeatExchangerRatedPointError(InfeasibleDesignError):
    """Selected product data cannot be applied to the requested P05 calculation."""


@dataclass(frozen=True)
class HeatExchangerRatedPointSelection:
    """Explicit rated-point identity and its requested applicability conditions."""

    product: ProductRecord
    rated_point_id: str
    refrigerant: str
    topology: ProductTopology
    operating_mode: OperatingMode
    conditions: Mapping[str, Quantity]


@dataclass(frozen=True)
class HeatExchangerBoundaryInput:
    """Caller-owned P05 boundary values not supplied by the product rated point."""

    refrigerant_inlet_state: ThermoState
    refrigerant_mass_flow: MassFlow
    secondary_inlet_temperature: Temperature
    secondary_mass_flow: MassFlow
    secondary_specific_heat_capacity: SpecificHeatCapacity
    cell_count: int


@dataclass(frozen=True)
class RatedValueTrace:
    """Canonical value plus the product-data identities that supplied it."""

    value_id: str
    canonical_name: str
    original_name: str
    original_value: float
    original_unit: str
    value: float
    unit: str
    source_id: str


@dataclass(frozen=True)
class HeatExchangerRatedPointView:
    """Validated product values used by, or reported beside, the P05 calculation."""

    product_id: str
    rated_point_id: str
    refrigerant: str
    topology: ProductTopology
    operating_mode: OperatingMode
    heat_exchanger_mode: HeatExchangerMode
    total_thermal_conductance: ThermalConductance
    refrigerant_pressure_drop: PressureDifference
    rated_conditions: tuple[RatedValueTrace, ...]
    rated_outputs: tuple[RatedValueTrace, ...]
    rated_point_source_id: str
    is_mock: bool


@dataclass(frozen=True)
class HeatExchangerRatedPointResult:
    """P05 prediction kept separate from the selected product's rated outputs."""

    model_path: Literal["RATED_POINT_CONSTANT_UA"]
    rated_data: HeatExchangerRatedPointView
    calculation: HeatExchanger1DResult


def select_heat_exchanger_rated_point(
    request: HeatExchangerRatedPointSelection,
) -> HeatExchangerRatedPointView:
    """Validate and expose one exact HX rated point without interpolation or inference."""
    product = request.product
    try:
        hx_mode = _HX_COMPONENT_MODES[product.component_type]
    except KeyError as exc:
        raise HeatExchangerRatedPointError(
            "rated-point constant-UA application requires an evaporator, condenser, or "
            "gas-cooler product"
        ) from exc

    rated_point = _rated_point(product, request.rated_point_id)
    if rated_point.use_status.automatic_selection != AutomaticSelectionStatus.ELIGIBLE:
        raise HeatExchangerRatedPointError(
            f"rated point {request.rated_point_id!r} is not eligible for calculation"
        )
    if rated_point.refrigerant != request.refrigerant:
        raise HeatExchangerRatedPointError("rated-point refrigerant does not match the request")
    if request.refrigerant not in product.supported_refrigerants:
        raise HeatExchangerRatedPointError("requested refrigerant is not supported by the product")
    if rated_point.topology != request.topology:
        raise HeatExchangerRatedPointError("rated-point topology does not match the request")
    if rated_point.mode != request.operating_mode:
        raise HeatExchangerRatedPointError("rated-point operating mode does not match the request")

    expected_conditions = {value.canonical_name.value: value for value in rated_point.conditions}
    missing_conditions = _REQUIRED_REFRIGERANT_CONDITIONS - expected_conditions.keys()
    if missing_conditions:
        raise HeatExchangerRatedPointError(
            "rated point lacks required refrigerant applicability conditions "
            f"{sorted(missing_conditions)!r}"
        )
    if set(request.conditions) != set(expected_conditions):
        raise HeatExchangerRatedPointError(
            f"rated-point conditions must be supplied exactly as {sorted(expected_conditions)!r}"
        )
    for name, expected in expected_conditions.items():
        actual = _convert_condition(request.conditions[name], expected.value_si.unit, name)
        if not _same_value(actual, expected.value_si.value):
            raise HeatExchangerRatedPointError(
                f"rated-point condition {name!r} does not exactly match the selected point"
            )

    outputs = {value.canonical_name: value for value in rated_point.outputs}
    ua = _required_output(outputs, CanonicalValueName.UA, request.rated_point_id)
    pressure_drop = _required_output(
        outputs,
        CanonicalValueName.REFRIGERANT_PRESSURE_DROP,
        request.rated_point_id,
    )
    if ua.value_si.unit != "W/K" or ua.value_si.value <= 0.0:
        raise HeatExchangerRatedPointError(
            "rated-point ua must be finite and positive in canonical unit 'W/K'"
        )
    if pressure_drop.value_si.unit != "Pa" or pressure_drop.value_si.value < 0.0:
        raise HeatExchangerRatedPointError(
            "rated-point refrigerant_pressure_drop must be nonnegative in canonical unit 'Pa'"
        )

    _require_source_references(product, rated_point)
    return HeatExchangerRatedPointView(
        product_id=product.product_id,
        rated_point_id=rated_point.rated_point_id,
        refrigerant=rated_point.refrigerant,
        topology=rated_point.topology,
        operating_mode=rated_point.mode,
        heat_exchanger_mode=hx_mode,
        total_thermal_conductance=ThermalConductance(value=ua.value_si.value, unit="W/K"),
        refrigerant_pressure_drop=PressureDifference(
            value=pressure_drop.value_si.value,
            unit="Pa",
        ),
        rated_conditions=tuple(_trace(value) for value in rated_point.conditions),
        rated_outputs=tuple(_trace(value) for value in rated_point.outputs),
        rated_point_source_id=rated_point.source_id,
        is_mock=product.is_mock,
    )


def evaluate_heat_exchanger_rated_point(
    backend: PropertyBackend,
    rated_data: HeatExchangerRatedPointView,
    boundaries: HeatExchangerBoundaryInput,
) -> HeatExchangerRatedPointResult:
    """Call the unchanged P05 model with product UA/drop and caller-owned boundaries."""
    inlet = boundaries.refrigerant_inlet_state
    if inlet.fluid != rated_data.refrigerant:
        raise HeatExchangerRatedPointError(
            "P05 refrigerant inlet state does not match the selected rated point"
        )
    _require_boundaries_match_rated_point(rated_data, boundaries)
    calculation = evaluate_heat_exchanger_1d(
        backend,
        HeatExchanger1DInput(
            mode=rated_data.heat_exchanger_mode,
            refrigerant_inlet_state=inlet,
            refrigerant_mass_flow=boundaries.refrigerant_mass_flow,
            secondary_inlet_temperature=boundaries.secondary_inlet_temperature,
            secondary_mass_flow=boundaries.secondary_mass_flow,
            secondary_specific_heat_capacity=boundaries.secondary_specific_heat_capacity,
            total_thermal_conductance=rated_data.total_thermal_conductance,
            refrigerant_pressure_drop=rated_data.refrigerant_pressure_drop,
            cell_count=boundaries.cell_count,
        ),
    )
    return HeatExchangerRatedPointResult(
        model_path="RATED_POINT_CONSTANT_UA",
        rated_data=rated_data,
        calculation=calculation,
    )


def _rated_point(product: ProductRecord, rated_point_id: str) -> RatedPoint:
    for rated_point in product.rated_points:
        if rated_point.rated_point_id == rated_point_id:
            return rated_point
    raise HeatExchangerRatedPointError(f"product does not contain rated point {rated_point_id!r}")


def _required_output(
    outputs: Mapping[CanonicalValueName, ProductDataValue],
    name: CanonicalValueName,
    rated_point_id: str,
) -> ProductDataValue:
    try:
        return outputs[name]
    except KeyError as exc:
        raise HeatExchangerRatedPointError(
            f"rated point {rated_point_id!r} is missing required output {name.value!r}"
        ) from exc


def _convert_condition(value: Quantity, unit: str, name: str) -> float:
    try:
        converted = float(_UNITS.Quantity(value.value, value.unit).to(unit).magnitude)
    except (pint.errors.PintError, TypeError, ValueError) as exc:
        raise HeatExchangerRatedPointError(
            f"rated-point condition {name!r} is incompatible with canonical unit {unit!r}"
        ) from exc
    if not math.isfinite(converted):
        raise HeatExchangerRatedPointError("rated-point conditions must be finite")
    return converted


def _same_value(actual: float, expected: float) -> bool:
    """Treat only unit-conversion roundoff as equal, not an applicability tolerance."""
    return actual == expected or math.isclose(actual, expected, rel_tol=1.0e-12, abs_tol=0.0)


def _trace(value: ProductDataValue) -> RatedValueTrace:
    return RatedValueTrace(
        value_id=value.value_id,
        canonical_name=value.canonical_name.value,
        original_name=value.original_name,
        original_value=value.original_value,
        original_unit=value.original_unit,
        value=value.value_si.value,
        unit=value.value_si.unit,
        source_id=value.source_id,
    )


def _require_source_references(product: ProductRecord, rated_point: RatedPoint) -> None:
    """Defend the calculation boundary even if a caller bypassed model validation."""
    source_ids = {source.source_id for source in product.data_sources}
    if rated_point.source_id not in source_ids:
        raise HeatExchangerRatedPointError("rated point has an unresolved source_id")
    for value in rated_point.conditions + rated_point.outputs:
        if value.source_id not in source_ids:
            raise HeatExchangerRatedPointError(
                f"rated-point value {value.value_id!r} has an unresolved source_id"
            )


def _require_boundaries_match_rated_point(
    rated_data: HeatExchangerRatedPointView,
    boundaries: HeatExchangerBoundaryInput,
) -> None:
    """Tie unambiguous refrigerant-side rated conditions to the actual P05 inputs."""
    conditions = {value.canonical_name: value for value in rated_data.rated_conditions}
    actual = {
        CanonicalValueName.INLET_PRESSURE.value: boundaries.refrigerant_inlet_state.pressure.value,
        CanonicalValueName.INLET_TEMPERATURE.value: (
            boundaries.refrigerant_inlet_state.temperature.value
        ),
        CanonicalValueName.MASS_FLOW.value: boundaries.refrigerant_mass_flow.value,
    }
    for name, actual_value in actual.items():
        expected = conditions[name]
        if not _same_value(actual_value, expected.value):
            raise HeatExchangerRatedPointError(
                f"P05 boundary {name!r} does not match the selected rated point"
            )
