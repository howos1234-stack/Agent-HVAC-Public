"""Deterministic comparison of component predictions with sourced manufacturer values.

This module evaluates evidence; it does not create product data, tolerances, or missing
operating conditions.  It intentionally remains an internal WS-A implementation rather
than extending the frozen common result contracts.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

import pint

from agent_hvac.schemas.components import (
    AutomaticSelectionStatus,
    ProductDataValue,
    ProductRecord,
    ToleranceKind,
    ToleranceReference,
    ToleranceSpec,
)
from agent_hvac.utils.exceptions import HVACError
from agent_hvac.utils.units import Quantity

_UNITS: pint.UnitRegistry[float] = pint.UnitRegistry()


class ManufacturerValidationError(HVACError):
    """The validation request itself is malformed or inconsistent."""


class ManufacturerValidationStatus(StrEnum):
    """Evidence-aware outcome; only PASS establishes numerical agreement."""

    PASS = "PASS"
    FAIL = "FAIL"
    NOT_VERIFIABLE = "NOT_VERIFIABLE"
    MODEL_NOT_APPLICABLE = "MODEL_NOT_APPLICABLE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ManufacturerOutputComparison:
    """One calculated output compared in the source value's canonical SI unit."""

    canonical_name: str
    expected_value: float
    calculated_value: float
    unit: str
    absolute_error: float
    allowed_error: float | None
    status: ManufacturerValidationStatus
    expected_value_id: str
    expected_source_id: str
    tolerance_source_id: str | None
    message: str


@dataclass(frozen=True)
class ManufacturerValidationRequest:
    """Inputs already selected and calculated by component-specific deterministic code."""

    product: ProductRecord
    record_id: str
    model_path: str
    expected_outputs: tuple[ProductDataValue, ...]
    calculated_outputs: Mapping[str, Quantity]
    model_applicable: bool = True
    applicability_reason: str | None = None
    blockers: tuple[str, ...] = ()


@dataclass(frozen=True)
class ManufacturerValidationReport:
    """Traceable case result kept distinct from P06/Gate completion."""

    status: ManufacturerValidationStatus
    product_id: str
    component_type: str
    manufacturer: str
    model: str
    record_id: str
    model_path: str
    is_mock: bool
    comparisons: tuple[ManufacturerOutputComparison, ...]
    source_ids: tuple[str, ...]
    reasons: tuple[str, ...]


def evaluate_manufacturer_validation(
    request: ManufacturerValidationRequest,
) -> ManufacturerValidationReport:
    """Compare outputs without inventing tolerance or treating mock evidence as real."""
    _validate_request(request)
    source_ids = tuple(
        dict.fromkeys(
            source_id
            for value in request.expected_outputs
            for source_id in _value_source_ids(value)
        )
    )
    if request.blockers:
        return _report(
            request,
            ManufacturerValidationStatus.BLOCKED,
            source_ids,
            reasons=request.blockers,
        )
    if request.product.is_mock:
        return _report(
            request,
            ManufacturerValidationStatus.BLOCKED,
            source_ids,
            reasons=("mock product data cannot establish manufacturer validation",),
        )
    if not request.model_applicable:
        return _report(
            request,
            ManufacturerValidationStatus.MODEL_NOT_APPLICABLE,
            source_ids,
            reasons=(request.applicability_reason or "component model is not applicable",),
        )

    missing = sorted(
        value.canonical_name.value
        for value in request.expected_outputs
        if value.canonical_name.value not in request.calculated_outputs
    )
    if missing:
        return _report(
            request,
            ManufacturerValidationStatus.BLOCKED,
            source_ids,
            reasons=(f"calculated outputs are missing {missing!r}",),
        )

    comparisons = tuple(
        _compare_output(value, request.calculated_outputs[value.canonical_name.value])
        for value in request.expected_outputs
    )
    if any(item.status == ManufacturerValidationStatus.FAIL for item in comparisons):
        status = ManufacturerValidationStatus.FAIL
    elif any(item.status == ManufacturerValidationStatus.NOT_VERIFIABLE for item in comparisons):
        status = ManufacturerValidationStatus.NOT_VERIFIABLE
    else:
        status = ManufacturerValidationStatus.PASS
    return _report(request, status, source_ids, comparisons=comparisons)


