"""Load a synthetic compressor, valve and HX bundle through the public contract."""

from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook

from agent_hvac.components.heat_exchanger_rated_point import (
    HeatExchangerRatedPointSelection,
    select_heat_exchanger_rated_point,
)
from agent_hvac.components.product_adapter import adapt_product_performance_map
from agent_hvac.database.index import ExcelComponentRepository
from agent_hvac.schemas.components import (
    ComponentType,
    OperatingMode,
    ProductTopology,
)
from agent_hvac.utils.units import Quantity
from tests.ws_a.test_excel_hx_integration import (
    _convert_detailed_workbook_to_gas_cooler,
)
from tests.ws_b.test_excel_repository import (
    convert_detailed_workbook_to_valve,
    write_detailed_workbook,
)


def _namespace_identifiers(path: Path, namespace: str) -> None:
    workbook = load_workbook(path)
    for sheet in workbook.worksheets:
        headers = tuple(cell.value for cell in sheet[1])
        id_columns = {
            index + 1
            for index, header in enumerate(headers)
            if isinstance(header, str) and header.endswith("_id")
        }
        for row in sheet.iter_rows(min_row=2):
            for column in id_columns:
                cell = row[column - 1]
                if isinstance(cell.value, str) and cell.value:
                    cell.value = f"{namespace}-{cell.value}"
    workbook.save(path)
    workbook.close()


def _write_bundle(root: Path) -> None:
    compressor = root / "synthetic-compressor.xlsx"
    valve = root / "synthetic-valve.xlsx"
    gas_cooler = root / "synthetic-gas-cooler.xlsx"

    write_detailed_workbook(compressor)
    _namespace_identifiers(compressor, "compressor")

    write_detailed_workbook(valve)
    convert_detailed_workbook_to_valve(valve)
    _namespace_identifiers(valve, "valve")

    write_detailed_workbook(gas_cooler)
    _convert_detailed_workbook_to_gas_cooler(gas_cooler)
    _namespace_identifiers(gas_cooler, "gas-cooler")


def test_synthetic_component_bundle_reaches_ws_a_adapters_without_id_collisions(
    tmp_path: Path,
) -> None:
    _write_bundle(tmp_path)
    repository = ExcelComponentRepository(tmp_path)

    summary = repository.reload()

    assert summary.errors == ()
    assert summary.loaded_products == 3
    products = {product.component_type: product for product in repository.records}
    assert set(products) == {
        ComponentType.COMPRESSOR,
        ComponentType.EXPANSION_VALVE,
        ComponentType.GAS_COOLER,
    }
    assert all(product.is_mock for product in products.values())
    assert (
        len({source.source_id for product in products.values() for source in product.data_sources})
        == 3
    )

    compressor_map = adapt_product_performance_map(
        products[ComponentType.COMPRESSOR],
        "compressor-cmp-map-1",
    )
    valve_map = adapt_product_performance_map(
        products[ComponentType.EXPANSION_VALVE],
        "valve-cmp-map-1",
    )
    assert compressor_map.source_ids == ("compressor-src-cmp-1",)
    assert valve_map.source_ids == ("valve-src-cmp-1",)

    gas_cooler = products[ComponentType.GAS_COOLER]
    rated = select_heat_exchanger_rated_point(
        HeatExchangerRatedPointSelection(
            product=gas_cooler,
            rated_point_id="gas-cooler-rated-1",
            refrigerant="R744",
            topology=ProductTopology.R744_TRANSCRITICAL,
            operating_mode=OperatingMode.COOLING,
            conditions={
                "inlet_pressure": Quantity(value=90.0, unit="bar"),
                "inlet_temperature": Quantity(value=375.0, unit="K"),
                "mass_flow": Quantity(value=360.0, unit="kg/h"),
            },
        )
    )
    assert rated.rated_point_source_id == "gas-cooler-src-cmp-1"
    assert rated.is_mock is True
