"""Excel schema 0.2.0 detailed-record ingestion and parent quarantine."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import pint
from pydantic import ValidationError

from agent_hvac.schemas.components import (
    AccuracyValidationStatus,
    AutomaticSelectionStatus,
    AxisPhysicalKind,
    AxisRole,
    CanonicalAxisName,
    CanonicalValueName,
    DataOrigin,
    DataUseStatus,
    DerivedMethod,
    EnvelopeVertex,
    InterpolationPolicy,
    MapAxis,
    OperatingEnvelope,
    OperatingMode,
    PerformanceMap,
    PerformanceMapKind,
    PerformancePoint,
    PhysicsDerivedDataSource,
    ProductDataSource,
    ProductDataValue,
    ProductRecord,
    ProductTopology,
    RatedPoint,
    ToleranceAbsenceReason,
    ToleranceInfo,
    ToleranceKind,
    ToleranceReference,
    ToleranceSpec,
    UseRestrictionReason,
    WorkbookProductDataSource,
)
from agent_hvac.utils.exceptions import DatabaseValidationError
from agent_hvac.utils.units import Quantity

SCHEMA_VERSION = "0.2.0"

DATA_SOURCES = "data_sources"
DERIVED_SOURCE_CONDITIONS = "derived_source_conditions"
RATED_POINTS = "rated_points"
RATED_VALUES = "rated_point_values"
PERFORMANCE_MAPS = "performance_maps"
MAP_AXES = "map_axes"
PERFORMANCE_POINTS = "performance_points"
PERFORMANCE_VALUES = "performance_point_values"
MAP_FIXED = "map_fixed_conditions"
OPERATING_ENVELOPES = "operating_envelopes"
ENVELOPE_AXES = "envelope_axes"
ENVELOPE_VERTICES = "envelope_vertices"
ENVELOPE_FIXED = "envelope_fixed_conditions"

CORE_DETAIL_SHEETS = {
    DATA_SOURCES,
    RATED_POINTS,
    RATED_VALUES,
    PERFORMANCE_MAPS,
    MAP_AXES,
    PERFORMANCE_POINTS,
    PERFORMANCE_VALUES,
    OPERATING_ENVELOPES,
    ENVELOPE_AXES,
    ENVELOPE_VERTICES,
}
ALL_DETAIL_SHEETS = CORE_DETAIL_SHEETS | {
    DERIVED_SOURCE_CONDITIONS,
    MAP_FIXED,
    ENVELOPE_FIXED,
}

TOLERANCE_COLUMNS = (
    "tolerance_kind",
    "tolerance_value",
    "tolerance_unit",
    "tolerance_reference",
    "tolerance_reference_value",
    "tolerance_reference_unit",
    "tolerance_source_id",
    "tolerance_absence_reason",
    "accuracy_validation",
)
VALUE_COLUMNS = (
    "value_id",
    "canonical_name",
    "original_name",
    "original_value",
    "original_unit",
    "provided_value_si",
    "provided_canonical_unit",
    *TOLERANCE_COLUMNS,
    "source_id",
)

SOURCE_COLUMNS = (
    "product_id",
    "source_id",
    "origin",
    "document_ref",
    "table_or_figure_ref",
    "original_manufacturer",
    "original_model",
    "method_id",
    "method_version",
    "equation_ref",
    "input_value_refs",
    "assumptions",
)
DERIVED_SOURCE_CONDITION_COLUMNS = ("derived_source_id", *VALUE_COLUMNS)
RATED_PARENT_COLUMNS = (
    "product_id",
    "rated_point_id",
    "refrigerant_label",
    "topology",
    "mode",
    "source_id",
    "automatic_selection",
    "restriction_reasons",
)
RATED_VALUE_COLUMNS = ("rated_point_id", "value_role", *VALUE_COLUMNS)
MAP_PARENT_COLUMNS = (
    "product_id",
    "map_id",
    "map_kind",
    "refrigerant_label",
    "topology",
    "mode",
    "interpolation",
    "extrapolation",
    "source_id",
    "automatic_selection",
    "restriction_reasons",
)
AXIS_COLUMNS = (
    "axis_id",
    "order",
    "canonical_name",
    "native_name",
    "role",
    "physical_kind",
    "original_unit",
    "canonical_unit",
    "source_id",
)
MAP_AXIS_COLUMNS = ("map_id", *AXIS_COLUMNS)
POINT_COLUMNS = ("map_id", "point_id", "source_id")
POINT_VALUE_COLUMNS = ("point_id", "value_role", "axis_id", *VALUE_COLUMNS)
MAP_FIXED_COLUMNS = ("map_id", *VALUE_COLUMNS)
ENVELOPE_PARENT_COLUMNS = (
    "product_id",
    "envelope_id",
    "refrigerant_label",
    "boundary_inclusive",
    "source_id",
    "automatic_selection",
    "restriction_reasons",
)
ENVELOPE_AXIS_COLUMNS = ("envelope_id", *AXIS_COLUMNS)
ENVELOPE_VERTEX_COLUMNS = (
    "envelope_id",
    "vertex_order",
    "axis_id",
    "original_value",
    "original_unit",
    "provided_value_si",
    "provided_canonical_unit",
    "source_id",
)
ENVELOPE_FIXED_COLUMNS = ("envelope_id", *VALUE_COLUMNS)

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
_AXIS_UNITS: dict[CanonicalAxisName, str] = {
    CanonicalAxisName.SUCTION_PRESSURE: "Pa",
    CanonicalAxisName.DISCHARGE_PRESSURE: "Pa",
    CanonicalAxisName.SPEED: "1/s",
    CanonicalAxisName.FREQUENCY: "Hz",
    CanonicalAxisName.INLET_PRESSURE: "Pa",
    CanonicalAxisName.OUTLET_PRESSURE: "Pa",
    CanonicalAxisName.OPENING: "dimensionless",
}
_AXIS_VALUE_NAMES = {axis: CanonicalValueName(axis.value) for axis in CanonicalAxisName}
_REFRIGERANT_ALIASES = {
    "r744": "R744",
    "co2": "R744",
    "carbondioxide": "R744",
}
_UNITS: pint.UnitRegistry[float] = pint.UnitRegistry()


@dataclass(frozen=True)
class DetailLoadResult:
    records: tuple[ProductRecord, ...]
    diagnostics: tuple[str, ...]


@dataclass(frozen=True)
class SheetRow:
    sheet: str
    row: int
    values: Mapping[str, object]


def has_detail_sheets(sheetnames: Sequence[str]) -> bool:
    return bool(ALL_DETAIL_SHEETS.intersection(sheetnames))


def normalize_supported_refrigerants(
    records: tuple[ProductRecord, ...],
) -> tuple[ProductRecord, ...]:
    """Validate and canonicalize schema-0.2 product refrigerants."""
    normalized_records: list[ProductRecord] = []
    for record in records:
        normalized: list[str] = []
        for label in record.supported_refrigerants:
            try:
                canonical = _REFRIGERANT_ALIASES[label.strip().casefold()]
            except KeyError as exc:
                raise DatabaseValidationError(
                    "Invalid basic supported_refrigerants for "
                    f"product {record.product_id!r}: unapproved refrigerant alias {label!r}"
                ) from exc
            if canonical in normalized:
                raise DatabaseValidationError(
                    "Invalid basic supported_refrigerants for "
                    f"product {record.product_id!r}: duplicate canonical refrigerant "
                    f"{canonical!r}"
                )
            normalized.append(canonical)
        payload = record.model_dump(mode="python")
        payload["supported_refrigerants"] = tuple(normalized)
        normalized_records.append(ProductRecord.model_validate(payload))
    return tuple(normalized_records)


def load_details(
    workbook: Any,
    records: tuple[ProductRecord, ...],
    *,
    relative_path: str,
    digest: str,
) -> DetailLoadResult:
    """Load independent detailed parents and quarantine only invalid dependencies."""
    if not has_detail_sheets(workbook.sheetnames):
        return DetailLoadResult(records=records, diagnostics=())

    missing = sorted(_missing_bundle_sheets(workbook.sheetnames))
    if missing:
        message = _diagnostic(
            relative_path,
            "<detail>",
            0,
            "workbook",
            "detail",
            f"missing required detail sheet(s): {', '.join(missing)}",
        )
        return DetailLoadResult(records=records, diagnostics=(message,))

    try:
        sheets = _read_detail_sheets(workbook)
    except DatabaseValidationError as exc:
        message = _diagnostic(relative_path, "<detail>", 0, "workbook", "detail", str(exc))
        return DetailLoadResult(records=records, diagnostics=(message,))

    diagnostics: list[str] = []
    record_ids = {record.product_id for record in records}
    sources_by_product = _load_sources(
        sheets[DATA_SOURCES],
        sheets[DERIVED_SOURCE_CONDITIONS],
        record_ids,
        relative_path=relative_path,
        digest=digest,
        diagnostics=diagnostics,
    )
    rated_by_product = _load_rated(
        sheets,
        record_ids,
        sources_by_product,
        relative_path=relative_path,
        diagnostics=diagnostics,
    )
    maps_by_product = _load_maps(
        sheets,
        record_ids,
        sources_by_product,
        relative_path=relative_path,
        diagnostics=diagnostics,
    )
    envelopes_by_product = _load_envelopes(
        sheets,
        record_ids,
        sources_by_product,
        relative_path=relative_path,
        diagnostics=diagnostics,
    )

    detailed: list[ProductRecord] = []
    for record in records:
        product_sources = tuple(sources_by_product.get(record.product_id, ()))
        rated = tuple(rated_by_product.get(record.product_id, ()))
        maps = tuple(maps_by_product.get(record.product_id, ()))
        envelopes = tuple(envelopes_by_product.get(record.product_id, ()))
        rated, maps, envelopes = _quarantine_record_contract(
            relative_path, record, rated, maps, envelopes, diagnostics
        )
        product_sources, rated, maps, envelopes = _quarantine_duplicate_value_ids(
            relative_path,
            record.product_id,
            product_sources,
            rated,
            maps,
            envelopes,
            diagnostics,
        )
        product_sources, rated, maps, envelopes = _quarantine_invalid_source_fanout(
            relative_path,
            record.product_id,
            product_sources,
            rated,
            maps,
            envelopes,
            diagnostics,
        )
        payload = record.model_dump(mode="python")
        payload.update(
            data_sources=product_sources,
            rated_points=rated,
            performance_maps=maps,
            operating_envelopes=envelopes,
        )
        try:
            detailed.append(ProductRecord.model_validate(payload))
        except ValidationError as exc:
            diagnostics.append(
                _diagnostic(
                    relative_path,
                    "<product-detail>",
                    0,
                    "product",
                    record.product_id,
                    _validation_message(exc),
                )
            )
            detailed.append(record)
    return DetailLoadResult(
        records=tuple(detailed),
        diagnostics=tuple(sorted(set(diagnostics), key=str.casefold)),
    )


def _missing_bundle_sheets(sheetnames: Sequence[str]) -> set[str]:
    present = set(sheetnames)
    missing = (
        {DATA_SOURCES}
        if ALL_DETAIL_SHEETS.intersection(present) and DATA_SOURCES not in present
        else set()
    )
    bundles = (
        ({RATED_POINTS, RATED_VALUES}, "rated"),
        ({PERFORMANCE_MAPS, MAP_AXES, PERFORMANCE_POINTS, PERFORMANCE_VALUES}, "map"),
        ({OPERATING_ENVELOPES, ENVELOPE_AXES, ENVELOPE_VERTICES}, "envelope"),
    )
    for bundle, _ in bundles:
        if bundle.intersection(present) and not bundle <= present:
            missing.update(bundle - present)
    return missing


def _read_detail_sheets(workbook: Any) -> dict[str, list[SheetRow]]:
    required: dict[str, tuple[str, ...]] = {
        DATA_SOURCES: SOURCE_COLUMNS,
        DERIVED_SOURCE_CONDITIONS: DERIVED_SOURCE_CONDITION_COLUMNS,
        RATED_POINTS: RATED_PARENT_COLUMNS,
        RATED_VALUES: RATED_VALUE_COLUMNS,
        PERFORMANCE_MAPS: MAP_PARENT_COLUMNS,
        MAP_AXES: MAP_AXIS_COLUMNS,
        PERFORMANCE_POINTS: POINT_COLUMNS,
        PERFORMANCE_VALUES: POINT_VALUE_COLUMNS,
        OPERATING_ENVELOPES: ENVELOPE_PARENT_COLUMNS,
        ENVELOPE_AXES: ENVELOPE_AXIS_COLUMNS,
        ENVELOPE_VERTICES: ENVELOPE_VERTEX_COLUMNS,
        MAP_FIXED: MAP_FIXED_COLUMNS,
        ENVELOPE_FIXED: ENVELOPE_FIXED_COLUMNS,
    }
    result: dict[str, list[SheetRow]] = {}
    for name, columns in required.items():
        if name not in workbook.sheetnames:
            result[name] = []
            continue
        result[name] = _sheet_rows(workbook[name], columns)
    return result


def _sheet_rows(sheet: Any, required: tuple[str, ...]) -> list[SheetRow]:
    iterator = sheet.iter_rows(values_only=True)
    try:
        raw_header = next(iterator)
    except StopIteration as exc:
        raise DatabaseValidationError(f"{sheet.title} sheet is empty") from exc
    header = [_header(value, sheet.title) for value in raw_header]
    if len(header) != len(set(header)):
        raise DatabaseValidationError(f"{sheet.title} contains duplicate column names")
    missing = sorted(set(required) - set(header))
    if missing:
        raise DatabaseValidationError(
            f"{sheet.title} missing required column(s): {', '.join(missing)}"
        )
    rows: list[SheetRow] = []
    for row_number, values in enumerate(iterator, start=2):
        if all(_blank(value) for value in values):
            continue
        rows.append(
            SheetRow(
                sheet=sheet.title,
                row=row_number,
                values=dict(zip(header, values, strict=False)),
            )
        )
    return rows


def _header(value: object, sheet: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DatabaseValidationError(f"{sheet} contains a blank or non-text header")
    return value.strip()


def _load_sources(
    rows: list[SheetRow],
    condition_rows: list[SheetRow],
    product_ids: set[str],
    *,
    relative_path: str,
    digest: str,
    diagnostics: list[str],
) -> dict[str, tuple[ProductDataSource, ...]]:
    loaded: dict[str, list[ProductDataSource]] = defaultdict(list)
    seen: dict[str, SheetRow] = {}
    duplicate_source_ids: set[str] = set()
    for row in rows:
        product_id = _text_or_empty(row.values.get("product_id"))
        source_id = _text_or_empty(row.values.get("source_id"))
        if product_id not in product_ids:
            diagnostics.append(
                _row_diagnostic(relative_path, row, "source", source_id, "unknown product_id")
            )
            continue
        if source_id in seen:
            duplicate_source_ids.add(source_id)
            diagnostics.append(
                _row_diagnostic(relative_path, row, "source", source_id, "duplicate source_id")
            )
            first = seen[source_id]
            diagnostics.append(
                _row_diagnostic(relative_path, first, "source", source_id, "duplicate source_id")
            )
            continue
        seen[source_id] = row

    conditions_by_source = _group_rows(condition_rows, "derived_source_id")
    for derived_source_id, linked_rows in conditions_by_source.items():
        source_row = seen.get(derived_source_id)
        if derived_source_id in duplicate_source_ids or source_row is None:
            for linked_row in linked_rows:
                diagnostics.append(
                    _row_diagnostic(
                        relative_path,
                        linked_row,
                        "source",
                        derived_source_id or "<missing>",
                        "unresolved or duplicate derived_source_id",
                    )
                )
            continue
        origin = _text_or_empty(source_row.values.get("origin"))
        if origin != DataOrigin.PHYSICS_DERIVED.value:
            for linked_row in linked_rows:
                diagnostics.append(
                    _row_diagnostic(
                        relative_path,
                        linked_row,
                        "source",
                        derived_source_id,
                        "derived_source_id must reference a PHYSICS_DERIVED source",
                    )
                )

    for source_id, row in sorted(seen.items()):
        if source_id in duplicate_source_ids:
            continue
        product_id = _text_or_empty(row.values.get("product_id"))
        try:
            origin = DataOrigin(_text(row.values.get("origin"), "origin"))
            applicable_conditions: tuple[ProductDataValue, ...] = ()
            if origin == DataOrigin.PHYSICS_DERIVED:
                linked_rows = conditions_by_source.get(source_id, [])
                if not linked_rows:
                    raise ValueError(
                        "PHYSICS_DERIVED source requires at least one applicable condition"
                    )
                built: list[ProductDataValue] = []
                invalid_conditions = False
                seen_value_ids: set[str] = set()
                seen_names: set[CanonicalValueName] = set()
                for linked_row in linked_rows:
                    try:
                        condition = _value_from_row(linked_row)
                        if (
                            condition.value_id in seen_value_ids
                            or condition.canonical_name in seen_names
                        ):
                            raise ValueError(
                                "duplicate applicable condition value_id or canonical_name"
                            )
                        seen_value_ids.add(condition.value_id)
                        seen_names.add(condition.canonical_name)
                        built.append(condition)
                    except (KeyError, ValueError, TypeError, ValidationError) as exc:
                        invalid_conditions = True
                        diagnostics.append(
                            _row_diagnostic(
                                relative_path,
                                linked_row,
                                "source",
                                source_id,
                                str(exc),
                            )
                        )
                if invalid_conditions:
                    raise ValueError("invalid PHYSICS_DERIVED applicable_conditions")
                applicable_conditions = _sort_values(tuple(built))
            source = _source_from_row(
                row,
                relative_path=relative_path,
                digest=digest,
                applicable_conditions=applicable_conditions,
            )
            loaded[product_id].append(source)
        except (KeyError, ValueError, TypeError, ValidationError) as exc:
            diagnostics.append(
                _row_diagnostic(relative_path, row, "source", source_id or "<missing>", str(exc))
            )
    return {
        product_id: tuple(
            sorted(
                (item for item in items if item.source_id not in duplicate_source_ids),
                key=lambda item: item.source_id,
            )
        )
        for product_id, items in loaded.items()
    }


def _source_from_row(
    row: SheetRow,
    *,
    relative_path: str,
    digest: str,
    applicable_conditions: tuple[ProductDataValue, ...],
) -> ProductDataSource:
    source_id = _text(row.values.get("source_id"), "source_id")
    origin = DataOrigin(_text(row.values.get("origin"), "origin"))
    if origin in (DataOrigin.MANUFACTURER, DataOrigin.TEST_STANDARD):
        forbidden_text = ("method_id", "method_version", "equation_ref")
        if any(not _blank(row.values.get(field)) for field in forbidden_text):
            raise ValueError(f"{origin.value} source forbids derived method fields")
        if _json_text_tuple(row.values.get("input_value_refs"), "input_value_refs"):
            raise ValueError(f"{origin.value} source forbids input_value_refs")
        if _json_text_tuple(row.values.get("assumptions"), "assumptions"):
            raise ValueError(f"{origin.value} source forbids assumptions")
        return WorkbookProductDataSource(
            source_id=source_id,
            origin=origin,
            excel_file=relative_path,
            file_sha256=digest,
            sheet=row.sheet,
            row=row.row,
            document_ref=_text(row.values.get("document_ref"), "document_ref"),
            table_or_figure_ref=_optional_text(row.values.get("table_or_figure_ref")),
            original_manufacturer=_text(
                row.values.get("original_manufacturer"), "original_manufacturer"
            ),
            original_model=_text(row.values.get("original_model"), "original_model"),
        )
    forbidden_workbook = (
        "document_ref",
        "table_or_figure_ref",
        "original_manufacturer",
        "original_model",
    )
    if any(not _blank(row.values.get(field)) for field in forbidden_workbook):
        raise ValueError("PHYSICS_DERIVED source forbids workbook provenance fields")
    return PhysicsDerivedDataSource(
        source_id=source_id,
        origin=DataOrigin.PHYSICS_DERIVED,
        derived_method=DerivedMethod(
            method_id=_text(row.values.get("method_id"), "method_id"),
            method_version=_text(row.values.get("method_version"), "method_version"),
            equation_ref=_text(row.values.get("equation_ref"), "equation_ref"),
            input_value_refs=_json_text_tuple(
                row.values.get("input_value_refs"), "input_value_refs", nonempty=True
            ),
            applicable_conditions=applicable_conditions,
            assumptions=_json_text_tuple(row.values.get("assumptions"), "assumptions"),
        ),
    )


def _load_rated(
    sheets: Mapping[str, list[SheetRow]],
    product_ids: set[str],
    sources: Mapping[str, tuple[ProductDataSource, ...]],
    *,
    relative_path: str,
    diagnostics: list[str],
) -> dict[str, tuple[RatedPoint, ...]]:
    parent_rows = _unique_parents(
        sheets[RATED_POINTS], "rated_point_id", product_ids, relative_path, diagnostics
    )
    value_rows = _group_rows(sheets[RATED_VALUES], "rated_point_id")
    result: dict[str, list[RatedPoint]] = defaultdict(list)
    for parent_id, row in sorted(parent_rows.items()):
        product_id = _text_or_empty(row.values.get("product_id"))
        try:
            values = value_rows.get(parent_id, [])
            conditions = tuple(
                _value_from_row(item)
                for item in values
                if _text(item.values.get("value_role"), "value_role") == "CONDITION"
            )
            outputs = tuple(
                _value_from_row(item)
                for item in values
                if _text(item.values.get("value_role"), "value_role") == "OUTPUT"
            )
            if len(conditions) + len(outputs) != len(values):
                raise ValueError("value_role must be CONDITION or OUTPUT")
            rated = RatedPoint(
                rated_point_id=parent_id,
                refrigerant=_canonical_refrigerant(row.values.get("refrigerant_label")),
                original_refrigerant_label=_text(
                    row.values.get("refrigerant_label"), "refrigerant_label"
                ),
                topology=ProductTopology(_text(row.values.get("topology"), "topology")),
                mode=OperatingMode(_text(row.values.get("mode"), "mode")),
                conditions=_sort_values(conditions),
                outputs=_sort_values(outputs),
                source_id=_text(row.values.get("source_id"), "source_id"),
                use_status=_use_status(row),
            )
            _validate_single_parent(product_id, sources, rated_points=(rated,))
            result[product_id].append(rated)
        except (KeyError, ValueError, TypeError, ValidationError) as exc:
            diagnostics.append(
                _row_diagnostic(relative_path, row, "rated_point", parent_id, str(exc))
            )
    _orphan_rows(value_rows, parent_rows, relative_path, "rated_point", diagnostics)
    return {
        key: tuple(sorted(value, key=lambda item: item.rated_point_id))
        for key, value in result.items()
    }


def _load_maps(
    sheets: Mapping[str, list[SheetRow]],
    product_ids: set[str],
    sources: Mapping[str, tuple[ProductDataSource, ...]],
    *,
    relative_path: str,
    diagnostics: list[str],
) -> dict[str, tuple[PerformanceMap, ...]]:
    parents = _unique_parents(
        sheets[PERFORMANCE_MAPS], "map_id", product_ids, relative_path, diagnostics
    )
    axes = _group_rows(sheets[MAP_AXES], "map_id")
    point_parents = _unique_rows_by_id(
        sheets[PERFORMANCE_POINTS], "point_id", relative_path, diagnostics
    )
    raw_points_by_id = _group_rows(sheets[PERFORMANCE_POINTS], "point_id")
    invalid_point_ids = {
        point_id for point_id, rows in raw_points_by_id.items() if not point_id or len(rows) > 1
    }
    invalid_point_ids_by_map: dict[str, set[str]] = defaultdict(set)
    for point_id in invalid_point_ids:
        for point_row in raw_points_by_id[point_id]:
            map_id = _text_or_empty(point_row.values.get("map_id"))
            invalid_point_ids_by_map[map_id].add(point_id or "<missing>")
    point_values = _group_rows(sheets[PERFORMANCE_VALUES], "point_id")
    fixed = _group_rows(sheets[MAP_FIXED], "map_id")
    points_by_map = _group_mapping_values(point_parents, "map_id")
    result: dict[str, list[PerformanceMap]] = defaultdict(list)
    for map_id, row in sorted(parents.items()):
        product_id = _text_or_empty(row.values.get("product_id"))
        try:
            if map_id in invalid_point_ids_by_map:
                raise ValueError(
                    "missing or duplicate point_id in performance_points: "
                    f"{sorted(invalid_point_ids_by_map[map_id])}"
                )
            axis_rows = axes.get(map_id, [])
            point_rows = points_by_map.get(map_id, [])
            built_points, built_axes = _build_map_points_axes(
                map_id, axis_rows, point_rows, point_values
            )
            fixed_values = _sort_values(
                tuple(_value_from_row(item) for item in fixed.get(map_id, []))
            )
            output_names = tuple(
                name
                for name in CanonicalValueName
                if any(
                    name == output.canonical_name
                    for point in built_points
                    for output in point.outputs
                )
            )
            performance_map = PerformanceMap(
                map_id=map_id,
                map_kind=PerformanceMapKind(_text(row.values.get("map_kind"), "map_kind")),
                refrigerant=_canonical_refrigerant(row.values.get("refrigerant_label")),
                original_refrigerant_label=_text(
                    row.values.get("refrigerant_label"), "refrigerant_label"
                ),
                topology=ProductTopology(_text(row.values.get("topology"), "topology")),
                mode=OperatingMode(_text(row.values.get("mode"), "mode")),
                axes=built_axes,
                fixed_conditions=fixed_values,
                output_names=output_names,
                points=built_points,
                interpolation=InterpolationPolicy(
                    _text(row.values.get("interpolation"), "interpolation")
                ),
                extrapolation=_forbidden(row.values.get("extrapolation")),
                source_id=_text(row.values.get("source_id"), "source_id"),
                use_status=_use_status(row),
            )
            _validate_single_parent(product_id, sources, performance_maps=(performance_map,))
            result[product_id].append(performance_map)
        except (KeyError, ValueError, TypeError, ValidationError) as exc:
            diagnostics.append(_row_diagnostic(relative_path, row, "map", map_id, str(exc)))
    _orphan_rows(axes, parents, relative_path, "map", diagnostics)
    _orphan_rows(fixed, parents, relative_path, "map", diagnostics)
    _orphan_point_rows(point_parents, parents, point_values, relative_path, diagnostics)
    return {
        key: tuple(sorted(value, key=lambda item: item.map_id)) for key, value in result.items()
    }


def _build_map_points_axes(
    map_id: str,
    axis_rows: list[SheetRow],
    point_rows: list[SheetRow],
    value_rows: Mapping[str, list[SheetRow]],
) -> tuple[tuple[PerformancePoint, ...], tuple[MapAxis, ...]]:
    declarations = _axis_declarations(axis_rows, "map_id", map_id)
    declared_axis_ids = {
        _text(declaration.values.get("axis_id"), "axis_id") for declaration in declarations
    }
    points: list[PerformancePoint] = []
    coordinates_by_axis: dict[str, list[ProductDataValue]] = defaultdict(list)
    for point_row in sorted(
        point_rows, key=lambda item: _text_or_empty(item.values.get("point_id"))
    ):
        point_id = _text(point_row.values.get("point_id"), "point_id")
        coordinates: dict[str, ProductDataValue] = {}
        outputs: list[ProductDataValue] = []
        for value_row in value_rows.get(point_id, []):
            role = _text(value_row.values.get("value_role"), "value_role")
            value = _value_from_row(value_row)
            if role == "COORDINATE":
                axis_id = _text(value_row.values.get("axis_id"), "axis_id")
                if axis_id in coordinates:
                    raise ValueError(f"point {point_id} contains duplicate axis_id {axis_id}")
                coordinates[axis_id] = value
                coordinates_by_axis[axis_id].append(value)
            elif role == "OUTPUT":
                if not _blank(value_row.values.get("axis_id")):
                    raise ValueError(f"point {point_id} output must not contain axis_id")
                outputs.append(value)
            else:
                raise ValueError("value_role must be COORDINATE or OUTPUT")
        if set(coordinates) != declared_axis_ids:
            missing = sorted(declared_axis_ids - set(coordinates))
            unexpected = sorted(set(coordinates) - declared_axis_ids)
            raise ValueError(
                f"point {point_id} coordinate axis IDs disagree with map; "
                f"missing={missing}, unexpected={unexpected}"
            )
        ordered_coordinates = tuple(
            coordinates[_text(axis.values.get("axis_id"), "axis_id")] for axis in declarations
        )
        points.append(
            PerformancePoint(
                point_id=point_id,
                coordinates=ordered_coordinates,
                outputs=_sort_values(tuple(outputs)),
                source_id=_text(point_row.values.get("source_id"), "source_id"),
            )
        )
    built_axes = tuple(
        _axis_from_row(axis, coordinates_by_axis[_text(axis.values.get("axis_id"), "axis_id")])
        for axis in declarations
    )
    return tuple(points), built_axes


def _load_envelopes(
    sheets: Mapping[str, list[SheetRow]],
    product_ids: set[str],
    sources: Mapping[str, tuple[ProductDataSource, ...]],
    *,
    relative_path: str,
    diagnostics: list[str],
) -> dict[str, tuple[OperatingEnvelope, ...]]:
    parents = _unique_parents(
        sheets[OPERATING_ENVELOPES], "envelope_id", product_ids, relative_path, diagnostics
    )
    axes = _group_rows(sheets[ENVELOPE_AXES], "envelope_id")
    vertices = _group_rows(sheets[ENVELOPE_VERTICES], "envelope_id")
    fixed = _group_rows(sheets[ENVELOPE_FIXED], "envelope_id")
    result: dict[str, list[OperatingEnvelope]] = defaultdict(list)
    for envelope_id, row in sorted(parents.items()):
        product_id = _text_or_empty(row.values.get("product_id"))
        try:
            declarations = _axis_declarations(axes.get(envelope_id, []), "envelope_id", envelope_id)
            if len(declarations) != 2:
                raise ValueError("operating envelope requires exactly two axes")
            coordinate_values: dict[str, list[ProductDataValue]] = defaultdict(list)
            by_order: dict[int, dict[str, ProductDataValue]] = defaultdict(dict)
            vertex_sources: dict[int, set[str]] = defaultdict(set)
            for vertex_row in vertices.get(envelope_id, []):
                order = _integer(vertex_row.values.get("vertex_order"), "vertex_order")
                axis_id = _text(vertex_row.values.get("axis_id"), "axis_id")
                declaration = next(
                    (
                        item
                        for item in declarations
                        if _text(item.values.get("axis_id"), "axis_id") == axis_id
                    ),
                    None,
                )
                if declaration is None:
                    raise ValueError(f"vertex references unknown axis_id {axis_id}")
                canonical_axis = CanonicalAxisName(
                    _text(declaration.values.get("canonical_name"), "canonical_name")
                )
                value = _value_from_vertex(vertex_row, declaration, canonical_axis)
                if axis_id in by_order[order]:
                    raise ValueError(f"vertex {order} contains duplicate axis_id {axis_id}")
                by_order[order][axis_id] = value
                coordinate_values[axis_id].append(value)
                vertex_sources[order].add(_text(vertex_row.values.get("source_id"), "source_id"))
            built_axes = tuple(
                _axis_from_row(
                    axis,
                    coordinate_values[_text(axis.values.get("axis_id"), "axis_id")],
                )
                for axis in declarations
            )
            built_vertices: list[EnvelopeVertex] = []
            declared_axis_ids = {
                _text(axis.values.get("axis_id"), "axis_id") for axis in declarations
            }
            for order in sorted(by_order):
                if len(vertex_sources[order]) != 1:
                    raise ValueError(f"vertex {order} must use exactly one source_id")
                if set(by_order[order]) != declared_axis_ids:
                    missing = sorted(declared_axis_ids - set(by_order[order]))
                    unexpected = sorted(set(by_order[order]) - declared_axis_ids)
                    raise ValueError(
                        f"vertex {order} coordinate axis IDs disagree with envelope; "
                        f"missing={missing}, unexpected={unexpected}"
                    )
                coordinate_tuple = tuple(
                    by_order[order][_text(axis.values.get("axis_id"), "axis_id")]
                    for axis in declarations
                )
                if len(coordinate_tuple) != 2:
                    raise ValueError(f"vertex {order} must contain exactly two coordinates")
                coordinates = (coordinate_tuple[0], coordinate_tuple[1])
                built_vertices.append(
                    EnvelopeVertex(
                        vertex_order=order,
                        coordinates=coordinates,
                        source_id=next(iter(vertex_sources[order])),
                    )
                )
            envelope = OperatingEnvelope(
                envelope_id=envelope_id,
                refrigerant=_canonical_refrigerant(row.values.get("refrigerant_label")),
                original_refrigerant_label=_text(
                    row.values.get("refrigerant_label"), "refrigerant_label"
                ),
                axes=(built_axes[0], built_axes[1]),
                boundary_vertices=tuple(built_vertices),
                boundary_inclusive=_boolean(
                    row.values.get("boundary_inclusive"), "boundary_inclusive"
                ),
                fixed_conditions=_sort_values(
                    tuple(_value_from_row(item) for item in fixed.get(envelope_id, []))
                ),
                source_id=_text(row.values.get("source_id"), "source_id"),
                use_status=_use_status(row),
            )
            _validate_single_parent(product_id, sources, operating_envelopes=(envelope,))
            result[product_id].append(envelope)
        except (KeyError, ValueError, TypeError, ValidationError) as exc:
            diagnostics.append(
                _row_diagnostic(relative_path, row, "envelope", envelope_id, str(exc))
            )
    _orphan_rows(axes, parents, relative_path, "envelope", diagnostics)
    _orphan_rows(vertices, parents, relative_path, "envelope", diagnostics)
    _orphan_rows(fixed, parents, relative_path, "envelope", diagnostics)
    return {
        key: tuple(sorted(value, key=lambda item: item.envelope_id))
        for key, value in result.items()
    }


def _axis_declarations(rows: list[SheetRow], parent_key: str, parent_id: str) -> list[SheetRow]:
    if not rows:
        raise ValueError(f"{parent_id} contains no axis declarations")
    seen_ids: set[str] = set()
    seen_orders: set[int] = set()
    ordered: list[tuple[int, SheetRow]] = []
    for row in rows:
        if _text(row.values.get(parent_key), parent_key) != parent_id:
            raise ValueError(f"axis row parent mismatch for {parent_id}")
        axis_id = _text(row.values.get("axis_id"), "axis_id")
        order = _integer(row.values.get("order"), "order")
        if axis_id in seen_ids or order in seen_orders:
            raise ValueError(f"{parent_id} contains duplicate axis_id or order")
        seen_ids.add(axis_id)
        seen_orders.add(order)
        ordered.append((order, row))
    ordered.sort(key=lambda item: item[0])
    return [row for _, row in ordered]


def _axis_from_row(row: SheetRow, values: list[ProductDataValue]) -> MapAxis:
    if not values:
        raise ValueError("axis has no coordinate values")
    canonical_text = _optional_text(row.values.get("canonical_name"))
    canonical = CanonicalAxisName(canonical_text) if canonical_text is not None else None
    declared_original_unit = _text(row.values.get("original_unit"), "original_unit")
    if any(value.original_unit != declared_original_unit for value in values):
        raise ValueError("coordinate original_unit disagrees with axis declaration")
    pairs = sorted({(value.value_si.value, value.original_value) for value in values})
    return MapAxis(
        axis_id=_text(row.values.get("axis_id"), "axis_id"),
        order=_integer(row.values.get("order"), "order"),
        canonical_name=canonical,
        native_name=_text(row.values.get("native_name"), "native_name"),
        role=AxisRole(_text(row.values.get("role"), "role")),
        physical_kind=AxisPhysicalKind(_text(row.values.get("physical_kind"), "physical_kind")),
        original_unit=declared_original_unit,
        canonical_unit=_text(row.values.get("canonical_unit"), "canonical_unit"),
        original_values=tuple(original for _, original in pairs),
        values_si=tuple(si for si, _ in pairs),
        source_id=_text(row.values.get("source_id"), "source_id"),
    )


def _value_from_vertex(
    row: SheetRow, declaration: SheetRow, canonical_axis: CanonicalAxisName
) -> ProductDataValue:
    values = dict(row.values)
    axis_id = _text(values.get("axis_id"), "axis_id")
    order = _integer(values.get("vertex_order"), "vertex_order")
    values.update(
        value_id=f"{_text(values.get('envelope_id'), 'envelope_id')}:vertex:{order}:{axis_id}",
        canonical_name=_AXIS_VALUE_NAMES[canonical_axis].value,
        original_name=_text(declaration.values.get("native_name"), "native_name"),
        tolerance_kind=None,
        tolerance_value=None,
        tolerance_unit=None,
        tolerance_reference=None,
        tolerance_reference_value=None,
        tolerance_reference_unit=None,
        tolerance_source_id=None,
        tolerance_absence_reason=ToleranceAbsenceReason.NOT_APPLICABLE.value,
        accuracy_validation=AccuracyValidationStatus.NOT_VERIFIABLE.value,
    )
    return _value_from_mapping(values)


def _value_from_row(row: SheetRow) -> ProductDataValue:
    return _value_from_mapping(row.values)


def _value_from_mapping(values: Mapping[str, object]) -> ProductDataValue:
    canonical = CanonicalValueName(_text(values.get("canonical_name"), "canonical_name"))
    original_value = _number(values.get("original_value"), "original_value")
    original_unit = _text(values.get("original_unit"), "original_unit")
    expected_unit = _VALUE_UNITS.get(canonical)
    if expected_unit is None:
        normalized = Quantity(value=original_value, unit=original_unit)
        si_value, si_unit = normalized.value, normalized.unit
    else:
        try:
            converted = _UNITS.Quantity(original_value, original_unit).to(expected_unit)
            si_value = float(converted.magnitude)
        except (pint.errors.PintError, TypeError, ValueError) as exc:
            raise ValueError(
                f"original_unit {original_unit!r} is incompatible with {expected_unit!r}"
            ) from exc
        si_unit = expected_unit
    _validate_audit(values, si_value, si_unit)
    return ProductDataValue(
        value_id=_text(values.get("value_id"), "value_id"),
        canonical_name=canonical,
        original_name=_text(values.get("original_name"), "original_name"),
        original_value=original_value,
        original_unit=original_unit,
        value_si=Quantity(value=si_value, unit=si_unit),
        source_id=_text(values.get("source_id"), "source_id"),
        tolerance=_tolerance(values, canonical_unit=si_unit),
    )


def _validate_audit(values: Mapping[str, object], calculated: float, expected_unit: str) -> None:
    raw_value = values.get("provided_value_si")
    raw_unit = values.get("provided_canonical_unit")
    if _blank(raw_value) != _blank(raw_unit):
        raise ValueError("provided SI value and canonical unit must be supplied together")
    if _blank(raw_value):
        return
    provided = _number(raw_value, "provided_value_si")
    unit = _text(raw_unit, "provided_canonical_unit")
    if unit != expected_unit:
        raise ValueError(f"provided_canonical_unit must be {expected_unit!r}")
    same = (
        provided == calculated
        if provided == 0.0 or calculated == 0.0
        else math.isclose(provided, calculated, rel_tol=1e-12, abs_tol=0.0)
    )
    if not same:
        raise ValueError("provided_value_si disagrees with loader unit conversion")


def _tolerance(values: Mapping[str, object], *, canonical_unit: str) -> ToleranceInfo:
    accuracy = AccuracyValidationStatus(
        _text(values.get("accuracy_validation"), "accuracy_validation")
    )
    absence = _optional_text(values.get("tolerance_absence_reason"))
    kind = _optional_text(values.get("tolerance_kind"))
    if kind is None:
        unexpected = (
            "tolerance_value",
            "tolerance_unit",
            "tolerance_reference",
            "tolerance_reference_value",
            "tolerance_reference_unit",
            "tolerance_source_id",
        )
        if any(not _blank(values.get(field)) for field in unexpected):
            raise ValueError("tolerance fields require tolerance_kind")
        return ToleranceInfo(
            value=None,
            absence_reason=ToleranceAbsenceReason(_text(absence, "tolerance_absence_reason")),
            accuracy_validation=accuracy,
        )
    tolerance_kind = ToleranceKind(kind)
    tolerance_value = _number(values.get("tolerance_value"), "tolerance_value")
    tolerance_unit = _text(values.get("tolerance_unit"), "tolerance_unit")
    reference_raw = values.get("tolerance_reference_value")
    reference_unit_raw = values.get("tolerance_reference_unit")
    if _blank(reference_raw) != _blank(reference_unit_raw):
        raise ValueError("tolerance reference value and unit must be supplied together")
    if tolerance_kind == ToleranceKind.ABSOLUTE:
        _convert_unit_value(tolerance_value, tolerance_unit, canonical_unit, "tolerance_unit")
    reference_value = (
        None
        if _blank(reference_raw)
        else Quantity(
            value=_convert_unit_value(
                _number(reference_raw, "tolerance_reference_value"),
                _text(reference_unit_raw, "tolerance_reference_unit"),
                canonical_unit,
                "tolerance_reference_unit",
            ),
            unit=canonical_unit,
        )
    )
    tolerance = ToleranceSpec(
        kind=tolerance_kind,
        value=Quantity(value=tolerance_value, unit=tolerance_unit),
        reference=ToleranceReference(
            _text(values.get("tolerance_reference"), "tolerance_reference")
        ),
        reference_value=reference_value,
        source_id=_text(values.get("tolerance_source_id"), "tolerance_source_id"),
    )
    if absence is not None:
        raise ValueError("tolerance value forbids tolerance_absence_reason")
    return ToleranceInfo(value=tolerance, accuracy_validation=accuracy)


def _convert_unit_value(value: float, unit: str, target: str, field: str) -> float:
    try:
        return float(_UNITS.Quantity(value, unit).to(target).magnitude)
    except (pint.errors.PintError, TypeError, ValueError) as exc:
        raise ValueError(f"{field} {unit!r} is incompatible with {target!r}") from exc


def _use_status(row: SheetRow) -> DataUseStatus:
    reasons = tuple(
        UseRestrictionReason(item)
        for item in _json_text_tuple(row.values.get("restriction_reasons"), "restriction_reasons")
    )
    return DataUseStatus(
        source_preserved=True,
        structure_valid=True,
        automatic_selection=AutomaticSelectionStatus(
            _text(row.values.get("automatic_selection"), "automatic_selection")
        ),
        reasons=reasons,
    )


def _quarantine_duplicate_value_ids(
    relative_path: str,
    product_id: str,
    sources: tuple[ProductDataSource, ...],
    rated: tuple[RatedPoint, ...],
    maps: tuple[PerformanceMap, ...],
    envelopes: tuple[OperatingEnvelope, ...],
    diagnostics: list[str],
) -> tuple[
    tuple[ProductDataSource, ...],
    tuple[RatedPoint, ...],
    tuple[PerformanceMap, ...],
    tuple[OperatingEnvelope, ...],
]:
    owners: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for source in sources:
        if isinstance(source, PhysicsDerivedDataSource):
            for value in source.derived_method.applicable_conditions:
                owners[value.value_id].append(("source", source.source_id))
    for rated_parent in rated:
        for value in rated_parent.conditions + rated_parent.outputs:
            owners[value.value_id].append(("rated_point", rated_parent.rated_point_id))
    for map_parent in maps:
        for value in map_parent.fixed_conditions:
            owners[value.value_id].append(("map", map_parent.map_id))
        for point in map_parent.points:
            for value in point.coordinates + point.outputs:
                owners[value.value_id].append(("map", map_parent.map_id))
    for envelope_parent in envelopes:
        for value in envelope_parent.fixed_conditions:
            owners[value.value_id].append(("envelope", envelope_parent.envelope_id))
        for vertex in envelope_parent.boundary_vertices:
            for value in vertex.coordinates:
                owners[value.value_id].append(("envelope", envelope_parent.envelope_id))
    invalid: set[tuple[str, str]] = set()
    for value_id, linked in owners.items():
        distinct = set(linked)
        if len(linked) == 1:
            continue
        invalid.update(distinct)
        for kind, parent_id in sorted(distinct):
            diagnostics.append(
                _diagnostic(
                    relative_path,
                    "<product-detail>",
                    0,
                    kind,
                    parent_id,
                    f"duplicate product-wide value_id {value_id!r} in product {product_id}",
                )
            )
    return (
        tuple(item for item in sources if ("source", item.source_id) not in invalid),
        tuple(item for item in rated if ("rated_point", item.rated_point_id) not in invalid),
        tuple(item for item in maps if ("map", item.map_id) not in invalid),
        tuple(item for item in envelopes if ("envelope", item.envelope_id) not in invalid),
    )


def _quarantine_record_contract(
    relative_path: str,
    record: ProductRecord,
    rated: tuple[RatedPoint, ...],
    maps: tuple[PerformanceMap, ...],
    envelopes: tuple[OperatingEnvelope, ...],
    diagnostics: list[str],
) -> tuple[tuple[RatedPoint, ...], tuple[PerformanceMap, ...], tuple[OperatingEnvelope, ...]]:
    supported = set(record.supported_refrigerants)

    def valid_refrigerant(kind: str, parent_id: str, refrigerant: str) -> bool:
        if refrigerant in supported:
            return True
        diagnostics.append(
            _diagnostic(
                relative_path,
                "<product-detail>",
                0,
                kind,
                parent_id,
                "detailed record refrigerant is not supported by product",
            )
        )
        return False

    valid_rated: list[RatedPoint] = []
    for rated_parent in rated:
        if not valid_refrigerant(
            "rated_point", rated_parent.rated_point_id, rated_parent.refrigerant
        ):
            continue
        if _rated_contract_is_valid(record, rated_parent):
            valid_rated.append(rated_parent)
        else:
            diagnostics.append(
                _diagnostic(
                    relative_path,
                    "<product-detail>",
                    0,
                    "rated_point",
                    rated_parent.rated_point_id,
                    "eligible R744 compressor capacity rated point lacks required conditions",
                )
            )

    expected_kind = {
        "compressor": PerformanceMapKind.COMPRESSOR,
        "expansion_valve": PerformanceMapKind.EXPANSION_VALVE,
    }.get(record.component_type.value)
    valid_maps: list[PerformanceMap] = []
    for map_parent in maps:
        if not valid_refrigerant("map", map_parent.map_id, map_parent.refrigerant):
            continue
        if map_parent.map_kind != expected_kind:
            diagnostics.append(
                _diagnostic(
                    relative_path,
                    "<product-detail>",
                    0,
                    "map",
                    map_parent.map_id,
                    "component_type and map_kind disagree",
                )
            )
            continue
        valid_maps.append(map_parent)

    valid_envelopes: list[OperatingEnvelope] = []
    for envelope_parent in envelopes:
        if not valid_refrigerant(
            "envelope", envelope_parent.envelope_id, envelope_parent.refrigerant
        ):
            continue
        error = _envelope_contract_error(record, envelope_parent)
        if error is None:
            valid_envelopes.append(envelope_parent)
        else:
            diagnostics.append(
                _diagnostic(
                    relative_path,
                    "<product-detail>",
                    0,
                    "envelope",
                    envelope_parent.envelope_id,
                    error,
                )
            )
    return tuple(valid_rated), tuple(valid_maps), tuple(valid_envelopes)


def _rated_contract_is_valid(record: ProductRecord, parent: RatedPoint) -> bool:
    if not (
        record.component_type.value == "compressor"
        and parent.use_status.automatic_selection == AutomaticSelectionStatus.ELIGIBLE
        and parent.refrigerant == "R744"
        and parent.topology == ProductTopology.R744_TRANSCRITICAL
        and parent.mode == OperatingMode.COOLING
        and CanonicalValueName.COOLING_CAPACITY
        in {output.canonical_name for output in parent.outputs}
    ):
        return True
    conditions = {condition.canonical_name for condition in parent.conditions}
    return {
        CanonicalValueName.SUCTION_PRESSURE,
        CanonicalValueName.DISCHARGE_PRESSURE,
        CanonicalValueName.SUCTION_TEMPERATURE,
    } <= conditions and bool(
        conditions
        & {
            CanonicalValueName.GAS_COOLER_OUTLET_TEMPERATURE,
            CanonicalValueName.GAS_COOLER_OUTLET_ENTHALPY,
        }
    )


def _envelope_contract_error(record: ProductRecord, parent: OperatingEnvelope) -> str | None:
    if parent.use_status.automatic_selection != AutomaticSelectionStatus.ELIGIBLE:
        return None
    axes = tuple(axis.canonical_name for axis in parent.axes)
    fixed = {value.canonical_name for value in parent.fixed_conditions}
    if record.component_type.value == "compressor":
        if (
            axes
            != (
                CanonicalAxisName.SUCTION_PRESSURE,
                CanonicalAxisName.DISCHARGE_PRESSURE,
            )
            or CanonicalValueName.SUCTION_TEMPERATURE not in fixed
        ):
            return "eligible compressor envelope lacks required axes/fixed conditions"
        if len(fixed & {CanonicalValueName.SPEED, CanonicalValueName.FREQUENCY}) != 1:
            return "eligible compressor envelope requires one speed/frequency condition"
    elif record.component_type.value == "expansion_valve" and (
        axes
        != (
            CanonicalAxisName.INLET_PRESSURE,
            CanonicalAxisName.OUTLET_PRESSURE,
        )
        or not {CanonicalValueName.INLET_TEMPERATURE, CanonicalValueName.OPENING} <= fixed
    ):
        return "eligible valve envelope lacks required axes/fixed conditions"
    return None


def _quarantine_invalid_source_fanout(
    relative_path: str,
    product_id: str,
    sources: tuple[ProductDataSource, ...],
    rated: tuple[RatedPoint, ...],
    maps: tuple[PerformanceMap, ...],
    envelopes: tuple[OperatingEnvelope, ...],
    diagnostics: list[str],
) -> tuple[
    tuple[ProductDataSource, ...],
    tuple[RatedPoint, ...],
    tuple[PerformanceMap, ...],
    tuple[OperatingEnvelope, ...],
]:
    valid_sources = sources
    valid_rated = rated
    valid_maps = maps
    valid_envelopes = envelopes
    reported_sources: set[str] = set()

    while True:
        source_ids = {source.source_id for source in valid_sources}
        value_ids = _all_value_ids(valid_sources, valid_rated, valid_maps, valid_envelopes)
        invalid_reasons: dict[str, str] = {}
        for source in valid_sources:
            if not isinstance(source, PhysicsDerivedDataSource):
                continue
            missing_value_refs = set(source.derived_method.input_value_refs) - value_ids
            missing_source_refs = (
                _value_source_ids(source.derived_method.applicable_conditions) - source_ids
            )
            if missing_value_refs:
                invalid_reasons[source.source_id] = (
                    f"unresolved derived input_value_refs: {sorted(missing_value_refs)}"
                )
            elif missing_source_refs:
                invalid_reasons[source.source_id] = (
                    f"invalid applicable-condition source fan-out: {sorted(missing_source_refs)}"
                )

        invalid_source_ids = set(invalid_reasons)
        for source_id in sorted(invalid_source_ids - reported_sources):
            diagnostics.append(
                _diagnostic(
                    relative_path,
                    DATA_SOURCES,
                    0,
                    "source",
                    source_id,
                    f"{invalid_reasons[source_id]} in product {product_id}",
                )
            )
        reported_sources.update(invalid_source_ids)
        if invalid_source_ids:
            valid_sources = tuple(
                source for source in valid_sources if source.source_id not in invalid_source_ids
            )
            source_ids = {source.source_id for source in valid_sources}

        removed_parent = False

        def keep_parent(
            kind: str,
            parent_id: str,
            used_sources: set[str],
            valid_source_ids: set[str] = source_ids,
        ) -> bool:
            nonlocal removed_parent
            missing = used_sources - valid_source_ids
            if not missing:
                return True
            removed_parent = True
            diagnostics.append(
                _diagnostic(
                    relative_path,
                    "<product-detail>",
                    0,
                    kind,
                    parent_id,
                    f"invalid source fan-out: {sorted(missing)}",
                )
            )
            return False

        valid_rated = tuple(
            parent
            for parent in valid_rated
            if keep_parent(
                "rated_point",
                parent.rated_point_id,
                {parent.source_id} | _value_source_ids(parent.conditions + parent.outputs),
            )
        )
        valid_maps = tuple(
            parent
            for parent in valid_maps
            if keep_parent("map", parent.map_id, _map_source_ids(parent))
        )
        valid_envelopes = tuple(
            parent
            for parent in valid_envelopes
            if keep_parent("envelope", parent.envelope_id, _envelope_source_ids(parent))
        )
        if not invalid_source_ids and not removed_parent:
            break

    return valid_sources, valid_rated, valid_maps, valid_envelopes


def _all_value_ids(
    sources: tuple[ProductDataSource, ...],
    rated: tuple[RatedPoint, ...],
    maps: tuple[PerformanceMap, ...],
    envelopes: tuple[OperatingEnvelope, ...],
) -> set[str]:
    result: set[str] = set()
    for source in sources:
        if isinstance(source, PhysicsDerivedDataSource):
            result.update(value.value_id for value in source.derived_method.applicable_conditions)
    for rated_parent in rated:
        result.update(value.value_id for value in rated_parent.conditions + rated_parent.outputs)
    for map_parent in maps:
        result.update(value.value_id for value in map_parent.fixed_conditions)
        for point in map_parent.points:
            result.update(value.value_id for value in point.coordinates + point.outputs)
    for envelope_parent in envelopes:
        result.update(value.value_id for value in envelope_parent.fixed_conditions)
        for vertex in envelope_parent.boundary_vertices:
            result.update(value.value_id for value in vertex.coordinates)
    return result


def _value_source_ids(values: Iterable[ProductDataValue]) -> set[str]:
    result = {value.source_id for value in values}
    result.update(
        value.tolerance.value.source_id for value in values if value.tolerance.value is not None
    )
    return result


def _map_source_ids(parent: PerformanceMap) -> set[str]:
    result = {parent.source_id, *(axis.source_id for axis in parent.axes)}
    result.update(_value_source_ids(parent.fixed_conditions))
    for point in parent.points:
        result.add(point.source_id)
        result.update(_value_source_ids(point.coordinates + point.outputs))
    return result


def _envelope_source_ids(parent: OperatingEnvelope) -> set[str]:
    result = {parent.source_id, *(axis.source_id for axis in parent.axes)}
    result.update(_value_source_ids(parent.fixed_conditions))
    for vertex in parent.boundary_vertices:
        result.add(vertex.source_id)
        result.update(_value_source_ids(vertex.coordinates))
    return result


def _validate_single_parent(
    product_id: str,
    sources: Mapping[str, tuple[ProductDataSource, ...]],
    *,
    rated_points: tuple[RatedPoint, ...] = (),
    performance_maps: tuple[PerformanceMap, ...] = (),
    operating_envelopes: tuple[OperatingEnvelope, ...] = (),
) -> None:
    source_tuple = sources.get(product_id, ())
    if not source_tuple:
        raise ValueError("product has no valid data_sources")
    # Product-wide validation is completed by the caller with the real basic product.
    source_ids = {source.source_id for source in source_tuple}
    parents: tuple[RatedPoint | PerformanceMap | OperatingEnvelope, ...] = (
        *rated_points,
        *performance_maps,
        *operating_envelopes,
    )
    for parent in parents:
        source_id = parent.source_id
        if source_id not in source_ids:
            raise ValueError(f"unresolved or cross-product parent source_id: {source_id}")
    for rated in rated_points:
        _validate_values_sources(rated.conditions + rated.outputs, source_ids)
    for performance_map in performance_maps:
        _validate_values_sources(performance_map.fixed_conditions, source_ids)
        for axis in performance_map.axes:
            if axis.source_id not in source_ids:
                raise ValueError(f"unresolved or cross-product axis source_id: {axis.source_id}")
        for point in performance_map.points:
            if point.source_id not in source_ids:
                raise ValueError(f"unresolved or cross-product point source_id: {point.source_id}")
            _validate_values_sources(point.coordinates + point.outputs, source_ids)
    for envelope in operating_envelopes:
        _validate_values_sources(envelope.fixed_conditions, source_ids)
        for axis in envelope.axes:
            if axis.source_id not in source_ids:
                raise ValueError(f"unresolved or cross-product axis source_id: {axis.source_id}")
        for vertex in envelope.boundary_vertices:
            if vertex.source_id not in source_ids:
                raise ValueError(
                    f"unresolved or cross-product vertex source_id: {vertex.source_id}"
                )
            _validate_values_sources(vertex.coordinates, source_ids)


def _validate_values_sources(values: Iterable[ProductDataValue], source_ids: set[str]) -> None:
    for value in values:
        if value.source_id not in source_ids:
            raise ValueError(f"unresolved or cross-product value source_id: {value.source_id}")
        tolerance = value.tolerance.value
        if tolerance is not None and tolerance.source_id not in source_ids:
            raise ValueError(
                f"unresolved or cross-product tolerance source_id: {tolerance.source_id}"
            )


def _unique_parents(
    rows: list[SheetRow],
    id_column: str,
    product_ids: set[str],
    relative_path: str,
    diagnostics: list[str],
) -> dict[str, SheetRow]:
    result: dict[str, SheetRow] = {}
    duplicates: set[str] = set()
    for row in rows:
        parent_id = _text_or_empty(row.values.get(id_column))
        product_id = _text_or_empty(row.values.get("product_id"))
        if product_id not in product_ids:
            diagnostics.append(
                _row_diagnostic(relative_path, row, id_column, parent_id, "unknown product_id")
            )
            continue
        if not parent_id:
            diagnostics.append(
                _row_diagnostic(relative_path, row, id_column, "<missing>", "missing parent ID")
            )
            continue
        if parent_id in result:
            duplicates.add(parent_id)
            diagnostics.append(
                _row_diagnostic(relative_path, row, id_column, parent_id, "duplicate parent ID")
            )
        else:
            result[parent_id] = row
    for parent_id in duplicates:
        result.pop(parent_id, None)
    return result


def _unique_rows_by_id(
    rows: list[SheetRow], id_column: str, relative_path: str, diagnostics: list[str]
) -> dict[str, SheetRow]:
    result: dict[str, SheetRow] = {}
    for item_id, matching_rows in _group_rows(rows, id_column).items():
        if item_id and len(matching_rows) == 1:
            result[item_id] = matching_rows[0]
            continue
        for row in matching_rows:
            map_id = _text_or_empty(row.values.get("map_id")) or "<missing>"
            diagnostics.append(
                _row_diagnostic(
                    relative_path,
                    row,
                    id_column,
                    item_id or "<missing>",
                    f"duplicate or missing ID; map_id={map_id}",
                )
            )
    return result


def _group_rows(rows: list[SheetRow], key: str) -> dict[str, list[SheetRow]]:
    result: dict[str, list[SheetRow]] = defaultdict(list)
    for row in rows:
        result[_text_or_empty(row.values.get(key))].append(row)
    return result


def _group_mapping_values(rows: Mapping[str, SheetRow], key: str) -> dict[str, list[SheetRow]]:
    result: dict[str, list[SheetRow]] = defaultdict(list)
    for row in rows.values():
        result[_text_or_empty(row.values.get(key))].append(row)
    return result


def _orphan_rows(
    rows: Mapping[str, list[SheetRow]],
    parents: Mapping[str, SheetRow],
    relative_path: str,
    kind: str,
    diagnostics: list[str],
) -> None:
    for parent_id, items in rows.items():
        if parent_id in parents:
            continue
        for row in items:
            diagnostics.append(
                _row_diagnostic(
                    relative_path,
                    row,
                    kind,
                    parent_id or "<missing>",
                    "unresolved parent ID",
                )
            )


def _orphan_point_rows(
    points: Mapping[str, SheetRow],
    parents: Mapping[str, SheetRow],
    values: Mapping[str, list[SheetRow]],
    relative_path: str,
    diagnostics: list[str],
) -> None:
    for _point_id, row in points.items():
        map_id = _text_or_empty(row.values.get("map_id"))
        if map_id not in parents:
            diagnostics.append(
                _row_diagnostic(
                    relative_path,
                    row,
                    "map",
                    map_id or "<missing>",
                    "unresolved parent ID",
                )
            )
    for point_id, rows in values.items():
        if point_id not in points:
            for row in rows:
                diagnostics.append(
                    _row_diagnostic(
                        relative_path,
                        row,
                        "point",
                        point_id or "<missing>",
                        "unresolved point_id",
                    )
                )


def _sort_values(values: tuple[ProductDataValue, ...]) -> tuple[ProductDataValue, ...]:
    order = {name: index for index, name in enumerate(CanonicalValueName)}
    return tuple(sorted(values, key=lambda item: (order[item.canonical_name], item.value_id)))


def _canonical_refrigerant(value: object) -> str:
    original = _text(value, "refrigerant_label")
    try:
        return _REFRIGERANT_ALIASES[original.casefold()]
    except KeyError as exc:
        raise ValueError(f"unapproved refrigerant alias: {original!r}") from exc


def _json_text_tuple(value: object, field: str, *, nonempty: bool = False) -> tuple[str, ...]:
    if _blank(value):
        decoded: object = []
    elif isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{field} must be a JSON array of strings") from exc
    else:
        raise ValueError(f"{field} must be a JSON array of strings")
    if not isinstance(decoded, list) or any(
        not isinstance(item, str) or not item.strip() for item in decoded
    ):
        raise ValueError(f"{field} must be a JSON array of non-empty strings")
    result = tuple(dict.fromkeys(item.strip() for item in decoded))
    if nonempty and not result:
        raise ValueError(f"{field} must not be empty")
    return result


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be an integer")
    number = float(value)
    if not math.isfinite(number) or not number.is_integer():
        raise ValueError(f"{field} must be an integer")
    return int(number)


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be a finite number")
    return number


def _boolean(value: object, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().casefold() in {"true", "false"}:
        return value.strip().casefold() == "true"
    raise ValueError(f"{field} must be TRUE or FALSE")


def _forbidden(value: object) -> Literal["FORBIDDEN"]:
    text = _text(value, "extrapolation")
    if text != "FORBIDDEN":
        raise ValueError("extrapolation must be FORBIDDEN")
    return "FORBIDDEN"


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value.strip()


def _text_or_empty(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _optional_text(value: object) -> str | None:
    if _blank(value):
        return None
    return _text(value, "optional text")


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _row_diagnostic(
    relative_path: str,
    row: SheetRow,
    kind: str,
    record_id: str,
    message: str,
) -> str:
    return _diagnostic(relative_path, row.sheet, row.row, kind, record_id, message)


def _diagnostic(
    relative_path: str,
    sheet: str,
    row: int,
    kind: str,
    record_id: str,
    message: str,
) -> str:
    location = f"{relative_path}:{sheet}" + (f"!{row}" if row else "")
    return f"{location}: {kind} {record_id}: {message}"


def _validation_message(exc: ValidationError) -> str:
    errors = exc.errors(include_url=False)
    if not errors:
        return str(exc)
    return "; ".join(str(error["msg"]) for error in errors)