def _validate_request(request: ManufacturerValidationRequest) -> None:
    if not request.record_id.strip() or not request.model_path.strip():
        raise ManufacturerValidationError("record_id and model_path must be non-empty")
    if not request.expected_outputs:
        raise ManufacturerValidationError("at least one expected output is required")
    names = [value.canonical_name.value for value in request.expected_outputs]
    if len(names) != len(set(names)):
        raise ManufacturerValidationError("expected outputs contain duplicate canonical names")
    if request.model_applicable and request.applicability_reason is not None:
        raise ManufacturerValidationError(
            "applicability_reason is only valid when model_applicable is false"
        )
    if not request.model_applicable and request.blockers:
        raise ManufacturerValidationError(
            "use either an applicability result or execution blockers, not both"
        )
    try:
        ProductRecord.model_validate(request.product.model_dump(mode="json"))
    except ValueError as exc:
        raise ManufacturerValidationError(
            "product must pass production contract validation"
        ) from exc
    _validate_evidence_links(request)


def _validate_evidence_links(request: ManufacturerValidationRequest) -> None:
    """Require requested evidence to be an exact member of the named product record."""
    records: dict[str, tuple[tuple[ProductDataValue, ...], bool]] = {}

    def add(
        record_id: str,
        values: tuple[ProductDataValue, ...],
        eligible: bool,
    ) -> None:
        if record_id in records:
            raise ManufacturerValidationError(f"ambiguous product record_id {record_id!r}")
        records[record_id] = (values, eligible)

    for rated in request.product.rated_points:
        add(
            rated.rated_point_id,
            rated.outputs,
            rated.use_status.automatic_selection == AutomaticSelectionStatus.ELIGIBLE,
        )
    for performance_map in request.product.performance_maps:
        for point in performance_map.points:
            add(
                f"{performance_map.map_id}:{point.point_id}",
                point.outputs,
                performance_map.use_status.automatic_selection == AutomaticSelectionStatus.ELIGIBLE,
            )

    record = records.get(request.record_id)
    if record is None:
        raise ManufacturerValidationError(
            f"record_id {request.record_id!r} does not exist in product "
            f"{request.product.product_id!r}"
        )
    record_values, eligible = record
    if not eligible:
        raise ManufacturerValidationError(
            f"record_id {request.record_id!r} is not ELIGIBLE for manufacturer validation"
        )
    by_id = {value.value_id: value for value in record_values}
    requested_ids = {value.value_id for value in request.expected_outputs}
    if requested_ids != set(by_id):
        raise ManufacturerValidationError(
            f"expected outputs must exactly match record {request.record_id!r} outputs"
        )
    source_ids = {source.source_id for source in request.product.data_sources}
    for expected in request.expected_outputs:
        stored = by_id.get(expected.value_id)
        if stored is None:
            raise ManufacturerValidationError(
                f"expected value {expected.value_id!r} is not the stored value in record "
                f"{request.record_id!r}"
            )
        if expected.source_id not in source_ids:
            raise ManufacturerValidationError(
                f"expected source_id {expected.source_id!r} does not exist in product"
            )
        tolerance = expected.tolerance.value
        if tolerance is not None and tolerance.source_id not in source_ids:
            raise ManufacturerValidationError(
                f"tolerance source_id {tolerance.source_id!r} does not exist in product"
            )
        if stored != expected:
            raise ManufacturerValidationError(
                f"expected value {expected.value_id!r} is not the stored value in record "
                f"{request.record_id!r}"
            )


