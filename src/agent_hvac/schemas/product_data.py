"""ProductRecord 0.2.0 detailed product-data contract."""

from __future__ import annotations

import itertools
import math
from enum import StrEnum
from fractions import Fraction
from typing import Annotated, Literal, Self

import pint
from pydantic import AwareDatetime, Field, model_validator

from agent_hvac.schemas.base import ContractModel, NonEmptyStr
from agent_hvac.schemas.provenance import Parameter
from agent_hvac.utils.units import Quantity

RecordId = Annotated[
    str,
    Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"),
]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

_UNITS: pint.UnitRegistry[float] = pint.UnitRegistry()


class ComponentType(StrEnum):
    COMPRESSOR = "compressor"
    EVAPORATOR = "evaporator"
    CONDENSER = "condenser"
    GAS_COOLER = "gas_cooler"
    EXPANSION_VALVE = "expansion_valve"
    PIPE = "pipe"
    FAN = "fan"
    PUMP = "pump"
    RECEIVER = "receiver"
    ACCUMULATOR = "accumulator"
    IHX = "ihx"


class DataOrigin(StrEnum):
    MANUFACTURER = "MANUFACTURER"
    TEST_STANDARD = "TEST_STANDARD"
    PHYSICS_DERIVED = "PHYSICS_DERIVED"


class AxisRole(StrEnum):
    CANONICAL = "CANONICAL"
    NATIVE_ONLY = "NATIVE_ONLY"


class AutomaticSelectionStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"


class UseRestrictionReason(StrEnum):
    NATIVE_TEMPERATURE_AXIS_ONLY = "NATIVE_TEMPERATURE_AXIS_ONLY"
    SUCTION_TEMPERATURE_MISSING = "SUCTION_TEMPERATURE_MISSING"
    INLET_TEMPERATURE_MISSING = "INLET_TEMPERATURE_MISSING"
    OPENING_CONDITION_MISSING = "OPENING_CONDITION_MISSING"
    SUPERHEAT_ONLY = "SUPERHEAT_ONLY"
    INCOMPLETE_REGULAR_GRID = "INCOMPLETE_REGULAR_GRID"
    UNSUPPORTED_REFRIGERANT = "UNSUPPORTED_REFRIGERANT"
    UNAPPROVED_ALIAS = "UNAPPROVED_ALIAS"
    REQUIRED_OUTPUT_MISSING = "REQUIRED_OUTPUT_MISSING"
    UA_NOT_AVAILABLE = "UA_NOT_AVAILABLE"
    UNAPPROVED_TOPOLOGY = "UNAPPROVED_TOPOLOGY"
    UNSUPPORTED_AXIS = "UNSUPPORTED_AXIS"
    COMPONENT_MAP_KIND_MISMATCH = "COMPONENT_MAP_KIND_MISMATCH"
    INVALID_FLASHING_INLET_STATE = "INVALID_FLASHING_INLET_STATE"


class InterpolationPolicy(StrEnum):
    LINEAR = "LINEAR"
    MULTILINEAR = "MULTILINEAR"


class PerformanceMapKind(StrEnum):
    COMPRESSOR = "COMPRESSOR"
    EXPANSION_VALVE = "EXPANSION_VALVE"


class ProductTopology(StrEnum):
    R744_TRANSCRITICAL = "R744_TRANSCRITICAL"
    SUBCRITICAL = "SUBCRITICAL"
    OTHER_NATIVE_ONLY = "OTHER_NATIVE_ONLY"


class OperatingMode(StrEnum):
    COOLING = "COOLING"
    HEATING = "HEATING"
    OTHER_NATIVE_ONLY = "OTHER_NATIVE_ONLY"


class AxisPhysicalKind(StrEnum):
    PRESSURE = "PRESSURE"
    TEMPERATURE = "TEMPERATURE"
    ROTATIONAL_SPEED = "ROTATIONAL_SPEED"
    FREQUENCY = "FREQUENCY"
    OPENING_FRACTION = "OPENING_FRACTION"


class CanonicalAxisName(StrEnum):
    SUCTION_PRESSURE = "suction_pressure"
    DISCHARGE_PRESSURE = "discharge_pressure"
    SPEED = "speed"
    FREQUENCY = "frequency"
    INLET_PRESSURE = "inlet_pressure"
    OUTLET_PRESSURE = "outlet_pressure"
    OPENING = "opening"


