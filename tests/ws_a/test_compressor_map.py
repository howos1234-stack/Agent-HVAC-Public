"""Compressor-specific application tests for approved production maps."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from agent_hvac.components.compressor_map import (
    CompressorMapInput,
    evaluate_compressor_map,
)
from agent_hvac.components.performance_map import PerformanceMapError
from agent_hvac.schemas.components import CanonicalValueName, ProductRecord
from agent_hvac.utils.exceptions import ComponentEnvelopeError
from agent_hvac.utils.units import Pressure, Quantity, Temperature

FIXTURE = Path(__file__).parents[1] / "fixtures" / "compressor_product_v020.json"


@pytest.fixture
def product() -> ProductRecord:
    return ProductRecord.model_validate_json(FIXTURE.read_text(encoding="utf-8"))


def _conditions(**updates: Quantity) -> dict[str, Quantity]:
    conditions = {
        "suction_pressure": Pressure(value=3_500_000.0, unit="Pa"),
        "discharge_pressure": Pressure(value=8_500_000.0, unit="Pa"),
        "suction_temperature": Temperature(value=280.0, unit="K"),
        "frequency": Quantity(value=50.0, unit="Hz"),
    }
    conditions.update(updates)
    return conditions


def _input(product: ProductRecord, **updates: Quantity) -> CompressorMapInput:
    return CompressorMapInput(
        product=product,
        map_id="cmp-map-1",
        envelope_id="cmp-envelope-1",
        conditions=_conditions(**updates),
    )


def test_compressor_map_interpolates_and_identifies_separate_model_path(
    product: ProductRecord,
) -> None:
    result = evaluate_compressor_map(_input(product))

    assert result.model_path == "PERFORMANCE_MAP"
    assert result.product_id == "MOCK-compressor-v020"
    assert result.is_mock is product.is_mock is True
    assert result.map_id == "cmp-map-1"
    assert result.envelope_id == "cmp-envelope-1"
    assert result.outputs["input_power"] == pytest.approx(1150.0, rel=0.0, abs=1e-12)
    assert result.outputs["mass_flow"] == pytest.approx(0.085, rel=0.0, abs=1e-12)
    assert result.output_units == {"input_power": "W", "mass_flow": "kg/s"}
    assert result.conditions_si == {
        "suction_pressure": 3_500_000.0,
        "discharge_pressure": 8_500_000.0,
        "suction_temperature": 280.0,
        "frequency": 50.0,
    }
    assert result.condition_units == {
        "suction_pressure": "Pa",
        "discharge_pressure": "Pa",
        "suction_temperature": "K",
        "frequency": "Hz",
    }


def test_compressor_map_preserves_distinct_record_source_ids(product: ProductRecord) -> None:
    payload = deepcopy(product.model_dump(mode="json"))
    performance_map = payload["performance_maps"][0]
    envelope = payload["operating_envelopes"][0]
    performance_map["source_id"] = "src-map-parent"
    performance_map["axes"][0]["source_id"] = "src-map-axis-suction"
    performance_map["axes"][1]["source_id"] = "src-map-axis-discharge"
    performance_map["fixed_conditions"][0]["source_id"] = "src-map-fixed-temp"
    performance_map["fixed_conditions"][1]["source_id"] = "src-map-fixed-frequency"
    performance_map["points"][0]["source_id"] = "src-point-00"
    performance_map["points"][0]["outputs"][0]["source_id"] = "src-output-power"
    performance_map["points"][0]["outputs"][1]["source_id"] = "src-output-flow"
    envelope["source_id"] = "src-envelope-parent"
    envelope["axes"][0]["source_id"] = "src-envelope-axis-suction"
    envelope["axes"][1]["source_id"] = "src-envelope-axis-discharge"
    envelope["fixed_conditions"][0]["source_id"] = "src-envelope-fixed-temp"
    envelope["fixed_conditions"][1]["source_id"] = "src-envelope-fixed-frequency"
    envelope["boundary_vertices"][0]["source_id"] = "src-envelope-vertex-0"
    _supply_referenced_sources(payload)
    distinct_product = ProductRecord.model_validate(payload)

    result = evaluate_compressor_map(
        _input(
            distinct_product,
            suction_pressure=Pressure(value=30.0, unit="bar"),
            discharge_pressure=Pressure(value=80.0, unit="bar"),
        )
    )

    assert result.map_source_ids == ("src-map-parent",)
    assert result.map_axis_source_ids == (
        "src-map-axis-suction",
        "src-map-axis-discharge",
    )
    assert result.map_fixed_condition_source_ids == {
        "suction_temperature": "src-map-fixed-temp",
        "frequency": "src-map-fixed-frequency",
    }
    assert result.point_source_ids == ("src-point-00",)
    assert result.output_source_ids == {
        "input_power": ("src-output-power",),
        "mass_flow": ("src-output-flow",),
    }
    assert result.envelope_source_ids == ("src-envelope-parent",)
    assert result.envelope_axis_source_ids == (
        "src-envelope-axis-suction",
        "src-envelope-axis-discharge",
    )
    assert result.envelope_fixed_condition_source_ids == {
        "suction_temperature": "src-envelope-fixed-temp",
        "frequency": "src-envelope-fixed-frequency",
    }
    assert "src-envelope-vertex-0" in result.envelope_vertex_source_ids


def test_map_internal_point_outside_envelope_is_rejected(product: ProductRecord) -> None:
    envelope = product.operating_envelopes[0]
    triangular_envelope = envelope.model_copy(
        update={"boundary_vertices": envelope.boundary_vertices[:3]}
    )
    restricted_product = product.model_copy(update={"operating_envelopes": (triangular_envelope,)})

    with pytest.raises(ComponentEnvelopeError, match="outside operating envelope"):
        evaluate_compressor_map(
            _input(
                restricted_product,
                suction_pressure=Pressure(value=31.0, unit="bar"),
                discharge_pressure=Pressure(value=89.0, unit="bar"),
            )
        )


@pytest.mark.parametrize(
    "conditions",
    [
        {
            "suction_pressure": Pressure(value=3_500_000.0, unit="Pa"),
            "discharge_pressure": Pressure(value=8_500_000.0, unit="Pa"),
            "suction_temperature": Temperature(value=280.0, unit="K"),
        },
        {
            "suction_pressure": Pressure(value=3_500_000.0, unit="Pa"),
            "discharge_pressure": Pressure(value=8_500_000.0, unit="Pa"),
            "suction_temperature": Temperature(value=280.0, unit="K"),
            "frequency": Quantity(value=50.0, unit="Hz"),
            "ambient_temperature": Temperature(value=300.0, unit="K"),
        },
    ],
)
def test_missing_or_extra_operating_condition_is_not_guessed(
    product: ProductRecord, conditions: dict[str, Quantity]
) -> None:
    with pytest.raises(PerformanceMapError, match="must be exactly"):
        evaluate_compressor_map(
            CompressorMapInput(
                product=product,
                map_id="cmp-map-1",
                envelope_id="cmp-envelope-1",
                conditions=conditions,
            )
        )


def test_fixed_condition_mismatch_is_rejected(product: ProductRecord) -> None:
    with pytest.raises(PerformanceMapError, match="does not exactly match"):
        evaluate_compressor_map(_input(product, frequency=Quantity(value=60.0, unit="Hz")))


def test_failed_synthetic_candidate_cannot_reuse_previous_map_result(
    product: ProductRecord,
) -> None:
    first = evaluate_compressor_map(_input(product))

    with pytest.raises(PerformanceMapError, match="does not exactly match"):
        evaluate_compressor_map(_input(product, frequency=Quantity(value=60.0, unit="Hz")))

    repeated = evaluate_compressor_map(_input(product))
    assert repeated.outputs == first.outputs
    assert repeated.output_source_ids == first.output_source_ids
    assert repeated.is_mock is first.is_mock is True


def test_non_compressive_pressure_direction_is_rejected(product: ProductRecord) -> None:
    with pytest.raises(PerformanceMapError, match="discharge pressure must exceed"):
        evaluate_compressor_map(
            _input(
                product,
                suction_pressure=Pressure(value=8_000_000.0, unit="Pa"),
                discharge_pressure=Pressure(value=8_000_000.0, unit="Pa"),
            )
        )


@pytest.mark.parametrize(("output_index", "message"), [(0, "input_power"), (1, "mass_flow")])
def test_nonpositive_operating_output_is_rejected(
    product: ProductRecord, output_index: int, message: str
) -> None:
    performance_map = product.performance_maps[0]
    point = performance_map.points[0]
    outputs = list(point.outputs)
    outputs[output_index] = outputs[output_index].model_copy(
        update={"value_si": outputs[output_index].value_si.model_copy(update={"value": 0.0})}
    )
    changed_point = point.model_copy(update={"outputs": tuple(outputs)})
    changed_map = performance_map.model_copy(
        update={"points": (changed_point,) + performance_map.points[1:]}
    )
    changed_product = product.model_copy(update={"performance_maps": (changed_map,)})

    with pytest.raises(PerformanceMapError, match=message):
        evaluate_compressor_map(
            _input(
                changed_product,
                suction_pressure=Pressure(value=30.0, unit="bar"),
                discharge_pressure=Pressure(value=80.0, unit="bar"),
            )
        )


def test_map_and_envelope_refrigerants_must_match(product: ProductRecord) -> None:
    envelope = product.operating_envelopes[0].model_copy(update={"refrigerant": "R410A"})
    changed_product = product.model_copy(update={"operating_envelopes": (envelope,)})

    with pytest.raises(PerformanceMapError, match="refrigerants differ"):
        evaluate_compressor_map(_input(changed_product))


def test_wrong_condition_dimension_is_rejected(product: ProductRecord) -> None:
    with pytest.raises(PerformanceMapError, match="incompatible with canonical unit 'Hz'"):
        evaluate_compressor_map(_input(product, frequency=Quantity(value=50.0, unit="m")))


@pytest.mark.parametrize("temperature_k", [-1.0, 0.0])
def test_nonpositive_absolute_temperature_is_rejected(
    product: ProductRecord, temperature_k: float
) -> None:
    changed_product = _validated_product_with_fixed_condition(
        product,
        CanonicalValueName.SUCTION_TEMPERATURE,
        CanonicalValueName.SUCTION_TEMPERATURE,
        temperature_k,
        "K",
    )

    with pytest.raises(PerformanceMapError, match="above absolute zero"):
        evaluate_compressor_map(
            _input(
                changed_product,
                suction_temperature=Quantity(value=temperature_k, unit="K"),
            )
        )


@pytest.mark.parametrize(
    ("drive_name", "unit", "drive_value"),
    [
        (CanonicalValueName.FREQUENCY, "Hz", -1.0),
        (CanonicalValueName.FREQUENCY, "Hz", 0.0),
        (CanonicalValueName.SPEED, "1/s", -1.0),
        (CanonicalValueName.SPEED, "1/s", 0.0),
    ],
)
def test_nonpositive_fixed_frequency_or_speed_is_rejected(
    product: ProductRecord,
    drive_name: CanonicalValueName,
    unit: str,
    drive_value: float,
) -> None:
    changed_product = _validated_product_with_fixed_condition(
        product,
        CanonicalValueName.FREQUENCY,
        drive_name,
        drive_value,
        unit,
    )
    conditions = _conditions()
    conditions.pop(CanonicalValueName.FREQUENCY.value)
    conditions[drive_name.value] = Quantity(value=drive_value, unit=unit)

    with pytest.raises(PerformanceMapError, match="must be positive"):
        evaluate_compressor_map(
            CompressorMapInput(
                product=changed_product,
                map_id="cmp-map-1",
                envelope_id="cmp-envelope-1",
                conditions=conditions,
            )
        )


@pytest.mark.parametrize(
    ("drive_name", "unit", "physical_kind", "drive_value"),
    [
        (CanonicalValueName.FREQUENCY, "Hz", "FREQUENCY", -1.0),
        (CanonicalValueName.FREQUENCY, "Hz", "FREQUENCY", 0.0),
        (CanonicalValueName.SPEED, "1/s", "ROTATIONAL_SPEED", -1.0),
        (CanonicalValueName.SPEED, "1/s", "ROTATIONAL_SPEED", 0.0),
    ],
)
def test_nonpositive_variable_frequency_or_speed_axis_is_rejected(
    product: ProductRecord,
    drive_name: CanonicalValueName,
    unit: str,
    physical_kind: str,
    drive_value: float,
) -> None:
    changed_product = _validated_product_with_drive_axis(
        product, drive_name, unit, physical_kind, drive_value
    )
    conditions = _conditions()
    conditions[drive_name.value] = Quantity(value=drive_value, unit=unit)

    with pytest.raises(PerformanceMapError, match="must be positive"):
        evaluate_compressor_map(
            CompressorMapInput(
                product=changed_product,
                map_id="cmp-map-1",
                envelope_id="cmp-envelope-1",
                conditions=conditions,
            )
        )


def _validated_product_with_fixed_condition(
    product: ProductRecord,
    old_name: CanonicalValueName,
    new_name: CanonicalValueName,
    value: float,
    unit: str,
) -> ProductRecord:
    payload = deepcopy(product.model_dump(mode="json"))
    for parent_name in ("performance_maps", "operating_envelopes"):
        for condition in payload[parent_name][0]["fixed_conditions"]:
            if condition["canonical_name"] == old_name.value:
                condition.update(
                    {
                        "canonical_name": new_name.value,
                        "original_name": new_name.value,
                        "original_value": value,
                        "original_unit": unit,
                        "value_si": {"value": value, "unit": unit},
                    }
                )
    return ProductRecord.model_validate(payload)


def _validated_product_with_drive_axis(
    product: ProductRecord,
    drive_name: CanonicalValueName,
    unit: str,
    physical_kind: str,
    invalid_value: float,
) -> ProductRecord:
    payload = deepcopy(product.model_dump(mode="json"))
    performance_map = payload["performance_maps"][0]
    performance_map["fixed_conditions"] = [
        condition
        for condition in performance_map["fixed_conditions"]
        if condition["canonical_name"] != CanonicalValueName.FREQUENCY.value
    ]
    performance_map["axes"].append(
        {
            "axis_id": f"map-axis-{drive_name.value}",
            "order": 2,
            "canonical_name": drive_name.value,
            "native_name": drive_name.value,
            "role": "CANONICAL",
            "physical_kind": physical_kind,
            "original_unit": unit,
            "canonical_unit": unit,
            "original_values": [invalid_value, 50.0],
            "values_si": [invalid_value, 50.0],
            "source_id": "src-map-1",
        }
    )
    original_points = performance_map["points"]
    expanded_points: list[dict[str, Any]] = []
    for drive_index, drive_value in enumerate((invalid_value, 50.0)):
        for original_point in original_points:
            point = deepcopy(original_point)
            suffix = f"-{drive_name.value}-{drive_index}"
            point["point_id"] += suffix
            for value in point["coordinates"] + point["outputs"]:
                value["value_id"] += suffix
            point["coordinates"].append(
                {
                    "value_id": f"{point['point_id']}-drive",
                    "canonical_name": drive_name.value,
                    "original_name": drive_name.value,
                    "original_value": drive_value,
                    "original_unit": unit,
                    "value_si": {"value": drive_value, "unit": unit},
                    "source_id": "src-map-1",
                    "tolerance": {
                        "value": None,
                        "absence_reason": "NOT_STATED_IN_SOURCE",
                        "accuracy_validation": "NOT_VERIFIABLE",
                    },
                }
            )
            expanded_points.append(point)
    performance_map["points"] = expanded_points
    return ProductRecord.model_validate(payload)


def _supply_referenced_sources(payload: dict[str, Any]) -> None:
    source_template = payload["data_sources"][0]
    referenced: set[str] = set()

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "source_id" and isinstance(child, str):
                    referenced.add(child)
                else:
                    collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(payload["performance_maps"])
    collect(payload["operating_envelopes"])
    payload["data_sources"] = [
        {**source_template, "source_id": source_id} for source_id in sorted(referenced)
    ]