def _compare_output(
    expected: ProductDataValue,
    calculated: Quantity,
) -> ManufacturerOutputComparison:
    unit = expected.value_si.unit
    try:
        calculated_value = float(
            _UNITS.Quantity(calculated.value, calculated.unit).to(unit).magnitude
        )
    except (pint.errors.PintError, TypeError, ValueError) as exc:
        raise ManufacturerValidationError(
            f"calculated output {expected.canonical_name.value!r} is incompatible with {unit!r}"
        ) from exc
    if not math.isfinite(calculated_value):
        raise ManufacturerValidationError("calculated outputs must be finite")

    expected_value = expected.value_si.value
    absolute_error = abs(calculated_value - expected_value)
    if not math.isfinite(absolute_error):
        raise ManufacturerValidationError(
            f"comparison for {expected.canonical_name.value!r} overflowed"
        )
    tolerance = expected.tolerance.value
    if tolerance is None:
        return ManufacturerOutputComparison(
            canonical_name=expected.canonical_name.value,
            expected_value=expected_value,
            calculated_value=calculated_value,
            unit=unit,
            absolute_error=absolute_error,
            allowed_error=None,
            status=ManufacturerValidationStatus.NOT_VERIFIABLE,
            expected_value_id=expected.value_id,
            expected_source_id=expected.source_id,
            tolerance_source_id=None,
            message=(
                "source tolerance is unavailable; numerical difference is recorded but cannot "
                "establish accuracy"
            ),
        )

    allowed_error = _allowed_error(expected_value, unit, tolerance)
    if not math.isfinite(allowed_error):
        raise ManufacturerValidationError(
            f"allowed error for {expected.canonical_name.value!r} is not finite"
        )
    within = absolute_error <= allowed_error
    return ManufacturerOutputComparison(
        canonical_name=expected.canonical_name.value,
        expected_value=expected_value,
        calculated_value=calculated_value,
        unit=unit,
        absolute_error=absolute_error,
        allowed_error=allowed_error,
        status=(ManufacturerValidationStatus.PASS if within else ManufacturerValidationStatus.FAIL),
        expected_value_id=expected.value_id,
        expected_source_id=expected.source_id,
        tolerance_source_id=tolerance.source_id,
        message=("within source tolerance" if within else "outside source tolerance"),
    )


def _allowed_error(expected_value: float, unit: str, tolerance: ToleranceSpec) -> float:
    # ProductDataValue validation already guarantees ToleranceSpec.  Keeping this helper
    # independent from Pydantic internals makes the numerical policy explicit here.
    kind = tolerance.kind
    if kind == ToleranceKind.ABSOLUTE:
        return float(
            _UNITS.Quantity(tolerance.value.value, tolerance.value.unit).to(unit).magnitude
        )

    factor = float(
        _UNITS.Quantity(tolerance.value.value, tolerance.value.unit).to("dimensionless").magnitude
    )
    if tolerance.reference == ToleranceReference.MEASURED_VALUE:
        reference = expected_value
    else:
        if tolerance.reference_value is None:  # pragma: no cover - guarded by ProductRecord
            raise ManufacturerValidationError("relative tolerance requires a reference value")
        reference = float(
            _UNITS.Quantity(
                tolerance.reference_value.value,
                tolerance.reference_value.unit,
            )
            .to(unit)
            .magnitude
        )
    return abs(reference) * factor


def _value_source_ids(value: ProductDataValue) -> tuple[str, ...]:
    tolerance = value.tolerance.value
    if tolerance is None or tolerance.source_id == value.source_id:
        return (value.source_id,)
    return (value.source_id, tolerance.source_id)


def _report(
    request: ManufacturerValidationRequest,
    status: ManufacturerValidationStatus,
    source_ids: tuple[str, ...],
    *,
    comparisons: tuple[ManufacturerOutputComparison, ...] = (),
    reasons: tuple[str, ...] = (),
) -> ManufacturerValidationReport:
    product = request.product
    return ManufacturerValidationReport(
        status=status,
        product_id=product.product_id,
        component_type=product.component_type.value,
        manufacturer=product.manufacturer,
        model=product.model,
        record_id=request.record_id,
        model_path=request.model_path,
        is_mock=product.is_mock,
        comparisons=comparisons,
        source_ids=source_ids,
        reasons=reasons,
    )