class CanonicalValueName(StrEnum):
    SUCTION_PRESSURE = "suction_pressure"
    DISCHARGE_PRESSURE = "discharge_pressure"
    SUCTION_TEMPERATURE = "suction_temperature"
    GAS_COOLER_OUTLET_TEMPERATURE = "gas_cooler_outlet_temperature"
    GAS_COOLER_OUTLET_ENTHALPY = "gas_cooler_outlet_enthalpy"
    SPEED = "speed"
    FREQUENCY = "frequency"
    INPUT_POWER = "input_power"
    MASS_FLOW = "mass_flow"
    COOLING_CAPACITY = "cooling_capacity"
    HEATING_CAPACITY = "heating_capacity"
    DISCHARGE_TEMPERATURE = "discharge_temperature"
    ISENTROPIC_EFFICIENCY = "isentropic_efficiency"
    VOLUMETRIC_EFFICIENCY = "volumetric_efficiency"
    UA = "ua"
    MAXIMUM_WORKING_PRESSURE = "maximum_working_pressure"
    INLET_PRESSURE = "inlet_pressure"
    OUTLET_PRESSURE = "outlet_pressure"
    INLET_TEMPERATURE = "inlet_temperature"
    OPENING = "opening"
    KV = "kv"
    CV = "cv"
    HEAT_REJECTION = "heat_rejection"
    REFRIGERANT_PRESSURE_DROP = "refrigerant_pressure_drop"
    SECONDARY_PRESSURE_DROP = "secondary_pressure_drop"
    AIR_VOLUME_FLOW = "air_volume_flow"
    FAN_POWER = "fan_power"
    PUMP_POWER = "pump_power"
    INLET_RELATIVE_HUMIDITY = "inlet_relative_humidity"
    OTHER_NATIVE_ONLY = "other_native_only"


class ToleranceKind(StrEnum):
    ABSOLUTE = "ABSOLUTE"
    RELATIVE = "RELATIVE"
    PERCENT = "PERCENT"


class ToleranceReference(StrEnum):
    MEASURED_VALUE = "MEASURED_VALUE"
    RATED_VALUE = "RATED_VALUE"
    FULL_SCALE = "FULL_SCALE"


class ToleranceAbsenceReason(StrEnum):
    NOT_STATED_IN_SOURCE = "NOT_STATED_IN_SOURCE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class AccuracyValidationStatus(StrEnum):
    VERIFIABLE = "VERIFIABLE"
    NOT_VERIFIABLE = "NOT_VERIFIABLE"


_VALUE_UNITS: dict[CanonicalValueName, str] = {
    CanonicalValueName.SUCTION_PRESSURE: "Pa",
    CanonicalValueName.DISCHARGE_PRESSURE: "Pa",
    CanonicalValueName.SUCTION_TEMPERATURE: "K",
    CanonicalValueName.GAS_COOLER_OUTLET_TEMPERATURE: "K",
    CanonicalValueName.GAS_COOLER_OUTLET_ENTHALPY: "J/kg",
    CanonicalValueName.SPEED: "1/s",
    CanonicalValueName.FREQUENCY: "Hz",
    CanonicalValueName.INPUT_POWER: "W",
    CanonicalValueName.MASS_FLOW: "kg/s",
    CanonicalValueName.COOLING_CAPACITY: "W",
    CanonicalValueName.HEATING_CAPACITY: "W",
    CanonicalValueName.DISCHARGE_TEMPERATURE: "K",
    CanonicalValueName.ISENTROPIC_EFFICIENCY: "dimensionless",
    CanonicalValueName.VOLUMETRIC_EFFICIENCY: "dimensionless",
    CanonicalValueName.UA: "W/K",
    CanonicalValueName.MAXIMUM_WORKING_PRESSURE: "Pa",
    CanonicalValueName.INLET_PRESSURE: "Pa",
    CanonicalValueName.OUTLET_PRESSURE: "Pa",
    CanonicalValueName.INLET_TEMPERATURE: "K",
    CanonicalValueName.OPENING: "dimensionless",
    CanonicalValueName.HEAT_REJECTION: "W",
    CanonicalValueName.REFRIGERANT_PRESSURE_DROP: "Pa",
    CanonicalValueName.SECONDARY_PRESSURE_DROP: "Pa",
    CanonicalValueName.AIR_VOLUME_FLOW: "m^3/s",
    CanonicalValueName.FAN_POWER: "W",
    CanonicalValueName.PUMP_POWER: "W",
    CanonicalValueName.INLET_RELATIVE_HUMIDITY: "dimensionless",
}
_AXIS_KINDS = {
    CanonicalAxisName.SUCTION_PRESSURE: AxisPhysicalKind.PRESSURE,
    CanonicalAxisName.DISCHARGE_PRESSURE: AxisPhysicalKind.PRESSURE,
    CanonicalAxisName.SPEED: AxisPhysicalKind.ROTATIONAL_SPEED,
    CanonicalAxisName.FREQUENCY: AxisPhysicalKind.FREQUENCY,
    CanonicalAxisName.INLET_PRESSURE: AxisPhysicalKind.PRESSURE,
    CanonicalAxisName.OUTLET_PRESSURE: AxisPhysicalKind.PRESSURE,
    CanonicalAxisName.OPENING: AxisPhysicalKind.OPENING_FRACTION,
}
_AXIS_VALUES = {name: CanonicalValueName(name.value) for name in CanonicalAxisName}
_AXIS_UNITS = {
    CanonicalAxisName.SUCTION_PRESSURE: "Pa",
    CanonicalAxisName.DISCHARGE_PRESSURE: "Pa",
    CanonicalAxisName.SPEED: "1/s",
    CanonicalAxisName.FREQUENCY: "Hz",
    CanonicalAxisName.INLET_PRESSURE: "Pa",
    CanonicalAxisName.OUTLET_PRESSURE: "Pa",
    CanonicalAxisName.OPENING: "dimensionless",
}


