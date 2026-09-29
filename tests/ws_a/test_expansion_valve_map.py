"""Expansion-valve application tests for approved production maps."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from agent_hvac.components.candidate_trials import (
    ComponentCandidateTrial,
    evaluate_synthetic_component_trials,
)
from agent_hvac.components.expansion_valve_map import (
    ExpansionValveMapInput,
    evaluate_expansion_valve_map,
)
from agent_hvac.components.performance_map import PerformanceMapError
from agent_hvac.physics.state import ThermoState
from agent_hvac.properties.coolprop_backend import CoolPropBackend
from agent_hvac.schemas.components import ProductRecord
from agent_hvac.utils.exceptions import ComponentEnvelopeError, InvalidPropertyStateError
from agent_hvac.utils.units import (
    Density,
    Pressure,
    Quantity,
    SpecificEnthalpy,
    SpecificEntropy,
    Temperature,
)


class RecordingBackend:
    def __init__(self, phase: str = "liquid", *, fail_pt: bool = False) -> None:
        self.phase = phase
        self.fail_pt = fail_pt
        self.pt_calls: list[tuple[str, Pressure, Temperature]] = []

    def state_pt(self, fluid: str, p: Pressure, temperature: Temperature) -> ThermoState:
        self.pt_calls.append((fluid, p, temperature))
        if self.fail_pt:
            raise InvalidPropertyStateError("synthetic invalid inlet P-T state")
        return ThermoState(
            fluid=fluid,
            pressure=p,
            temperature=temperature,
            enthalpy=SpecificEnthalpy(value=250_000.0, unit="J/kg"),
            density=Density(value=700.0, unit="kg/m^3"),
            phase=self.phase,
            entropy=SpecificEntropy(value=1_200.0, unit="J/(kg*K)"),
        )

    def state_ph(
        self, fluid: str, p: Pressure, h: SpecificEnthalpy
    ) -> ThermoState:  # pragma: no cover - a call is a test failure
        raise AssertionError("valve map application must not calculate an outlet state")

    def state_ps(
        self, fluid: str, p: Pressure, entropy: SpecificEntropy
    ) -> ThermoState:  # pragma: no cover - a call is a test failure
        raise AssertionError("valve map application must not call state_ps")


@pytest.fixture
def product() -> ProductRecord:
    return ProductRecord.model_validate(_product_payload())


def _conditions(**updates: Quantity) -> dict[str, Quantity]:
    conditions = {
        "inlet_pressure": Pressure(value=8_500_000.0, unit="Pa"),
        "outlet_pressure": Pressure(value=3_500_000.0, unit="Pa"),
        "opening": Quantity(value=0.5, unit="dimensionless"),
        "inlet_temperature": Temperature(value=305.0, unit="K"),
    }
    conditions.update(updates)
    return conditions


def _input(
    product: ProductRecord,
    backend: RecordingBackend | None = None,
    /,
    **updates: Quantity,
) -> ExpansionValveMapInput:
    return ExpansionValveMapInput(
        backend=backend or RecordingBackend(),
        product=product,
        map_id="valve-map-1",
        envelope_id="valve-envelope-1",
        conditions=_conditions(**updates),
    )


def test_valve_map_interpolates_and_keeps_outlet_flashing_out_of_scope(
    product: ProductRecord,
) -> None:
    backend = RecordingBackend(phase="supercritical_liquid")

    result = evaluate_expansion_valve_map(_input(product, backend))

    assert result.model_path == "PERFORMANCE_MAP"
    assert result.product_id == "MOCK-expansion-valve-v020"
    assert result.is_mock is product.is_mock is True
    assert result.map_id == "valve-map-1"
    assert result.envelope_id == "valve-envelope-1"
    assert result.inlet_phase == "supercritical_liquid"
    assert result.outputs == {"mass_flow": pytest.approx(0.0775, rel=0.0, abs=1e-12)}
    assert result.output_units == {"mass_flow": "kg/s"}
    assert result.conditions_si == {
        "inlet_pressure": 8_500_000.0,
        "outlet_pressure": 3_500_000.0,
        "opening": 0.5,
        "inlet_temperature": 305.0,
    }
    assert result.condition_units == {
        "inlet_pressure": "Pa",
        "outlet_pressure": "Pa",
        "opening": "dimensionless",
        "inlet_temperature": "K",
    }
    assert len(backend.pt_calls) == 1
    assert backend.pt_calls[0][0] == "R744"
    assert backend.pt_calls[0][1].value == 8_500_000.0
    assert backend.pt_calls[0][2].value == 305.0


def test_valve_map_preserves_record_source_ids(product: ProductRecord) -> None:
    result = evaluate_expansion_valve_map(_input(product))

    assert result.map_source_ids == ("src-valve",)
    assert result.map_axis_source_ids == ("src-valve", "src-valve", "src-valve")
    assert result.map_fixed_condition_source_ids == {"inlet_temperature": "src-valve"}
    assert result.point_source_ids == ("src-valve",)
    assert result.output_source_ids == {"mass_flow": ("src-valve",)}
    assert result.envelope_source_ids == ("src-valve",)
    assert result.envelope_axis_source_ids == ("src-valve", "src-valve")
    assert result.envelope_fixed_condition_source_ids == {
        "inlet_temperature": "src-valve",
        "opening": "src-valve",
    }
    assert result.envelope_vertex_source_ids == ("src-valve",)


def test_valve_map_preserves_distinct_record_source_ids(product: ProductRecord) -> None:
    payload = deepcopy(product.model_dump(mode="json"))
    performance_map = payload["performance_maps"][0]
    envelope = payload["operating_envelopes"][0]
    performance_map["source_id"] = "src-map-parent"
    for index, axis in enumerate(performance_map["axes"]):
        axis["source_id"] = f"src-map-axis-{index}"
    performance_map["fixed_conditions"][0]["source_id"] = "src-map-fixed-temperature"
    expected_point_ids: list[str] = []
    expected_output_ids: list[str] = []
    for index, point in enumerate(performance_map["points"]):
        point_source_id = f"src-map-point-{index}"
        output_source_id = f"src-map-output-{index}"
        point["source_id"] = point_source_id
        point["outputs"][0]["source_id"] = output_source_id
        expected_point_ids.append(point_source_id)
        expected_output_ids.append(output_source_id)
    envelope["source_id"] = "src-envelope-parent"
    for index, axis in enumerate(envelope["axes"]):
        axis["source_id"] = f"src-envelope-axis-{index}"
    envelope["fixed_conditions"][0]["source_id"] = "src-envelope-fixed-temperature"
    envelope["fixed_conditions"][1]["source_id"] = "src-envelope-fixed-opening"
    expected_vertex_ids: list[str] = []
    for index, vertex in enumerate(envelope["boundary_vertices"]):
        vertex_source_id = f"src-envelope-vertex-{index}"
        vertex["source_id"] = vertex_source_id
        expected_vertex_ids.append(vertex_source_id)
    _supply_referenced_sources(payload)
    distinct_product = ProductRecord.model_validate(payload)

    result = evaluate_expansion_valve_map(_input(distinct_product))

    assert result.map_source_ids == ("src-map-parent",)
    assert result.map_axis_source_ids == (
        "src-map-axis-0",
        "src-map-axis-1",
        "src-map-axis-2",
    )
    assert result.map_fixed_condition_source_ids == {
        "inlet_temperature": "src-map-fixed-temperature"
    }
    assert result.point_source_ids == tuple(sorted(expected_point_ids))
    assert result.output_source_ids == {"mass_flow": tuple(sorted(expected_output_ids))}
    assert result.envelope_source_ids == ("src-envelope-parent",)
    assert result.envelope_axis_source_ids == (
        "src-envelope-axis-0",
        "src-envelope-axis-1",
    )
    assert result.envelope_fixed_condition_source_ids == {
        "inlet_temperature": "src-envelope-fixed-temperature",
        "opening": "src-envelope-fixed-opening",
    }
    assert result.envelope_vertex_source_ids == tuple(sorted(expected_vertex_ids))


@pytest.mark.parametrize(
    ("inlet_pressure_pa", "inlet_temperature_k", "expected_phases"),
    [
        (8_500_000.0, 305.0, {"supercritical", "supercritical_liquid"}),
        (5_500_000.0, 280.0, {"liquid"}),
    ],
)
def test_real_coolprop_backend_smoke_for_valid_r744_inlet_states(
    product: ProductRecord,
    inlet_pressure_pa: float,
    inlet_temperature_k: float,
    expected_phases: set[str],
) -> None:
    connected_product = _validated_product_with_inlet_domain(
        product,
        inlet_pressure_pa=inlet_pressure_pa,
        inlet_temperature_k=inlet_temperature_k,
    )

    result = evaluate_expansion_valve_map(
        ExpansionValveMapInput(
            backend=CoolPropBackend(),
            product=connected_product,
            map_id="valve-map-1",
            envelope_id="valve-envelope-1",
            conditions=_conditions(
                inlet_pressure=Pressure(value=inlet_pressure_pa, unit="Pa"),
                inlet_temperature=Temperature(value=inlet_temperature_k, unit="K"),
            ),
        )
    )

    assert result.inlet_phase in expected_phases
    assert result.outputs["mass_flow"] == pytest.approx(0.0775, rel=0.0, abs=1e-12)


def test_fixed_opening_valve_map_is_supported(product: ProductRecord) -> None:
    payload = deepcopy(product.model_dump(mode="json"))
    performance_map = payload["performance_maps"][0]
    selected_opening = 0.25
    performance_map["axes"] = performance_map["axes"][:2]
    performance_map["fixed_conditions"].append(
        _value("valve-fixed-opening", "opening", selected_opening, "dimensionless")
    )
    selected_points = []
    for point in performance_map["points"]:
        opening = point["coordinates"].pop()
        if opening["value_si"]["value"] == selected_opening:
            selected_points.append(point)
    performance_map["points"] = selected_points
    payload["operating_envelopes"][0]["fixed_conditions"][1] = _value(
        "envelope-fixed-opening",
        "opening",
        selected_opening,
        "dimensionless",
    )
    fixed_opening_product = ProductRecord.model_validate(payload)

    result = evaluate_expansion_valve_map(
        _input(
            fixed_opening_product,
            opening=Quantity(value=selected_opening, unit="dimensionless"),
        )
    )

    assert result.outputs["mass_flow"] == pytest.approx(0.0725, rel=0.0, abs=1e-12)


def test_map_internal_point_outside_valve_envelope_is_rejected(
    product: ProductRecord,
) -> None:
    envelope = product.operating_envelopes[0]
    triangular_envelope = envelope.model_copy(
        update={"boundary_vertices": envelope.boundary_vertices[:3]}
    )
    restricted_product = product.model_copy(update={"operating_envelopes": (triangular_envelope,)})

    with pytest.raises(ComponentEnvelopeError, match="outside operating envelope"):
        evaluate_expansion_valve_map(
            _input(
                restricted_product,
                inlet_pressure=Pressure(value=8_100_000.0, unit="Pa"),
                outlet_pressure=Pressure(value=3_900_000.0, unit="Pa"),
            )
        )


@pytest.mark.parametrize(
    "conditions",
    [
        {
            "inlet_pressure": Pressure(value=8_500_000.0, unit="Pa"),
            "outlet_pressure": Pressure(value=3_500_000.0, unit="Pa"),
            "inlet_temperature": Temperature(value=305.0, unit="K"),
        },
        {
            **_conditions(),
            "ambient_temperature": Temperature(value=300.0, unit="K"),
        },
    ],
)
def test_missing_or_extra_valve_condition_is_not_guessed(
    product: ProductRecord, conditions: dict[str, Quantity]
) -> None:
    with pytest.raises(PerformanceMapError, match="must be exactly"):
        evaluate_expansion_valve_map(
            ExpansionValveMapInput(
                backend=RecordingBackend(),
                product=product,
                map_id="valve-map-1",
                envelope_id="valve-envelope-1",
                conditions=conditions,
            )
        )


def test_valve_fixed_condition_mismatch_is_rejected(product: ProductRecord) -> None:
    with pytest.raises(PerformanceMapError, match="does not exactly match"):
        evaluate_expansion_valve_map(
            _input(product, inlet_temperature=Temperature(value=304.0, unit="K"))
        )


def test_failed_synthetic_candidate_cannot_reuse_previous_valve_result(
    product: ProductRecord,
) -> None:
    first = evaluate_expansion_valve_map(_input(product))

    with pytest.raises(PerformanceMapError, match="does not exactly match"):
        evaluate_expansion_valve_map(
            _input(product, inlet_temperature=Temperature(value=304.0, unit="K"))
        )

    repeated = evaluate_expansion_valve_map(_input(product))
    assert repeated.outputs == first.outputs
    assert repeated.output_source_ids == first.output_source_ids
    assert repeated.is_mock is first.is_mock is True


def test_valve_candidate_trial_keeps_property_failure_and_sources_separate(
    product: ProductRecord,
) -> None:
    candidates = (
        ComponentCandidateTrial("valve-a", _input(product)),
        ComponentCandidateTrial("valve-b", _input(product, RecordingBackend(fail_pt=True))),
        ComponentCandidateTrial("valve-c", _input(product)),
    )

    first, rejected, last = evaluate_synthetic_component_trials(candidates)

    assert (first.status, rejected.status, last.status) == (
        "EVALUATED",
        "REJECTED",
        "EVALUATED",
    )
    assert all(outcome.is_mock for outcome in (first, rejected, last))
    assert all(outcome.record_id == "valve-map-1" for outcome in (first, rejected, last))
    assert first.result is not None and last.result is not None
    assert first.result.outputs == last.result.outputs
    assert first.result.output_source_ids == last.result.output_source_ids
    assert rejected.selected_source_ids == first.selected_source_ids
    assert rejected.result is None
    assert rejected.failure_type == "InvalidPropertyStateError"
    assert "invalid inlet" in (rejected.failure_message or "")


@pytest.mark.parametrize(
    ("inlet", "outlet"),
    [(3_500_000.0, 3_500_000.0), (3_000_000.0, 4_000_000.0)],
)
def test_nonexpanding_pressure_direction_is_rejected(
    product: ProductRecord, inlet: float, outlet: float
) -> None:
    with pytest.raises(PerformanceMapError, match="inlet pressure must exceed"):
        evaluate_expansion_valve_map(
            _input(
                product,
                inlet_pressure=Pressure(value=inlet, unit="Pa"),
                outlet_pressure=Pressure(value=outlet, unit="Pa"),
            )
        )


@pytest.mark.parametrize("phase", ["twophase", "unknown"])
def test_non_single_phase_inlet_is_rejected(product: ProductRecord, phase: str) -> None:
    with pytest.raises(PerformanceMapError, match="single-phase or supercritical"):
        evaluate_expansion_valve_map(_input(product, RecordingBackend(phase=phase)))


def test_invalid_inlet_property_state_is_not_hidden(product: ProductRecord) -> None:
    with pytest.raises(InvalidPropertyStateError, match="synthetic invalid"):
        evaluate_expansion_valve_map(_input(product, RecordingBackend(fail_pt=True)))


def test_wrong_condition_dimension_is_rejected(product: ProductRecord) -> None:
    with pytest.raises(PerformanceMapError, match="incompatible with canonical unit"):
        evaluate_expansion_valve_map(
            _input(product, inlet_temperature=Quantity(value=305.0, unit="m"))
        )


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"inlet_temperature": Quantity(value=0.0, unit="K")}, "absolute zero"),
        ({"opening": Quantity(value=-0.1, unit="dimensionless")}, "closed interval"),
        ({"opening": Quantity(value=1.1, unit="dimensionless")}, "closed interval"),
        ({"inlet_pressure": Quantity(value=0.0, unit="Pa")}, "positive absolute"),
    ],
)
def test_nonphysical_valve_conditions_are_rejected(
    product: ProductRecord, updates: dict[str, Quantity], message: str
) -> None:
    with pytest.raises(PerformanceMapError, match=message):
        evaluate_expansion_valve_map(_input(product, **updates))


def test_valve_map_and_envelope_refrigerants_must_match(product: ProductRecord) -> None:
    envelope = product.operating_envelopes[0].model_copy(update={"refrigerant": "R410A"})
    changed_product = product.model_copy(update={"operating_envelopes": (envelope,)})

    with pytest.raises(PerformanceMapError, match="refrigerants differ"):
        evaluate_expansion_valve_map(_input(changed_product))


def test_capacity_output_is_not_converted_to_mass_flow(product: ProductRecord) -> None:
    payload = deepcopy(product.model_dump(mode="json"))
    performance_map = payload["performance_maps"][0]
    performance_map["output_names"] = ["cooling_capacity"]
    for index, point in enumerate(performance_map["points"]):
        point["outputs"] = [
            _value(f"capacity-{index}", "cooling_capacity", 10_000.0 + 100.0 * index, "W")
        ]
    capacity_product = ProductRecord.model_validate(payload)

    result = evaluate_expansion_valve_map(_input(capacity_product))

    assert result.outputs == {"cooling_capacity": pytest.approx(10_350.0)}
    assert result.output_units == {"cooling_capacity": "W"}
    assert "mass_flow" not in result.outputs


def test_nonpositive_map_output_is_rejected(product: ProductRecord) -> None:
    performance_map = product.performance_maps[0]
    changed_points = tuple(
        point.model_copy(
            update={
                "outputs": (
                    point.outputs[0].model_copy(
                        update={
                            "value_si": point.outputs[0].value_si.model_copy(update={"value": 0.0})
                        }
                    ),
                )
            }
        )
        for point in performance_map.points
    )
    changed_map = performance_map.model_copy(update={"points": changed_points})
    changed_product = product.model_copy(update={"performance_maps": (changed_map,)})

    with pytest.raises(PerformanceMapError, match="mass_flow"):
        evaluate_expansion_valve_map(_input(changed_product))


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


def _product_payload() -> dict[str, Any]:
    inlet_values = (8_000_000.0, 9_000_000.0)
    outlet_values = (3_000_000.0, 4_000_000.0)
    opening_values = (0.25, 0.75)
    points: list[dict[str, Any]] = []
    index = 0
    for inlet in inlet_values:
        for outlet in outlet_values:
            for opening in opening_values:
                mass_flow = inlet * 1e-8 - outlet * 5e-9 + opening * 0.02
                points.append(
                    {
                        "point_id": f"valve-point-{index}",
                        "coordinates": [
                            _value(f"vp-{index}-in", "inlet_pressure", inlet, "Pa"),
                            _value(f"vp-{index}-out", "outlet_pressure", outlet, "Pa"),
                            _value(
                                f"vp-{index}-opening",
                                "opening",
                                opening,
                                "dimensionless",
                            ),
                        ],
                        "outputs": [_value(f"vp-{index}-flow", "mass_flow", mass_flow, "kg/s")],
                        "source_id": "src-valve",
                    }
                )
                index += 1

    map_axes = [
        _axis("valve-axis-in", 0, "inlet_pressure", "PRESSURE", "Pa", inlet_values),
        _axis("valve-axis-out", 1, "outlet_pressure", "PRESSURE", "Pa", outlet_values),
        _axis(
            "valve-axis-opening",
            2,
            "opening",
            "OPENING_FRACTION",
            "dimensionless",
            opening_values,
        ),
    ]
    envelope_axes = [
        _axis("valve-envelope-in", 0, "inlet_pressure", "PRESSURE", "Pa", inlet_values),
        _axis("valve-envelope-out", 1, "outlet_pressure", "PRESSURE", "Pa", outlet_values),
    ]
    vertices = (
        (8_000_000.0, 3_000_000.0),
        (9_000_000.0, 3_000_000.0),
        (9_000_000.0, 4_000_000.0),
        (8_000_000.0, 4_000_000.0),
    )
    use_status = {
        "source_preserved": True,
        "structure_valid": True,
        "automatic_selection": "ELIGIBLE",
        "reasons": [],
    }
    return {
        "product_id": "MOCK-expansion-valve-v020",
        "component_type": "expansion_valve",
        "manufacturer": "FICTIONAL-P00",
        "model": "MOCK-expansion-valve-v020",
        "supported_refrigerants": ["R744"],
        "source": {
            "excel_file": "MOCK-NOT-A-REAL-WORKBOOK.xlsx",
            "sheet": "products",
            "row": 2,
            "document_ref": "P06 synthetic valve fixture; NO manufacturer evidence",
            "original_manufacturer": "FICTIONAL-P00",
            "original_model": "MOCK-expansion-valve-v020",
            "workbook_modified_at": "2026-09-20T00:00:00+09:00",
            "retrieved_at": "2026-09-20T00:00:00+09:00",
            "file_sha256": "2" * 64,
            "loader_version": "synthetic-only",
            "schema_version": "0.2.0",
        },
        "status": "unverified",
        "attributes": [],
        "rated_conditions": [],
        "operating_limits": [],
        "is_mock": True,
        "data_sources": [
            {
                "source_id": "src-valve",
                "origin": "MANUFACTURER",
                "excel_file": "MOCK-NOT-A-REAL-WORKBOOK.xlsx",
                "file_sha256": "2" * 64,
                "sheet": "performance_points",
                "row": 2,
                "document_ref": "Synthetic valve map and envelope fixture",
                "table_or_figure_ref": "synthetic-valve-table",
                "original_manufacturer": "FICTIONAL-P00",
                "original_model": "MOCK-expansion-valve-v020",
            }
        ],
        "rated_points": [],
        "performance_maps": [
            {
                "map_id": "valve-map-1",
                "map_kind": "EXPANSION_VALVE",
                "refrigerant": "R744",
                "original_refrigerant_label": "CO2",
                "topology": "R744_TRANSCRITICAL",
                "mode": "COOLING",
                "axes": map_axes,
                "fixed_conditions": [
                    _value(
                        "valve-fixed-inlet-temperature",
                        "inlet_temperature",
                        305.0,
                        "K",
                    )
                ],
                "output_names": ["mass_flow"],
                "points": points,
                "interpolation": "MULTILINEAR",
                "extrapolation": "FORBIDDEN",
                "source_id": "src-valve",
                "use_status": use_status,
            }
        ],
        "operating_envelopes": [
            {
                "envelope_id": "valve-envelope-1",
                "refrigerant": "R744",
                "original_refrigerant_label": "CO2",
                "axes": envelope_axes,
                "boundary_vertices": [
                    {
                        "vertex_order": vertex_order,
                        "coordinates": [
                            _value(
                                f"vertex-{vertex_order}-in",
                                "inlet_pressure",
                                inlet,
                                "Pa",
                            ),
                            _value(
                                f"vertex-{vertex_order}-out",
                                "outlet_pressure",
                                outlet,
                                "Pa",
                            ),
                        ],
                        "source_id": "src-valve",
                    }
                    for vertex_order, (inlet, outlet) in enumerate(vertices)
                ],
                "boundary_inclusive": True,
                "fixed_conditions": [
                    _value(
                        "envelope-fixed-inlet-temperature",
                        "inlet_temperature",
                        305.0,
                        "K",
                    ),
                    _value(
                        "envelope-fixed-opening",
                        "opening",
                        0.5,
                        "dimensionless",
                    ),
                ],
                "source_id": "src-valve",
                "use_status": use_status,
            }
        ],
    }


def _validated_product_with_inlet_domain(
    product: ProductRecord,
    *,
    inlet_pressure_pa: float,
    inlet_temperature_k: float,
) -> ProductRecord:
    payload = deepcopy(product.model_dump(mode="json"))
    pressure_shift = inlet_pressure_pa - 8_500_000.0
    for parent_name in ("performance_maps", "operating_envelopes"):
        parent = payload[parent_name][0]
        inlet_axis = parent["axes"][0]
        inlet_axis["original_values"] = [
            value + pressure_shift for value in inlet_axis["original_values"]
        ]
        inlet_axis["values_si"] = [value + pressure_shift for value in inlet_axis["values_si"]]
        for condition in parent["fixed_conditions"]:
            if condition["canonical_name"] == "inlet_temperature":
                condition["original_value"] = inlet_temperature_k
                condition["original_unit"] = "K"
                condition["value_si"] = {"value": inlet_temperature_k, "unit": "K"}
    for point in payload["performance_maps"][0]["points"]:
        coordinate = point["coordinates"][0]
        coordinate["original_value"] += pressure_shift
        coordinate["value_si"]["value"] += pressure_shift
    for vertex in payload["operating_envelopes"][0]["boundary_vertices"]:
        coordinate = vertex["coordinates"][0]
        coordinate["original_value"] += pressure_shift
        coordinate["value_si"]["value"] += pressure_shift
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
