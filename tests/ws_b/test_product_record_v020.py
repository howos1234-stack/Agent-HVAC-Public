import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from agent_hvac.schemas.components import (
    DerivedMethod,
    MapAxis,
    OperatingEnvelope,
    PerformanceMap,
    ProductRecord,
)
from agent_hvac.utils.units import Quantity

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "docs" / "workstreams" / "schema" / "ProductRecord.schema.json"
FixtureData = Callable[[str], dict[str, Any]]


def _value(value_id: str, name: str, value: float, unit: str) -> dict[str, Any]:
    return {
        "value_id": value_id,
        "canonical_name": name,
        "original_name": name,
        "original_value": value,
        "original_unit": unit,
        "value_si": {"value": value, "unit": unit},
        "source_id": "src-valve",
        "tolerance": {
            "value": None,
            "absence_reason": "NOT_STATED_IN_SOURCE",
            "accuracy_validation": "NOT_VERIFIABLE",
        },
    }


def _axis(
    axis_id: str,
    order: int,
    name: str,
    kind: str,
    unit: str,
    values: tuple[float, ...],
) -> dict[str, Any]:
    return {
        "axis_id": axis_id,
        "order": order,
        "canonical_name": name,
        "native_name": name,
        "role": "CANONICAL",
        "physical_kind": kind,
        "original_unit": unit,
        "canonical_unit": unit,
        "original_values": values,
        "values_si": values,
        "source_id": "src-valve",
    }


def _append_axis(
    data: dict[str, Any],
    *,
    name: str,
    kind: str,
    unit: str,
    values: tuple[float, ...],
) -> dict[str, Any]:
    updated = copy.deepcopy(data)
    updated["axes"].append(
        _axis(f"extra-axis-{name}", len(updated["axes"]), name, kind, unit, values)
    )
    points: list[dict[str, Any]] = []
    for point in updated["points"]:
        for value_index, value in enumerate(values):
            expanded = copy.deepcopy(point)
            suffix = f"-{name}-{value_index}"
            expanded["point_id"] += suffix
            for item in expanded["coordinates"] + expanded["outputs"]:
                item["value_id"] += suffix
            expanded["coordinates"].append(
                _value(f"{expanded['point_id']}-{name}", name, value, unit)
            )
            points.append(expanded)
    updated["points"] = points
    return updated


def _envelope_payload(vertices: tuple[tuple[float, float], ...]) -> dict[str, Any]:
    x_values = tuple(sorted({point[0] for point in vertices}))
    y_values = tuple(sorted({point[1] for point in vertices}))
    return {
        "envelope_id": "test-envelope",
        "refrigerant": "R744",
        "original_refrigerant_label": "CO2",
        "axes": [
            _axis("envelope-x", 0, "suction_pressure", "PRESSURE", "Pa", x_values),
            _axis("envelope-y", 1, "discharge_pressure", "PRESSURE", "Pa", y_values),
        ],
        "boundary_vertices": [
            {
                "vertex_order": order,
                "coordinates": [
                    _value(f"vertex-{order}-x", "suction_pressure", x, "Pa"),
                    _value(f"vertex-{order}-y", "discharge_pressure", y, "Pa"),
                ],
                "source_id": "src-valve",
            }
            for order, (x, y) in enumerate(vertices)
        ],
        "boundary_inclusive": True,
        "source_id": "src-valve",
        "use_status": {
            "source_preserved": True,
            "structure_valid": True,
            "automatic_selection": "ELIGIBLE",
            "reasons": [],
        },
    }


def _valve_map() -> dict[str, Any]:
    axes = [
        ("inlet_pressure", "PRESSURE", "Pa", (8000000.0, 9000000.0)),
        ("outlet_pressure", "PRESSURE", "Pa", (3000000.0, 4000000.0)),
        ("opening", "OPENING_FRACTION", "dimensionless", (0.25, 0.75)),
    ]
    points: list[dict[str, Any]] = []
    point_index = 0
    for inlet in axes[0][3]:
        for outlet in axes[1][3]:
            for opening in axes[2][3]:
                points.append(
                    {
                        "point_id": f"valve-point-{point_index}",
                        "coordinates": [
                            _value(f"vp-{point_index}-in", "inlet_pressure", inlet, "Pa"),
                            _value(f"vp-{point_index}-out", "outlet_pressure", outlet, "Pa"),
                            _value(
                                f"vp-{point_index}-opening",
                                "opening",
                                opening,
                                "dimensionless",
                            ),
                        ],
                        "outputs": [
                            _value(
                                f"vp-{point_index}-flow",
                                "mass_flow",
                                0.01 + point_index / 1000,
                                "kg/s",
                            )
                        ],
                        "source_id": "src-valve",
                    }
                )
                point_index += 1
    return {
        "map_id": "valve-map-1",
        "map_kind": "EXPANSION_VALVE",
        "refrigerant": "R744",
        "original_refrigerant_label": "CO2",
        "topology": "R744_TRANSCRITICAL",
        "mode": "COOLING",
        "axes": [
            {
                "axis_id": f"valve-axis-{name}",
                "order": order,
                "canonical_name": name,
                "native_name": name,
                "role": "CANONICAL",
                "physical_kind": kind,
                "original_unit": unit,
                "canonical_unit": unit,
                "original_values": values,
                "values_si": values,
                "source_id": "src-valve",
            }
            for order, (name, kind, unit, values) in enumerate(axes)
        ],
        "fixed_conditions": [
            _value("valve-fixed-inlet-temperature", "inlet_temperature", 305.0, "K")
        ],
        "output_names": ["mass_flow"],
        "points": points,
        "interpolation": "MULTILINEAR",
        "extrapolation": "FORBIDDEN",
        "source_id": "src-valve",
        "use_status": {
            "source_preserved": True,
            "structure_valid": True,
            "automatic_selection": "ELIGIBLE",
            "reasons": [],
        },
    }