def _converted(value: float, unit: str, target: str) -> float:
    try:
        return float(_UNITS.Quantity(value, unit).to(target).magnitude)
    except (pint.errors.PintError, TypeError, ValueError) as exc:
        raise ValueError(f"unit {unit!r} is incompatible with {target!r}") from exc


def _same(a: float, b: float) -> bool:
    return a == b if a == 0.0 or b == 0.0 else math.isclose(a, b, rel_tol=1e-12, abs_tol=0.0)


def _unique(items: tuple[object, ...], key: str, context: str) -> None:
    values = [getattr(item, key) for item in items]
    if len(values) != len(set(values)):
        raise ValueError(f"{context} contains duplicate {key}")


class DataUseStatus(ContractModel):
    source_preserved: bool
    structure_valid: bool
    automatic_selection: AutomaticSelectionStatus
    reasons: tuple[UseRestrictionReason, ...] = ()

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        if not self.source_preserved or not self.structure_valid:
            raise ValueError(
                "typed detailed records require preserved, structurally valid source data"
            )
        ordered = tuple(reason for reason in UseRestrictionReason if reason in self.reasons)
        object.__setattr__(self, "reasons", ordered)
        if self.automatic_selection == AutomaticSelectionStatus.ELIGIBLE and ordered:
            raise ValueError("ELIGIBLE records cannot have restriction reasons")
        if self.automatic_selection == AutomaticSelectionStatus.INELIGIBLE and not ordered:
            raise ValueError("INELIGIBLE records require at least one restriction reason")
        return self


class ToleranceSpec(ContractModel):
    kind: ToleranceKind
    value: Quantity
    reference: ToleranceReference
    reference_value: Quantity | None = None
    source_id: RecordId

    @model_validator(mode="after")
    def validate_reference(self) -> Self:
        if self.value.value < 0:
            raise ValueError("tolerance value must be nonnegative")
        if self.reference == ToleranceReference.MEASURED_VALUE and self.reference_value is not None:
            raise ValueError("MEASURED_VALUE tolerance forbids reference_value")
        if self.reference != ToleranceReference.MEASURED_VALUE and self.reference_value is None:
            raise ValueError("RATED_VALUE and FULL_SCALE tolerance require reference_value")
        if self.kind in (ToleranceKind.RELATIVE, ToleranceKind.PERCENT):
            _converted(self.value.value, self.value.unit, "dimensionless")
        return self


class ToleranceInfo(ContractModel):
    value: ToleranceSpec | None = None
    absence_reason: ToleranceAbsenceReason | None = None
    accuracy_validation: AccuracyValidationStatus

    @model_validator(mode="after")
    def validate_choice(self) -> Self:
        if (self.value is None) == (self.absence_reason is None):
            raise ValueError("exactly one of tolerance value or absence_reason is required")
        expected = (
            AccuracyValidationStatus.VERIFIABLE
            if self.value is not None
            else AccuracyValidationStatus.NOT_VERIFIABLE
        )
        if self.accuracy_validation != expected:
            raise ValueError("accuracy_validation disagrees with tolerance availability")
        return self


