"""Integration checks for ProductRecord 0.2.0 calculation-view adapters."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_hvac.components.performance_map import (
    PerformanceMapError,
    evaluate_regular_grid,
    require_envelope_contains,
)
from agent_hvac.components.product_adapter import (
    adapt_product_operating_envelope,
    adapt_product_performance_map,
)
from agent_hvac.schemas.components import (
    AutomaticSelectionStatus,
    DataUseStatus,
    ProductRecord,
    UseRestrictionReason,
)
from agent_hvac.utils.exceptions import ComponentEnvelopeError

FIXTURE = Path(__file__).parents[1] / "fixtures" / "compressor_product_v020.json"


@pytest.fixture
def product() -> ProductRecord:
    return ProductRecord.model_validate_json(FIXTURE.read_text(encoding="utf-8"))


def test_production_map_adapts_and_interpolates_canonical_si(product: ProductRecord) -> None:
    performance_map = adapt_product_performance_map(product, "cmp-map-1")

    result = evaluate_regular_grid(
        performance_map,
        {"suction_pressure": 3_500_000.0, "discharge_pressure": 8_500_000.0},
        {"suction_temperature": 280.0, "frequency": 50.0},
    )

    assert tuple(axis.name for axis in performance_map.axes) == (
        "suction_pressure",
        "discharge_pressure",
    )
    assert tuple(axis.unit for axis in performance_map.axes) == ("Pa", "Pa")
    assert result.outputs["input_power"] == pytest.approx(1150.0, rel=0.0, abs=1e-12)
    assert result.outputs["mass_flow"] == pytest.approx(0.085, rel=0.0, abs=1e-12)
    assert result.output_units == {"input_power": "W", "mass_flow": "kg/s"}
    assert result.map_source_ids == ("src-map-1",)
    assert result.point_source_ids == ("src-map-1",)
    assert result.output_source_ids == {
        "input_power": ("src-map-1",),
        "mass_flow": ("src-map-1",),
    }


def test_exact_node_and_fixed_condition_sources_are_preserved(product: ProductRecord) -> None:
    performance_map = adapt_product_performance_map(product, "cmp-map-1")

    result = evaluate_regular_grid(
        performance_map,
        {"suction_pressure": 3_000_000.0, "discharge_pressure": 8_000_000.0},
        {"suction_temperature": 280.0, "frequency": 50.0},
    )

    assert result.outputs == {"input_power": 1000.0, "mass_flow": 0.08}
    assert result.point_source_ids == ("src-map-1",)
    assert tuple(condition.source_id for condition in performance_map.fixed_conditions) == (
        "src-map-1",
        "src-map-1",
    )


def test_production_envelope_adapts_boundary_policy_and_vertex_sources(
    product: ProductRecord,
) -> None:
    envelope = adapt_product_operating_envelope(product, "cmp-envelope-1")
    fixed = {"suction_temperature": 280.0, "frequency": 50.0}

    require_envelope_contains(envelope, 3_500_000.0, 8_500_000.0, fixed)
    require_envelope_contains(envelope, 3_000_000.0, 8_500_000.0, fixed)
    with pytest.raises(ComponentEnvelopeError, match="outside"):
        require_envelope_contains(envelope, 2_900_000.0, 8_500_000.0, fixed)

    assert (envelope.x_axis_name, envelope.y_axis_name) == (
        "suction_pressure",
        "discharge_pressure",
    )
    assert (envelope.x_unit, envelope.y_unit) == ("Pa", "Pa")
    assert envelope.source_ids == ("src-map-1",)
    assert all(vertex.source_ids == ("src-map-1",) for vertex in envelope.vertices)


def test_adapter_requires_explicit_existing_record_ids(product: ProductRecord) -> None:
    with pytest.raises(PerformanceMapError, match="does not contain map"):
        adapt_product_performance_map(product, "missing-map")
    with pytest.raises(PerformanceMapError, match="does not contain operating envelope"):
        adapt_product_operating_envelope(product, "missing-envelope")


def test_adapter_rejects_ineligible_typed_records(product: ProductRecord) -> None:
    ineligible = DataUseStatus(
        source_preserved=True,
        structure_valid=True,
        automatic_selection=AutomaticSelectionStatus.INELIGIBLE,
        reasons=(UseRestrictionReason.UNSUPPORTED_AXIS,),
    )
    rejected_map = product.performance_maps[0].model_copy(update={"use_status": ineligible})
    rejected_envelope = product.operating_envelopes[0].model_copy(update={"use_status": ineligible})
    rejected_product = product.model_copy(
        update={
            "performance_maps": (rejected_map,),
            "operating_envelopes": (rejected_envelope,),
        }
    )

    with pytest.raises(PerformanceMapError, match="map .* is not eligible"):
        adapt_product_performance_map(rejected_product, "cmp-map-1")
    with pytest.raises(PerformanceMapError, match="envelope .* is not eligible"):
        adapt_product_operating_envelope(rejected_product, "cmp-envelope-1")