def test_v020_fixture_roundtrips_with_complete_map_and_envelope(
    fixture_data: FixtureData,
) -> None:
    record = ProductRecord.model_validate(fixture_data("compressor_product_v020"))

    assert len(record.performance_maps[0].points) == 4
    assert len(record.operating_envelopes[0].boundary_vertices) == 4
    assert ProductRecord.model_validate_json(record.model_dump_json()) == record


@pytest.mark.parametrize("fixture_name", ["compressor_product", "evaporator_product"])
def test_v010_fixture_defaults_detailed_fields_to_empty_tuples(
    fixture_name: str, fixture_data: FixtureData
) -> None:
    record = ProductRecord.model_validate(fixture_data(fixture_name))

    assert record.data_sources == ()
    assert record.rated_points == ()
    assert record.performance_maps == ()
    assert record.operating_envelopes == ()


def test_deployed_schema_is_generated_from_product_record() -> None:
    generated = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert generated == ProductRecord.model_json_schema()


def test_derived_method_requires_applicable_condition() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        DerivedMethod(
            method_id="derived-method",
            method_version="1.0.0",
            equation_ref="equation-1",
            input_value_refs=("input-value",),
            applicable_conditions=(),
        )


def test_incomplete_eligible_grid_is_rejected(fixture_data: FixtureData) -> None:
    data = fixture_data("compressor_product_v020")
    data["performance_maps"][0]["points"].pop()

    with pytest.raises(ValidationError, match="complete regular grid"):
        ProductRecord.model_validate(data)


def test_unresolved_source_reference_is_rejected(fixture_data: FixtureData) -> None:
    data = fixture_data("compressor_product_v020")
    data["performance_maps"][0]["points"][0]["outputs"][0]["source_id"] = "missing-source"

    with pytest.raises(ValidationError, match="unresolved value source_id"):
        ProductRecord.model_validate(data)


def test_duplicate_product_wide_value_id_is_rejected(fixture_data: FixtureData) -> None:
    data = fixture_data("compressor_product_v020")
    first = data["performance_maps"][0]["points"][0]["outputs"][0]["value_id"]
    data["operating_envelopes"][0]["fixed_conditions"][0]["value_id"] = first

    with pytest.raises(ValidationError, match="duplicate product-wide value_id"):
        ProductRecord.model_validate(data)


def test_component_and_map_kind_mismatch_is_rejected(fixture_data: FixtureData) -> None:
    data = fixture_data("compressor_product_v020")
    data["component_type"] = "expansion_valve"

    with pytest.raises(ValidationError, match="component_type and map_kind disagree"):
        ProductRecord.model_validate(data)


def test_missing_required_compressor_fixed_condition_is_rejected(
    fixture_data: FixtureData,
) -> None:
    data = fixture_data("compressor_product_v020")
    data["performance_maps"][0]["fixed_conditions"] = data["performance_maps"][0][
        "fixed_conditions"
    ][1:]

    with pytest.raises(ValidationError, match="fixed suction_temperature"):
        ProductRecord.model_validate(data)


def test_original_and_si_values_must_agree(fixture_data: FixtureData) -> None:
    data = fixture_data("compressor_product_v020")
    value = data["performance_maps"][0]["fixed_conditions"][0]
    value["value_si"]["value"] = 281.0

    with pytest.raises(ValidationError, match="original value/unit and value_si disagree"):
        ProductRecord.model_validate(data)

    value["value_si"] = {"value": 6.85, "unit": "degC"}
    with pytest.raises(ValidationError, match="approved SI unit 'K'"):
        ProductRecord.model_validate(data)