class ProductDataValue(ContractModel):
    value_id: RecordId
    canonical_name: CanonicalValueName
    original_name: NonEmptyStr
    original_value: float
    original_unit: NonEmptyStr
    value_si: Quantity
    source_id: RecordId
    tolerance: ToleranceInfo

    @model_validator(mode="before")
    @classmethod
    def validate_value_si_input_unit(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        raw_name = data.get("canonical_name")
        if not isinstance(raw_name, str):
            return data
        try:
            canonical_name = CanonicalValueName(raw_name)
        except ValueError:
            return data
        expected = _VALUE_UNITS.get(canonical_name)
        value_si = data.get("value_si")
        if expected is not None:
            if isinstance(value_si, dict) and value_si.get("unit") != expected:
                raise ValueError(f"value_si.unit must be the approved SI unit {expected!r}")
            if isinstance(value_si, Quantity):
                converted = _converted(value_si.value, value_si.unit, expected)
                if not _same(converted, value_si.value):
                    raise ValueError(
                        "value_si Quantity must already use the approved SI magnitude "
                        f"for {expected!r}"
                    )
        return data

    @model_validator(mode="after")
    def validate_units(self) -> Self:
        expected = _VALUE_UNITS.get(self.canonical_name)
        if expected is not None:
            converted = _converted(self.original_value, self.original_unit, expected)
            if not _same(converted, self.value_si.value):
                raise ValueError("original value/unit and value_si disagree")
            object.__setattr__(self.value_si, "unit", expected)
            tolerance = self.tolerance.value
            if tolerance is not None and tolerance.kind == ToleranceKind.ABSOLUTE:
                _converted(tolerance.value.value, tolerance.value.unit, expected)
            if tolerance is not None and tolerance.reference_value is not None:
                _converted(
                    tolerance.reference_value.value,
                    tolerance.reference_value.unit,
                    expected,
                )
        else:
            converted = _converted(self.original_value, self.original_unit, self.value_si.unit)
            if not _same(converted, self.value_si.value):
                raise ValueError("original value/unit and value_si disagree")
        if (
            self.canonical_name
            in (
                CanonicalValueName.OPENING,
                CanonicalValueName.ISENTROPIC_EFFICIENCY,
                CanonicalValueName.VOLUMETRIC_EFFICIENCY,
                CanonicalValueName.INLET_RELATIVE_HUMIDITY,
            )
            and not 0.0 <= self.value_si.value <= 1.0
        ):
            raise ValueError(f"{self.canonical_name} must be between 0 and 1")
        return self


class DerivedMethod(ContractModel):
    method_id: RecordId
    method_version: NonEmptyStr
    equation_ref: NonEmptyStr
    input_value_refs: tuple[RecordId, ...] = Field(min_length=1)
    applicable_conditions: tuple[ProductDataValue, ...] = Field(min_length=1)
    assumptions: tuple[NonEmptyStr, ...] = ()


class WorkbookProductDataSource(ContractModel):
    source_id: RecordId
    origin: Literal[DataOrigin.MANUFACTURER, DataOrigin.TEST_STANDARD]
    excel_file: NonEmptyStr
    file_sha256: Sha256
    sheet: NonEmptyStr
    row: int = Field(ge=1)
    document_ref: NonEmptyStr
    table_or_figure_ref: NonEmptyStr | None = None
    original_manufacturer: NonEmptyStr
    original_model: NonEmptyStr


class PhysicsDerivedDataSource(ContractModel):
    source_id: RecordId
    origin: Literal[DataOrigin.PHYSICS_DERIVED]
    derived_method: DerivedMethod


ProductDataSource = Annotated[
    WorkbookProductDataSource | PhysicsDerivedDataSource,
    Field(discriminator="origin"),
]


class RatedPoint(ContractModel):
    rated_point_id: RecordId
    refrigerant: NonEmptyStr
    original_refrigerant_label: NonEmptyStr
    topology: ProductTopology
    mode: OperatingMode
    conditions: tuple[ProductDataValue, ...] = Field(min_length=1)
    outputs: tuple[ProductDataValue, ...] = Field(min_length=1)
    source_id: RecordId
    use_status: DataUseStatus

    @model_validator(mode="after")
    def validate_values(self) -> Self:
        values = self.conditions + self.outputs
        _unique(values, "value_id", "rated point")
        _unique(values, "canonical_name", "rated point")
        return self


class MapAxis(ContractModel):
    axis_id: RecordId
    order: int = Field(ge=0)
    canonical_name: CanonicalAxisName | None
    native_name: NonEmptyStr
    role: AxisRole
    physical_kind: AxisPhysicalKind
    original_unit: NonEmptyStr
    canonical_unit: NonEmptyStr
    original_values: tuple[float, ...] = Field(min_length=2)
    values_si: tuple[float, ...] = Field(min_length=2)
    source_id: RecordId

    @model_validator(mode="after")
    def validate_axis(self) -> Self:
        if len(self.original_values) != len(self.values_si):
            raise ValueError("axis original_values and values_si lengths differ")
        if self.role == AxisRole.CANONICAL and self.canonical_name is None:
            raise ValueError("CANONICAL axis requires canonical_name")
        if self.role == AxisRole.NATIVE_ONLY and self.canonical_name is not None:
            raise ValueError("NATIVE_ONLY axis cannot claim a canonical_name")
        if self.canonical_name is not None:
            if self.physical_kind != _AXIS_KINDS[self.canonical_name]:
                raise ValueError("axis physical_kind disagrees with canonical_name")
            expected = _AXIS_UNITS[self.canonical_name]
            if self.canonical_unit != expected:
                raise ValueError(f"axis canonical_unit must be the approved SI unit {expected!r}")
            converted = tuple(
                _converted(v, self.original_unit, expected) for v in self.original_values
            )
            if not all(_same(a, b) for a, b in zip(converted, self.values_si, strict=True)):
                raise ValueError("axis original_values and values_si disagree")
            if self.canonical_name == CanonicalAxisName.OPENING and any(
                value < 0 or value > 1 for value in self.values_si
            ):
                raise ValueError("opening axis values must be between 0 and 1")
        if not all(a < b for a, b in itertools.pairwise(self.values_si)):
            raise ValueError("axis values_si must be strictly increasing")
        return self

    def canonical_values(self) -> tuple[float, ...]:
        if self.canonical_name is None:
            return self.values_si
        return self.values_si


class PerformancePoint(ContractModel):
    point_id: RecordId
    coordinates: tuple[ProductDataValue, ...] = Field(min_length=1)
    outputs: tuple[ProductDataValue, ...] = Field(min_length=1)
    source_id: RecordId


class PerformanceMap(ContractModel):
    map_id: RecordId
    map_kind: PerformanceMapKind
    refrigerant: NonEmptyStr
    original_refrigerant_label: NonEmptyStr
    topology: ProductTopology
    mode: OperatingMode
    axes: tuple[MapAxis, ...] = Field(min_length=1)
    fixed_conditions: tuple[ProductDataValue, ...] = ()
    output_names: tuple[CanonicalValueName, ...] = Field(min_length=1)
    points: tuple[PerformancePoint, ...] = Field(min_length=1)
    interpolation: InterpolationPolicy
    extrapolation: Literal["FORBIDDEN"] = "FORBIDDEN"
    source_id: RecordId
    use_status: DataUseStatus

    @model_validator(mode="after")
    def validate_map(self) -> Self:
        _unique(self.axes, "axis_id", "performance map")
        _unique(self.axes, "order", "performance map")
        _unique(self.points, "point_id", "performance map")
        _unique(self.fixed_conditions, "value_id", "map fixed conditions")
        _unique(self.fixed_conditions, "canonical_name", "map fixed conditions")
        if sorted(axis.order for axis in self.axes) != list(range(len(self.axes))):
            raise ValueError("axis order must be contiguous from zero")
        axes = tuple(sorted(self.axes, key=lambda axis: axis.order))
        eligible = self.use_status.automatic_selection == AutomaticSelectionStatus.ELIGIBLE
        if eligible:
            if any(axis.role != AxisRole.CANONICAL for axis in axes):
                raise ValueError("ELIGIBLE map requires canonical axes")
            _unique(axes, "canonical_name", "ELIGIBLE performance map")
        if len(self.output_names) != len(set(self.output_names)):
            raise ValueError("output_names contains duplicates")
        coordinate_tuples: list[tuple[float, ...]] = []
        for point in self.points:
            if len(point.coordinates) != len(axes):
                raise ValueError("point coordinate count must match axis count")
            _unique(point.coordinates + point.outputs, "value_id", "performance point")
            output_names = tuple(output.canonical_name for output in point.outputs)
            if set(output_names) != set(self.output_names) or len(output_names) != len(
                set(output_names)
            ):
                raise ValueError("point outputs must exactly match output_names")
            coordinates: list[float] = []
            for coordinate, axis in zip(point.coordinates, axes, strict=True):
                if (
                    axis.canonical_name is not None
                    and coordinate.canonical_name != _AXIS_VALUES[axis.canonical_name]
                ):
                    raise ValueError("point coordinate order/name disagrees with axes")
                value = coordinate.value_si.value
                if not any(_same(value, candidate) for candidate in axis.canonical_values()):
                    raise ValueError("point coordinate is outside declared axis values")
                coordinates.append(value)
            coordinate_tuples.append(tuple(coordinates))
        if len(coordinate_tuples) != len(set(coordinate_tuples)):
            raise ValueError("performance map contains duplicate coordinate tuples")
        if eligible:
            expected = math.prod(len(axis.values_si) for axis in axes)
            if len(self.points) != expected:
                raise ValueError("ELIGIBLE map requires a complete regular grid")
            self._validate_eligible_contract(axes)
        return self

    def _validate_eligible_contract(self, axes: tuple[MapAxis, ...]) -> None:
        axis_names = tuple(axis.canonical_name for axis in axes)
        fixed = {value.canonical_name for value in self.fixed_conditions}
        outputs = set(self.output_names)
        flow_or_capacity = bool(
            outputs & {CanonicalValueName.MASS_FLOW, CanonicalValueName.COOLING_CAPACITY}
        )
        if self.map_kind == PerformanceMapKind.COMPRESSOR:
            permitted_axes = {
                (
                    CanonicalAxisName.SUCTION_PRESSURE,
                    CanonicalAxisName.DISCHARGE_PRESSURE,
                ),
                (
                    CanonicalAxisName.SUCTION_PRESSURE,
                    CanonicalAxisName.DISCHARGE_PRESSURE,
                    CanonicalAxisName.SPEED,
                ),
                (
                    CanonicalAxisName.SUCTION_PRESSURE,
                    CanonicalAxisName.DISCHARGE_PRESSURE,
                    CanonicalAxisName.FREQUENCY,
                ),
            }
            if axis_names not in permitted_axes:
                raise ValueError("COMPRESSOR map has an unsupported canonical axis set or order")
            if CanonicalValueName.SUCTION_TEMPERATURE not in fixed:
                raise ValueError("COMPRESSOR map requires fixed suction_temperature")
            speed_count = sum(
                name in (CanonicalAxisName.SPEED, CanonicalAxisName.FREQUENCY)
                for name in axis_names
            ) + sum(
                name in (CanonicalValueName.SPEED, CanonicalValueName.FREQUENCY) for name in fixed
            )
            if speed_count != 1:
                raise ValueError("COMPRESSOR map requires exactly one speed/frequency condition")
            if CanonicalValueName.INPUT_POWER not in outputs or not flow_or_capacity:
                raise ValueError(
                    "COMPRESSOR map requires input_power and mass_flow/cooling_capacity"
                )
            if (
                CanonicalValueName.COOLING_CAPACITY in outputs
                and self.topology == ProductTopology.R744_TRANSCRITICAL
                and not fixed
                & {
                    CanonicalValueName.GAS_COOLER_OUTLET_TEMPERATURE,
                    CanonicalValueName.GAS_COOLER_OUTLET_ENTHALPY,
                }
            ):
                raise ValueError(
                    "transcritical compressor capacity requires gas-cooler outlet state"
                )
        else:
            permitted_axes = {
                (
                    CanonicalAxisName.INLET_PRESSURE,
                    CanonicalAxisName.OUTLET_PRESSURE,
                ),
                (
                    CanonicalAxisName.INLET_PRESSURE,
                    CanonicalAxisName.OUTLET_PRESSURE,
                    CanonicalAxisName.OPENING,
                ),
            }
            if axis_names not in permitted_axes:
                raise ValueError(
                    "EXPANSION_VALVE map has an unsupported canonical axis set or order"
                )
            if CanonicalValueName.INLET_TEMPERATURE not in fixed:
                raise ValueError("EXPANSION_VALVE map requires fixed inlet_temperature")
            opening_count = (CanonicalAxisName.OPENING in axis_names) + (
                CanonicalValueName.OPENING in fixed
            )
            if opening_count != 1:
                raise ValueError("EXPANSION_VALVE map requires opening in exactly one location")
            if CanonicalValueName.INPUT_POWER in outputs or not flow_or_capacity:
                raise ValueError(
                    "EXPANSION_VALVE map forbids input_power and requires flow/capacity"
                )
            if any(
                point.coordinates[0].value_si.value <= point.coordinates[1].value_si.value
                for point in self.points
            ):
                raise ValueError(
                    "R744 expansion-valve points require inlet_pressure > outlet_pressure"
                )


class EnvelopeVertex(ContractModel):
    vertex_order: int = Field(ge=0)
    coordinates: tuple[ProductDataValue, ProductDataValue]
    source_id: RecordId


def _exact_cross(
    a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]
) -> Fraction:
    ax, ay = (Fraction.from_float(value) for value in a)
    bx, by = (Fraction.from_float(value) for value in b)
    cx, cy = (Fraction.from_float(value) for value in c)
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


