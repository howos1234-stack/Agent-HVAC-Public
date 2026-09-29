"""Evidence-aware manufacturer comparison tests; all fixtures remain synthetic."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_hvac.components.manufacturer_validation import (
    ManufacturerValidationError,
    ManufacturerValidationRequest,
    ManufacturerValidationStatus,
    evaluate_manufacturer_validation,
)
from agent_hvac.schemas.components import ProductDataValue, ProductRecord
from agent_hvac.utils.units import Quantity

FIXTURE = Path(__file__).parents[1] / "fixtures" / "compressor_product_v020.json"


@pytest.fixture
def product() -> ProductRecord:
    return ProductRecord.model_validate_json(FIXTURE.read_text(encoding="utf-8"))


def _output(product: ProductRecord, name: str = "input_power") -> ProductDataValue:
    return next(
        value
        for value in product.performance_maps[0].points[0].outputs
        if value.canonical_name.value == name
    )


def _outputs(product: ProductRecord) -> tuple[ProductDataValue, ...]:
    return product.performance_maps[0].points[0].outputs


def _request(
    product: ProductRecord,
    *,
    output_name: str = "input_power",
    value: float = 1000.0,
    unit: str = "W",
    **updates: object,
) -> ManufacturerValidationRequest:
    data: dict[str, object] = {
        "product": product,
        "record_id": "cmp-map-1:point-00",
        "model_path": "PERFORMANCE_MAP",
        "expected_outputs": _outputs(product),
        "calculated_outputs": {
            output_name: Quantity(value=value, unit=unit),
            "mass_flow": Quantity(value=0.08, unit="kg/s"),
        },
    }
    data.update(updates)
    return ManufacturerValidationRequest(**data)  # type: ignore[arg-type]


def _production_like(product: ProductRecord, *, tolerance: dict[str, object]) -> ProductRecord:
    """Create a non-mock contract fixture only to test mechanics, never manufacturer truth."""
    raw = deepcopy(product.model_dump(mode="json"))
    raw["is_mock"] = False
    output = next(
        value
        for value in raw["performance_maps"][0]["points"][0]["outputs"]
        if value["canonical_name"] == "input_power"
    )
    output["tolerance"] = tolerance
    flow = next(
        value
        for value in raw["performance_maps"][0]["points"][0]["outputs"]
        if value["canonical_name"] == "mass_flow"
    )
    flow["tolerance"] = {
        "value": {
            "kind": "ABSOLUTE",
            "value": {"value": 0.0, "unit": "kg/s"},
            "reference": "MEASURED_VALUE",
            "source_id": "src-map-1",
        },
        "absence_reason": None,
        "accuracy_validation": "VERIFIABLE",
    }
    return ProductRecord.model_validate(raw)


def test_mock_product_is_blocked_and_never_becomes_manufacturer_pass(
    product: ProductRecord,
) -> None:
    report = evaluate_manufacturer_validation(_request(product))

    assert report.status == ManufacturerValidationStatus.BLOCKED
    assert report.is_mock is True
    assert report.comparisons == ()
    assert report.reasons == ("mock product data cannot establish manufacturer validation",)
    assert report.source_ids == ("src-map-1",)


def test_missing_source_tolerance_records_difference_as_not_verifiable(
    product: ProductRecord,
) -> None:
    raw = deepcopy(product.model_dump(mode="json"))
    raw["is_mock"] = False
    production_like = ProductRecord.model_validate(raw)

    report = evaluate_manufacturer_validation(_request(production_like, value=1001.0))

    assert report.status == ManufacturerValidationStatus.NOT_VERIFIABLE
    comparison = report.comparisons[0]
    assert comparison.absolute_error == pytest.approx(1.0, rel=0.0, abs=0.0)
    assert comparison.allowed_error is None
    assert comparison.expected_source_id == "src-map-1"
    assert comparison.tolerance_source_id is None


@pytest.mark.parametrize(
    ("calculated", "expected_status"),
    [
        (1009.0, ManufacturerValidationStatus.PASS),
        (1011.0, ManufacturerValidationStatus.FAIL),
    ],
)
def test_absolute_source_tolerance_controls_pass_or_fail(
    product: ProductRecord,
    calculated: float,
    expected_status: ManufacturerValidationStatus,
) -> None:
    evidence = _production_like(
        product,
        tolerance={
            "value": {
                "kind": "ABSOLUTE",
                "value": {"value": 10.0, "unit": "W"},
                "reference": "MEASURED_VALUE",
                "source_id": "src-map-1",
            },
            "absence_reason": None,
            "accuracy_validation": "VERIFIABLE",
        },
    )

    report = evaluate_manufacturer_validation(_request(evidence, value=calculated))

    assert report.status == expected_status
    assert report.comparisons[0].allowed_error == pytest.approx(10.0, rel=0.0, abs=0.0)
    assert report.comparisons[0].tolerance_source_id == "src-map-1"


@pytest.mark.parametrize(
    ("kind", "tolerance_value", "tolerance_unit"),
    [("RELATIVE", 0.01, "dimensionless"), ("PERCENT", 1.0, "percent")],
)
def test_relative_and_percent_tolerances_use_the_sourced_reference(
    product: ProductRecord,
    kind: str,
    tolerance_value: float,
    tolerance_unit: str,
) -> None:
    evidence = _production_like(
        product,
        tolerance={
            "value": {
                "kind": kind,
                "value": {"value": tolerance_value, "unit": tolerance_unit},
                "reference": "RATED_VALUE",
                "reference_value": {"value": 1000.0, "unit": "W"},
                "source_id": "src-map-1",
            },
            "absence_reason": None,
            "accuracy_validation": "VERIFIABLE",
        },
    )

    report = evaluate_manufacturer_validation(_request(evidence, value=1010.0))

    assert report.status == ManufacturerValidationStatus.PASS
    assert report.comparisons[0].allowed_error == pytest.approx(10.0, rel=0.0, abs=1e-12)


def test_fail_takes_precedence_when_other_output_is_not_verifiable(
    product: ProductRecord,
) -> None:
    evidence = _production_like(
        product,
        tolerance={
            "value": {
                "kind": "ABSOLUTE",
                "value": {"value": 1.0, "unit": "W"},
                "reference": "MEASURED_VALUE",
                "source_id": "src-map-1",
            },
            "absence_reason": None,
            "accuracy_validation": "VERIFIABLE",
        },
    )
    raw = evidence.model_dump(mode="json")
    flow_raw = next(
        value
        for value in raw["performance_maps"][0]["points"][0]["outputs"]
        if value["canonical_name"] == "mass_flow"
    )
    flow_raw["tolerance"] = {
        "value": None,
        "absence_reason": "NOT_STATED_IN_SOURCE",
        "accuracy_validation": "NOT_VERIFIABLE",
    }
    evidence = ProductRecord.model_validate(raw)
    flow = _output(evidence, "mass_flow")
    request = ManufacturerValidationRequest(
        product=evidence,
        record_id="cmp-map-1:point-00",
        model_path="PERFORMANCE_MAP",
        expected_outputs=(_output(evidence), flow),
        calculated_outputs={
            "input_power": Quantity(value=1002.0, unit="W"),
            "mass_flow": Quantity(value=0.08, unit="kg/s"),
        },
    )

    report = evaluate_manufacturer_validation(request)

    assert report.status == ManufacturerValidationStatus.FAIL
    assert [item.status for item in report.comparisons] == [
        ManufacturerValidationStatus.FAIL,
        ManufacturerValidationStatus.NOT_VERIFIABLE,
    ]


def test_blockers_and_model_non_applicability_are_explicit(product: ProductRecord) -> None:
    production_like = product.model_copy(update={"is_mock": False})
    blocked = evaluate_manufacturer_validation(
        _request(
            production_like,
            blockers=("pressure basis is unverified", "usage rights are unverified"),
        )
    )
    not_applicable = evaluate_manufacturer_validation(
        _request(
            production_like,
            model_applicable=False,
            applicability_reason="wet crossflow coil is outside the constant-UA dry model",
        )
    )

    assert blocked.status == ManufacturerValidationStatus.BLOCKED
    assert blocked.reasons == (
        "pressure basis is unverified",
        "usage rights are unverified",
    )
    assert not_applicable.status == ManufacturerValidationStatus.MODEL_NOT_APPLICABLE
    assert "wet crossflow coil" in not_applicable.reasons[0]


def test_missing_output_and_invalid_calculated_value_are_not_hidden(
    product: ProductRecord,
) -> None:
    production_like = product.model_copy(update={"is_mock": False})
    missing = evaluate_manufacturer_validation(_request(production_like, calculated_outputs={}))
    assert missing.status == ManufacturerValidationStatus.BLOCKED
    assert "missing" in missing.reasons[0]

    with pytest.raises(ManufacturerValidationError, match="incompatible"):
        evaluate_manufacturer_validation(_request(production_like, unit="K"))
    with pytest.raises(ValidationError, match="finite"):
        _request(production_like, value=float("inf"))


def test_duplicate_expected_output_is_rejected(product: ProductRecord) -> None:
    output = _output(product)
    request = ManufacturerValidationRequest(
        product=product,
        record_id="duplicate",
        model_path="PERFORMANCE_MAP",
        expected_outputs=(output, output),
        calculated_outputs={"input_power": Quantity(value=1000.0, unit="W")},
    )
    with pytest.raises(ManufacturerValidationError, match="duplicate"):
        evaluate_manufacturer_validation(request)


@pytest.mark.parametrize(
    ("field", "bad_id", "message"),
    [
        ("record", "missing-record", "does not exist"),
        ("value", "missing-value", "exactly match"),
        ("source", "missing-source", "expected source_id.*does not exist"),
        ("tolerance_source", "missing-tolerance-source", "tolerance source_id.*does not exist"),
    ],
)
def test_detached_or_unresolved_evidence_cannot_pass(
    product: ProductRecord,
    field: str,
    bad_id: str,
    message: str,
) -> None:
    evidence = _production_like(
        product,
        tolerance={
            "value": {
                "kind": "ABSOLUTE",
                "value": {"value": 10.0, "unit": "W"},
                "reference": "MEASURED_VALUE",
                "source_id": "src-map-1",
            },
            "absence_reason": None,
            "accuracy_validation": "VERIFIABLE",
        },
    )
    if field == "record":
        request = _request(evidence, record_id=bad_id)
    else:
        raw = _output(evidence).model_dump(mode="json")
        if field == "value":
            raw["value_id"] = bad_id
        elif field == "source":
            raw["source_id"] = bad_id
        else:
            raw["tolerance"]["value"]["source_id"] = bad_id
        detached = type(_output(evidence)).model_validate(raw)
        request = _request(
            evidence,
            expected_outputs=(detached, _output(evidence, "mass_flow")),
        )

    with pytest.raises(ManufacturerValidationError, match=message):
        evaluate_manufacturer_validation(request)


def test_overflowing_error_and_tolerance_cannot_become_pass(product: ProductRecord) -> None:
    evidence = _production_like(
        product,
        tolerance={
            "value": {
                "kind": "RELATIVE",
                "value": {"value": 1e308, "unit": "dimensionless"},
                "reference": "RATED_VALUE",
                "reference_value": {"value": 1e308, "unit": "W"},
                "source_id": "src-map-1",
            },
            "absence_reason": None,
            "accuracy_validation": "VERIFIABLE",
        },
    )
    raw = evidence.model_dump(mode="json")
    output = next(
        value
        for value in raw["performance_maps"][0]["points"][0]["outputs"]
        if value["canonical_name"] == "input_power"
    )
    output["original_value"] = 1e308
    output["value_si"]["value"] = 1e308
    evidence = ProductRecord.model_validate(raw)

    with pytest.raises(ManufacturerValidationError, match="overflowed"):
        evaluate_manufacturer_validation(_request(evidence, value=-1e308))

    with pytest.raises(ManufacturerValidationError, match="allowed error.*not finite"):
        evaluate_manufacturer_validation(_request(evidence, value=1e308))


def test_partial_or_ineligible_record_cannot_be_reported_as_pass(product: ProductRecord) -> None:
    evidence = _production_like(
        product,
        tolerance={
            "value": {
                "kind": "ABSOLUTE",
                "value": {"value": 1.0, "unit": "W"},
                "reference": "MEASURED_VALUE",
                "source_id": "src-map-1",
            },
            "absence_reason": None,
            "accuracy_validation": "VERIFIABLE",
        },
    )
    with pytest.raises(ManufacturerValidationError, match="exactly match"):
        evaluate_manufacturer_validation(_request(evidence, expected_outputs=(_output(evidence),)))

    raw = evidence.model_dump(mode="json")
    raw["performance_maps"][0]["use_status"] = {
        "source_preserved": True,
        "structure_valid": True,
        "automatic_selection": "INELIGIBLE",
        "reasons": ["REQUIRED_OUTPUT_MISSING"],
    }
    ineligible = ProductRecord.model_validate(raw)
    with pytest.raises(ManufacturerValidationError, match="not ELIGIBLE"):
        evaluate_manufacturer_validation(_request(ineligible))
