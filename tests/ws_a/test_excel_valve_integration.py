"""End-to-end checks from Excel schema 0.2.0 to expansion-valve map calculation."""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import load_workbook

from agent_hvac.components.expansion_valve_map import (
    ExpansionValveMapInput,
    evaluate_expansion_valve_map,
)
from agent_hvac.components.performance_map import PerformanceMapError
from agent_hvac.database.index import ExcelComponentRepository
from agent_hvac.properties.coolprop_backend import CoolPropBackend
from agent_hvac.schemas.components import ComponentType, ProductRecord
from agent_hvac.utils.units import Pressure, Quantity, Temperature
from tests.ws_b.test_excel_repository import (
    convert_detailed_workbook_to_valve,
    value_cells,
    write_detailed_workbook,
)


def _conditions() -> dict[str, Quantity]:
    return {
        "inlet_pressure": Pressure(value=95.0, unit="bar"),
        "outlet_pressure": Pressure(value=35.0, unit="bar"),
        "inlet_temperature": Temperature(value=280.0, unit="K"),
        "opening": Quantity(value=0.5, unit="dimensionless"),
    }


def _input(product: ProductRecord) -> ExpansionValveMapInput:
    return ExpansionValveMapInput(
        backend=CoolPropBackend(),
        product=product,
        map_id="cmp-map-1",
        envelope_id="envelope-1",
        conditions=_conditions(),
    )


def test_excel_loader_output_drives_valve_map_without_contract_copy(tmp_path: Path) -> None:
    workbook_path = tmp_path / "synthetic-valve.xlsx"
    write_detailed_workbook(workbook_path)
    convert_detailed_workbook_to_valve(workbook_path)
    repository = ExcelComponentRepository(tmp_path)

    summary = repository.reload()

    assert summary.errors == ()
    assert summary.loaded_products == 1
    product = ProductRecord.model_validate(repository.records[0].model_dump(mode="json"))
    assert product.component_type == ComponentType.EXPANSION_VALVE

    result = evaluate_expansion_valve_map(_input(product))

    assert result.model_path == "PERFORMANCE_MAP"
    assert result.product_id == "synthetic-compressor-1"
    assert result.map_id == "cmp-map-1"
    assert result.envelope_id == "envelope-1"
    assert result.inlet_phase in {"supercritical", "supercritical_liquid"}
    assert result.conditions_si == {
        "inlet_pressure": 9_500_000.0,
        "outlet_pressure": 3_500_000.0,
        "inlet_temperature": 280.0,
        "opening": 0.5,
    }
    assert result.outputs["mass_flow"] == pytest.approx(
        162.5 / 3_600.0,
        rel=0.0,
        abs=1e-12,
    )
    assert result.output_units == {"mass_flow": "kg/s"}
    assert result.map_source_ids == ("src-cmp-1",)
    assert result.map_axis_source_ids == ("src-cmp-1", "src-cmp-1")
    assert result.map_fixed_condition_source_ids == {
        "inlet_temperature": "src-cmp-1",
        "opening": "src-cmp-1",
    }
    assert result.envelope_source_ids == ("src-cmp-1",)
    assert result.envelope_axis_source_ids == ("src-cmp-1", "src-cmp-1")
    assert result.envelope_fixed_condition_source_ids == {
        "inlet_temperature": "src-cmp-1",
        "opening": "src-cmp-1",
    }


def test_quarantined_excel_valve_map_cannot_fall_back_to_isenthalpic_path(
    tmp_path: Path,
) -> None:
    workbook_path = tmp_path / "invalid-valve.xlsx"
    write_detailed_workbook(workbook_path)
    convert_detailed_workbook_to_valve(workbook_path)
    workbook = load_workbook(workbook_path)
    point_values = workbook["performance_point_values"]
    for index in range(1, 5):
        point_values.append(
            [
                f"point-{index}",
                "OUTPUT",
                None,
                *value_cells(f"valve-power-{index}", "input_power", 1.0, "W"),
            ]
        )
    workbook.save(workbook_path)
    workbook.close()

    repository = ExcelComponentRepository(tmp_path)
    summary = repository.reload()

    assert summary.loaded_products == 1
    product = repository.records[0]
    assert product.performance_maps == ()
    assert len(product.operating_envelopes) == 1
    assert any("forbids input_power" in error for error in summary.errors)
    with pytest.raises(PerformanceMapError, match="does not contain map"):
        evaluate_expansion_valve_map(_input(product))