def _orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> int:
    cross = _exact_cross(a, b, c)
    return (cross > 0) - (cross < 0)


def _point_on_segment(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]
) -> bool:
    return _exact_cross(start, end, point) == 0 and (
        min(start[0], end[0]) <= point[0] <= max(start[0], end[0])
        and min(start[1], end[1]) <= point[1] <= max(start[1], end[1])
    )


def _segments_intersect(
    a: tuple[float, float], b: tuple[float, float], c: tuple[float, float], d: tuple[float, float]
) -> bool:
    orientations = (
        _orientation(a, b, c),
        _orientation(a, b, d),
        _orientation(c, d, a),
        _orientation(c, d, b),
    )
    if orientations[0] != orientations[1] and orientations[2] != orientations[3]:
        return True
    return (
        (orientations[0] == 0 and _point_on_segment(c, a, b))
        or (orientations[1] == 0 and _point_on_segment(d, a, b))
        or (orientations[2] == 0 and _point_on_segment(a, c, d))
        or (orientations[3] == 0 and _point_on_segment(b, c, d))
    )


class OperatingEnvelope(ContractModel):
    envelope_id: RecordId
    refrigerant: NonEmptyStr
    original_refrigerant_label: NonEmptyStr
    axes: tuple[MapAxis, MapAxis]
    boundary_vertices: tuple[EnvelopeVertex, ...] = Field(min_length=3)
    boundary_inclusive: bool
    fixed_conditions: tuple[ProductDataValue, ...] = ()
    source_id: RecordId
    use_status: DataUseStatus

    @model_validator(mode="after")
    def validate_envelope(self) -> Self:
        _unique(self.axes, "axis_id", "operating envelope")
        if tuple(axis.order for axis in self.axes) != (0, 1):
            raise ValueError("envelope axes must have orders 0 and 1")
        _unique(self.fixed_conditions, "value_id", "envelope fixed conditions")
        _unique(self.fixed_conditions, "canonical_name", "envelope fixed conditions")
        orders = tuple(vertex.vertex_order for vertex in self.boundary_vertices)
        if orders != tuple(range(len(self.boundary_vertices))):
            raise ValueError("vertex_order must be contiguous from zero")
        points: list[tuple[float, float]] = []
        for vertex in self.boundary_vertices:
            _unique(vertex.coordinates, "value_id", "envelope vertex")
            pair: list[float] = []
            for coordinate, axis in zip(vertex.coordinates, self.axes, strict=True):
                if (
                    axis.canonical_name is not None
                    and coordinate.canonical_name != _AXIS_VALUES[axis.canonical_name]
                ):
                    raise ValueError("envelope coordinate order/name disagrees with axes")
                value = coordinate.value_si.value
                if not any(_same(value, candidate) for candidate in axis.canonical_values()):
                    raise ValueError("envelope coordinate is outside declared axis values")
                pair.append(value)
            points.append((pair[0], pair[1]))
        if len(points) != len(set(points)):
            raise ValueError(
                "envelope vertices must be unique and must not repeat the first vertex"
            )
        n = len(points)
        for i in range(n):
            for j in range(i + 1, n):
                if j in (i, i + 1) or (i == 0 and j == n - 1):
                    continue
                if _segments_intersect(
                    points[i], points[(i + 1) % n], points[j], points[(j + 1) % n]
                ):
                    raise ValueError("envelope polygon must be simple")
        origin = points[0]
        area = sum(
            (_exact_cross(origin, points[i], points[i + 1]) for i in range(1, len(points) - 1)),
            start=Fraction(0),
        )
        if area == 0:
            raise ValueError("envelope polygon must have nonzero area")
        if self.use_status.automatic_selection == AutomaticSelectionStatus.ELIGIBLE and any(
            axis.role != AxisRole.CANONICAL for axis in self.axes
        ):
            raise ValueError("ELIGIBLE envelope requires canonical axes")
        return self


