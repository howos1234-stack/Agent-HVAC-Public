"""Synthetic multi-workbook products through independent component trials."""

from dataclasses import replace
from pathlib import Path

import pytest
from openpyxl import load_workbook

from agent_hvac.components.candidate_trials import (
    ComponentCandidateTrial,
    HeatExchangerTrialInput,
    evaluate_synthetic_component_trials,
)
from agent_hvac.database.index import ExcelComponentRepository
from agent_hvac.properties.coolprop_backend import CoolPropBackend
from agent_hvac.schemas.components import ComponentType
from tests.ws_a.test_excel_component_bundle_integration import _write_bundle
from tests.ws_a.test_excel_compressor_integration import _input as compressor_input
from tests.ws_a.test_excel_hx_integration import _boundaries, _selection
from tests.ws_a.test_excel_valve_integration import _input as valve_input


def _trials(repository: ExcelComponentRepository) -> tuple[ComponentCandidateTrial, ...]:
    products = {product.component_type: product for product in repository.records}
    return (
        ComponentCandidateTrial(
            "compressor",
            replace(
                compressor_input(products[ComponentType.COMPRESSOR]),
                map_id="compressor-cmp-map-1",
                envelope_id="compressor-envelope-1",
            ),
        ),
        ComponentCandidateTrial(
            "valve",
            replace(
                valve_input(products[ComponentType.EXPANSION_VALVE]),
                map_id="valve-cmp-map-1",
                envelope_id="valve-envelope-1",
            ),
        ),
        ComponentCandidateTrial(
            "gas-cooler",
            HeatExchangerTrialInput(
                backend=CoolPropBackend(),
                selection=replace(
                    _selection(products[ComponentType.GAS_COOLER]),
                    rated_point_id="gas-cooler-rated-1",
                ),
                boundaries=_boundaries(),
            ),
        ),
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_loaded_mixed_candidates_preserve_results_order_and_source(
    tmp_path: Path, reverse: bool
) -> None:
    _write_bundle(tmp_path)
    repository = ExcelComponentRepository(tmp_path)
    assert repository.reload().errors == ()
    trials = _trials(repository)
    baseline = evaluate_synthetic_component_trials(trials)
    ordered = tuple(reversed(trials)) if reverse else trials
    outcomes = evaluate_synthetic_component_trials(ordered)
    assert tuple(outcome.candidate_id for outcome in outcomes) == tuple(
        trial.candidate_id for trial in ordered
    )
    assert {item.candidate_id: item for item in outcomes} == {
        item.candidate_id: item for item in baseline
    }
    for outcome in outcomes:
        assert outcome.status == "EVALUATED"
        assert outcome.result is not None
        assert outcome.is_mock is True
        assert outcome.failure_type is None
        assert set(outcome.selected_source_ids) == {f"{outcome.candidate_id}-src-cmp-1"}


def test_new_reload_records_reject_missing_map_without_reusing_prior_output(tmp_path: Path) -> None:
    _write_bundle(tmp_path)
    repository = ExcelComponentRepository(tmp_path)
    initial = repository.reload()
    assert initial.errors == ()
    initial_version = initial.database_version
    baseline = evaluate_synthetic_component_trials(_trials(repository))
    path = tmp_path / "synthetic-compressor.xlsx"
    original = path.read_bytes()
    workbook = load_workbook(path)
    points = workbook["performance_points"]
    points.append(["compressor-cmp-map-1", "duplicate", "compressor-src-cmp-1"])
    points.append(["compressor-cmp-map-1", "duplicate", "compressor-src-cmp-1"])
    workbook.save(path)
    workbook.close()
    changed = repository.reload()
    assert changed.errors
    assert changed.database_version != initial_version
    failed, valve, hx = evaluate_synthetic_component_trials(_trials(repository))
    assert failed.status == "REJECTED"
    assert failed.result is None
    assert failed.selected_source_ids == ("compressor-src-cmp-1",)
    assert failed.failure_type == "PerformanceMapError"
    assert valve == baseline[1]
    assert hx == baseline[2]
    path.write_bytes(original)
    recovered = repository.reload()
    assert recovered.errors == ()
    assert recovered.database_version == initial_version
    assert evaluate_synthetic_component_trials(_trials(repository)) == baseline