@pytest.mark.parametrize(
    "value_si",
    [
        {"value": 280.0, "unit": "K"},
        Quantity(value=280.0, unit="K"),
    ],
)
def test_value_si_dict_and_quantity_accept_correct_dimension(
    fixture_data: FixtureData,
    value_si: dict[str, object] | Quantity,
) -> None:
    data = fixture_data("compressor_product_v020")
    data["performance_maps"][0]["fixed_conditions"][0]["value_si"] = value_si

    record = ProductRecord.model_validate(data)

    validated = record.performance_maps[0].fixed_conditions[0].value_si
    assert validated.value == 280.0
    assert validated.unit == "K"


@pytest.mark.parametrize(
    "value_si",
    [
        {"value": 280.0, "unit": "m"},
        Quantity(value=280.0, unit="m"),
    ],
)
def test_value_si_dict_and_quantity_reject_wrong_dimension(
    fixture_data: FixtureData,
    value_si: dict[str, object] | Quantity,
) -> None:
    data = fixture_data("compressor_product_v020")
    data["performance_maps"][0]["fixed_conditions"][0]["value_si"] = value_si

    with pytest.raises(ValidationError, match="approved SI unit|incompatible with 'K'"):
        ProductRecord.model_validate(data)


def test_map_axis_requires_approved_si_unit_and_raw_si_values(
    fixture_data: FixtureData,
) -> None:
    axis = copy.deepcopy(fixture_data("compressor_product_v020")["performance_maps"][0]["axes"][0])
    axis.update(
        original_unit="bar",
        original_values=[30.0, 40.0],
        canonical_unit="bar",
        values_si=[30.0, 40.0],
    )

    with pytest.raises(ValidationError, match="approved SI unit 'Pa'"):
        MapAxis.model_validate(axis)

    axis["canonical_unit"] = "Pa"
    with pytest.raises(ValidationError, match="original_values and values_si disagree"):
        MapAxis.model_validate(axis)

    axis["values_si"] = [3000000.0, 4000000.0]
    validated = MapAxis.model_validate(axis)
    assert validated.canonical_values() == (3000000.0, 4000000.0)


@pytest.mark.parametrize("shift", [(0.0, 0.0), (3e12, 9e12)])
def test_envelope_accepts_collinear_separated_edges_rotation_and_reverse(
    shift: tuple[float, float],
) -> None:
    base = (
        (0.0, 0.0),
        (1.0, 0.0),
        (1.0, 1.0),
        (2.0, 1.0),
        (2.0, 0.0),
        (3.0, 0.0),
        (3.0, 2.0),
        (0.0, 2.0),
    )
    variants = (base, base[3:] + base[:3], tuple(reversed(base)))

    for variant in variants:
        shifted = tuple((x + shift[0], y + shift[1]) for x, y in variant)
        envelope = OperatingEnvelope.model_validate(_envelope_payload(shifted))
        assert len(envelope.boundary_vertices) == 8


def test_envelope_rejects_actual_self_intersection() -> None:
    crossing = ((0.0, 0.0), (3.0, 3.0), (0.0, 3.0), (3.0, 0.0))

    with pytest.raises(ValidationError, match="polygon must be simple"):
        OperatingEnvelope.model_validate(_envelope_payload(crossing))


def test_use_reasons_are_deduplicated_and_declaration_ordered(
    fixture_data: FixtureData,
) -> None:
    data = fixture_data("compressor_product_v020")
    status = data["performance_maps"][0]["use_status"]
    status["automatic_selection"] = "INELIGIBLE"
    status["reasons"] = [
        "REQUIRED_OUTPUT_MISSING",
        "UNSUPPORTED_AXIS",
        "REQUIRED_OUTPUT_MISSING",
    ]
    data["performance_maps"][0]["points"].pop()

    record = ProductRecord.model_validate(copy.deepcopy(data))

    assert tuple(reason.value for reason in record.performance_maps[0].use_status.reasons) == (
        "REQUIRED_OUTPUT_MISSING",
        "UNSUPPORTED_AXIS",
    )


def test_expansion_valve_contract_accepts_three_axis_regular_grid() -> None:
    performance_map = PerformanceMap.model_validate(_valve_map())

    assert len(performance_map.points) == 8


def test_expansion_valve_contract_accepts_fixed_opening() -> None:
    data = _valve_map()
    selected_opening = data["axes"][2]["values_si"][0]
    data["axes"] = data["axes"][:2]
    data["fixed_conditions"].append(
        _value("valve-fixed-opening", "opening", selected_opening, "dimensionless")
    )
    data["points"] = [
        point
        for point in data["points"]
        if point["coordinates"].pop()["value_si"]["value"] == selected_opening
    ]

    performance_map = PerformanceMap.model_validate(data)

    assert len(performance_map.axes) == 2
    assert len(performance_map.points) == 4