class ProductSource(ContractModel):
    excel_file: NonEmptyStr
    sheet: NonEmptyStr
    row: int = Field(ge=1)
    document_ref: NonEmptyStr
    original_manufacturer: NonEmptyStr
    original_model: NonEmptyStr
    workbook_modified_at: AwareDatetime
    retrieved_at: AwareDatetime
    file_sha256: Sha256
    loader_version: NonEmptyStr
    schema_version: NonEmptyStr


class ProductRecord(ContractModel):
    product_id: NonEmptyStr
    component_type: ComponentType
    manufacturer: NonEmptyStr
    model: NonEmptyStr
    supported_refrigerants: tuple[NonEmptyStr, ...] = Field(min_length=1)
    source: ProductSource
    status: str = Field(pattern="^(verified|unverified|deprecated)$")
    attributes: tuple[Parameter, ...] = ()
    rated_conditions: tuple[Parameter, ...] = ()
    operating_limits: tuple[Parameter, ...] = ()
    is_mock: bool
    data_sources: tuple[ProductDataSource, ...] = Field(
        default=(), exclude_if=lambda value: not value
    )
    rated_points: tuple[RatedPoint, ...] = Field(default=(), exclude_if=lambda value: not value)
    performance_maps: tuple[PerformanceMap, ...] = Field(
        default=(), exclude_if=lambda value: not value
    )
    operating_envelopes: tuple[OperatingEnvelope, ...] = Field(
        default=(), exclude_if=lambda value: not value
    )

    @model_validator(mode="after")
    def validate_detailed_contract(self) -> Self:
        _unique(self.data_sources, "source_id", "product")
        _unique(self.rated_points, "rated_point_id", "product")
        _unique(self.performance_maps, "map_id", "product")
        _unique(self.operating_envelopes, "envelope_id", "product")
        source_ids = {source.source_id for source in self.data_sources}
        value_ids: set[str] = set()

        def register(value: ProductDataValue) -> None:
            if value.value_id in value_ids:
                raise ValueError(f"duplicate product-wide value_id: {value.value_id}")
            value_ids.add(value.value_id)
            if value.source_id not in source_ids:
                raise ValueError(f"unresolved value source_id: {value.source_id}")
            if (
                value.tolerance.value is not None
                and value.tolerance.value.source_id not in source_ids
            ):
                raise ValueError("unresolved tolerance source_id")

        for source in self.data_sources:
            if isinstance(source, PhysicsDerivedDataSource):
                for value in source.derived_method.applicable_conditions:
                    register(value)
        for rated in self.rated_points:
            self._validate_parent(rated.refrigerant, rated.source_id, source_ids)
            for value in rated.conditions + rated.outputs:
                register(value)
            self._validate_rated_point(rated)
        for performance_map in self.performance_maps:
            self._validate_parent(
                performance_map.refrigerant, performance_map.source_id, source_ids
            )
            for axis in performance_map.axes:
                if axis.source_id not in source_ids:
                    raise ValueError("unresolved map axis source_id")
            for value in performance_map.fixed_conditions:
                register(value)
            for point in performance_map.points:
                if point.source_id not in source_ids:
                    raise ValueError("unresolved performance point source_id")
                for value in point.coordinates + point.outputs:
                    register(value)
            expected_kind = {
                ComponentType.COMPRESSOR: PerformanceMapKind.COMPRESSOR,
                ComponentType.EXPANSION_VALVE: PerformanceMapKind.EXPANSION_VALVE,
            }.get(self.component_type)
            if expected_kind != performance_map.map_kind:
                raise ValueError("component_type and map_kind disagree")
        for envelope in self.operating_envelopes:
            self._validate_parent(envelope.refrigerant, envelope.source_id, source_ids)
            for axis in envelope.axes:
                if axis.source_id not in source_ids:
                    raise ValueError("unresolved envelope axis source_id")
            for value in envelope.fixed_conditions:
                register(value)
            for vertex in envelope.boundary_vertices:
                if vertex.source_id not in source_ids:
                    raise ValueError("unresolved envelope vertex source_id")
                for value in vertex.coordinates:
                    register(value)
            self._validate_envelope_contract(envelope)
        for source in self.data_sources:
            if isinstance(source, PhysicsDerivedDataSource):
                unresolved = set(source.derived_method.input_value_refs) - value_ids
                if unresolved:
                    raise ValueError(f"unresolved derived input_value_refs: {sorted(unresolved)}")
        return self

    def _validate_parent(self, refrigerant: str, source_id: str, source_ids: set[str]) -> None:
        if refrigerant not in self.supported_refrigerants:
            raise ValueError("detailed record refrigerant is not supported by product")
        if source_id not in source_ids:
            raise ValueError(f"unresolved parent source_id: {source_id}")

    def _validate_rated_point(self, rated: RatedPoint) -> None:
        if (
            self.component_type == ComponentType.COMPRESSOR
            and rated.use_status.automatic_selection == AutomaticSelectionStatus.ELIGIBLE
            and rated.refrigerant == "R744"
            and rated.topology == ProductTopology.R744_TRANSCRITICAL
            and rated.mode == OperatingMode.COOLING
            and CanonicalValueName.COOLING_CAPACITY
            in {output.canonical_name for output in rated.outputs}
        ):
            conditions = {condition.canonical_name for condition in rated.conditions}
            required = {
                CanonicalValueName.SUCTION_PRESSURE,
                CanonicalValueName.DISCHARGE_PRESSURE,
                CanonicalValueName.SUCTION_TEMPERATURE,
            }
            if not required <= conditions or not conditions & {
                CanonicalValueName.GAS_COOLER_OUTLET_TEMPERATURE,
                CanonicalValueName.GAS_COOLER_OUTLET_ENTHALPY,
            }:
                raise ValueError(
                    "eligible R744 compressor capacity rated point lacks required conditions"
                )

    def _validate_envelope_contract(self, envelope: OperatingEnvelope) -> None:
        if envelope.use_status.automatic_selection != AutomaticSelectionStatus.ELIGIBLE:
            return
        axes = tuple(axis.canonical_name for axis in envelope.axes)
        fixed = {value.canonical_name for value in envelope.fixed_conditions}
        if self.component_type == ComponentType.COMPRESSOR:
            if (
                axes
                != (
                    CanonicalAxisName.SUCTION_PRESSURE,
                    CanonicalAxisName.DISCHARGE_PRESSURE,
                )
                or CanonicalValueName.SUCTION_TEMPERATURE not in fixed
            ):
                raise ValueError(
                    "eligible compressor envelope lacks required axes/fixed conditions"
                )
            if len(fixed & {CanonicalValueName.SPEED, CanonicalValueName.FREQUENCY}) != 1:
                raise ValueError(
                    "eligible compressor envelope requires one speed/frequency condition"
                )
        elif self.component_type == ComponentType.EXPANSION_VALVE:
            if (
                axes
                != (
                    CanonicalAxisName.INLET_PRESSURE,
                    CanonicalAxisName.OUTLET_PRESSURE,
                )
                or not {
                    CanonicalValueName.INLET_TEMPERATURE,
                    CanonicalValueName.OPENING,
                }
                <= fixed
            ):
                raise ValueError("eligible valve envelope lacks required axes/fixed conditions")
