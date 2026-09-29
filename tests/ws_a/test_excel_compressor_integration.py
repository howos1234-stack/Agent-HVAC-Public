"""End-to-end checks from Excel schema 0.2.0 to compressor-map calculation."""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import load_workbook

from agent_hvac.components.compressor_map import CompressorMapInput, evaluate_compressor_map
from agent_hvac.components.performance_map import PerformanceMapError
from agent_hvac.database.index import ExcelComponentRepository
from agent_hvac.schemas.components import ProductRecord
from agent_hvac.utils.units import Pressure, Quantity, Temperature
from tests.ws_b.test_excel_repository import write_detailed_workbook


def _conditions() -> dict[str, Quantity]:
    return {
        "suction_pressure": Pressure(value=35.0, unit="bar"),
        "discharge_pressure": Pressure(value=85.0, unit="bar"),
        "suction_temperature": Temperature(value=280.0, unit="K"),
        "frequency": Quantity(value=50.0, unit="Hz"),
    }


def _input(product: ProductRecord) -> CompressorMapInput:
    return CompressorMapInput(
        product=product,
        map_id="cmp-map-1",
        envelope_id="envelope-1",
        conditions=_conditions(),
    )


def test_excel_loader_output_drives_compressor_map_without_contract_copy(
    tmp_path: Path,
) -> None:
    workbook_path = tmp_path / "synthetic-compressor.xlsx"
    write_detailed_workbook(workbook_path)
    repository = ExcelComponentRepository(tmp_path)

    summary = repository.reload()

    assert summary.errors == ()
    assert summary.loaded_products == 1
    product = ProductRecord.model_validate(repository.records[0].model_dump(mode="json"))

    result = evaluate_compressor_map(_input(product))

    assert result.model_path == "PERFORMANCE_MAP"
    assert result.product_id == "synthetic-compressor-1"
    assert result.map_id == "cmp-map-1"
    assert result.envelope_id == "envelope-1"
    assert result.conditions_si == {
        "suction_pressure": 3_500_000.0,
        "discharge_pressure": 8_500_000.0,
        "suction_temperature": 280.0,
        "frequency": 50.0,
    }
    assert result.outputs["input_power"] == pytest.approx(2_250.0, rel=0.0, abs=1e-12)
    assert result.outputs["mass_flow"] == pytest.approx(
        162.5 / 3_600.0,
        rel=0.0,
        abs=1e-12,
    )
    assert result.output_units == {"input_power": "W", "mass_flow": "kg/s"}
    assert result.map_source_ids == ("src-cmp-1",)
    assert result.map_axis_source_ids == ("src-cmp-1", "src-cmp-1")
    assert result.map_fixed_condition_source_ids == {
        "suction_temperature": "src-cmp-1",
        "frequency": "src-cmp-1",
    }
    assert result.envelope_source_ids == ("src-cmp-1",)
    assert result.envelope_axis_source_ids == ("src-cmp-1", "src-cmp-1")
    assert result.envelope_fixed_condition_source_ids == {
        "suction_temperature": "src-cmp-1",
        "frequency": "src-cmp-1",
    }


def test_quarantined_excel_map_cannot_fall_back_to_another_calculation_path(
    tmp_path: Path,
) -> None:
    workbook_path = tmp_path / "invalid-point-id.xlsx"
    write_detailed_workbook(workbook_path)
    workbook = load_workbook(workbook_path)
    points = workbook["performance_points"]
    points.append(["cmp-map-1", "duplicate-extra", "src-cmp-1"])
    points.append(["cmp-map-1", "duplicate-extra", "src-cmp-1"])
    workbook.save(workbook_path)
    workbook.close()

    repository = ExcelComponentRepository(tmp_path)
    summary = repository.reload()

    assert summary.loaded_products == 1
    product = repository.records[0]
    assert product.performance_maps == ()
    assert len(product.rated_points) == 1
    assert len(product.operating_envelopes) == 1
    assert any(
        "map cmp-map-1" in error and "missing or duplicate point_id" in error
        for error in summary.errors
    )
    with pytest.raises(PerformanceMapError, match="does not contain map"):
        evaluate_compressor_map(_input(product))