@pytest.mark.parametrize(
    ("name", "unit"),
    [("speed", "1/s"), ("frequency", "Hz")],
)
def test_compressor_contract_accepts_fixed_speed_or_frequency(
    fixture_data: FixtureData,
    name: str,
    unit: str,
) -> None:
    data = copy.deepcopy(fixture_data("compressor_product_v020")["performance_maps"][0])
    control = next(
        condition
        for condition in data["fixed_conditions"]
        if condition["canonical_name"] == "frequency"
    )
    control.update(
        canonical_name=name,
        original_name=name,
        original_unit=unit,
        value_si={"value": 50.0, "unit": unit},
    )

    performance_map = PerformanceMap.model_validate(data)

    assert any(value.canonical_name.value == name for value in performance_map.fixed_conditions)


@pytest.mark.parametrize(
    ("name", "kind", "unit"),
    [("speed", "ROTATIONAL_SPEED", "1/s"), ("frequency", "FREQUENCY", "Hz")],
)
def test_compressor_contract_accepts_speed_or_frequency_axis(
    fixture_data: FixtureData,
    name: str,
    kind: str,
    unit: str,
) -> None:
    data = copy.deepcopy(fixture_data("compressor_product_v020")["performance_maps"][0])
    data["fixed_conditions"] = [
        condition
        for condition in data["fixed_conditions"]
        if condition["canonical_name"] not in {"speed", "frequency"}
    ]
    data = _append_axis(data, name=name, kind=kind, unit=unit, values=(50.0, 60.0))

    performance_map = PerformanceMap.model_validate(data)

    assert tuple(axis.canonical_name.value for axis in performance_map.axes)[-1] == name


def test_eligible_map_rejects_duplicate_canonical_axis_name() -> None:
    data = _append_axis(
        _valve_map(),
        name="opening",
        kind="OPENING_FRACTION",
        unit="dimensionless",
        values=(0.1, 0.9),
    )

    with pytest.raises(ValidationError, match="duplicate canonical_name"):
        PerformanceMap.model_validate(data)


def test_eligible_map_rejects_unapproved_axis_order() -> None:
    data = _valve_map()
    data["axes"][0]["order"], data["axes"][1]["order"] = 1, 0
    for point in data["points"]:
        point["coordinates"][0], point["coordinates"][1] = (
            point["coordinates"][1],
            point["coordinates"][0],
        )

    with pytest.raises(ValidationError, match="unsupported canonical axis set or order"):
        PerformanceMap.model_validate(data)


@pytest.mark.parametrize("map_kind", ["compressor", "valve"])
def test_eligible_map_rejects_unapproved_extra_axis(
    fixture_data: FixtureData,
    map_kind: str,
) -> None:
    if map_kind == "compressor":
        data = copy.deepcopy(fixture_data("compressor_product_v020")["performance_maps"][0])
        data = _append_axis(
            data,
            name="opening",
            kind="OPENING_FRACTION",
            unit="dimensionless",
            values=(0.25, 0.75),
        )
        expected = "COMPRESSOR map has an unsupported"
    else:
        data = _append_axis(
            _valve_map(),
            name="frequency",
            kind="FREQUENCY",
            unit="Hz",
            values=(50.0, 60.0),
        )
        expected = "EXPANSION_VALVE map has an unsupported"

    with pytest.raises(ValidationError, match=expected):
        PerformanceMap.model_validate(data)


def test_expansion_valve_rejects_input_power_output() -> None:
    data = _valve_map()
    data["output_names"] = ["input_power"]
    for point in data["points"]:
        point["outputs"] = [_value(f"{point['point_id']}-power", "input_power", 10.0, "W")]

    with pytest.raises(ValidationError, match="forbids input_power"):
        PerformanceMap.model_validate(data)


def test_expansion_valve_rejects_reversed_pressure_drop() -> None:
    data = _valve_map()
    data["axes"][0]["original_values"] = [3000000.0, 4000000.0]
    data["axes"][0]["values_si"] = [3000000.0, 4000000.0]
    data["axes"][1]["original_values"] = [8000000.0, 9000000.0]
    data["axes"][1]["values_si"] = [8000000.0, 9000000.0]
    for point in data["points"]:
        original_inlet = point["coordinates"][0]["original_value"]
        original_outlet = point["coordinates"][1]["original_value"]
        point["coordinates"][0] = _value(
            f"{point['point_id']}-bad-in", "inlet_pressure", original_outlet, "Pa"
        )
        point["coordinates"][1] = _value(
            f"{point['point_id']}-bad-out", "outlet_pressure", original_inlet, "Pa"
        )

    with pytest.raises(ValidationError, match="inlet_pressure > outlet_pressure"):
        PerformanceMap.model_validate(data)
