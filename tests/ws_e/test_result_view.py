import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_hvac.app.result_view import (
    export_artifact,
    optimization_rows,
    parse_artifact,
    state_rows,
)
from agent_hvac.schemas.results import OptimizationResult, SimulationResult

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_package_export_preserves_contract_and_mock():
    original = (FIXTURES / "final_design_package.json").read_text(encoding="utf-8")
    package = parse_artifact(original, "FinalDesignPackage")
    exported = json.loads(export_artifact(package))
    assert exported == json.loads(original)
    assert exported["metadata"]["is_mock"] is True
    assert exported["release_ready"] is False


@pytest.mark.parametrize("data", ["{", '{"unexpected":1}', "NaN"])
def test_invalid_json_rejected(data):
    with pytest.raises(ValidationError):
        parse_artifact(data, "SimulationResult")


def test_units_are_validated_and_displayed_in_si():
    data = json.loads((FIXTURES / "simulation_result_r744.json").read_text(encoding="utf-8"))
    data["state_points"]["example"]["pressure"] = {"value": 10, "unit": "bar"}
    result = parse_artifact(json.dumps(data), "SimulationResult")
    assert isinstance(result, SimulationResult)
    assert state_rows(result)[0]["p [Pa, absolute]"] == 1_000_000
    data["state_points"]["example"]["pressure"]["unit"] = "meter"
    with pytest.raises(ValidationError):
        parse_artifact(json.dumps(data), "SimulationResult")


def test_export_revalidates_mutable_nested_states():
    result = parse_artifact(
        (FIXTURES / "simulation_result_r744.json").read_bytes(), "SimulationResult"
    )
    assert isinstance(result, SimulationResult)
    result.state_points.clear()
    with pytest.raises(ValidationError):
        export_artifact(result)


def test_core_import_does_not_load_gui():
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import agent_hvac.schemas.results; import sys; assert 'streamlit' not in sys.modules",
        ],
        check=True,
    )


def test_optimization_result_round_trip_preserves_rank_units_and_mock():
    original = (FIXTURES / "optimization_result_p09.json").read_text(encoding="utf-8")
    result = parse_artifact(original, "OptimizationResult")
    assert isinstance(result, OptimizationResult)
    assert json.loads(export_artifact(result)) == json.loads(original)
    rows = optimization_rows(result)
    assert [row["rank"] for row in rows] == [1, 2, 3, 4, 5]
    assert rows[0]["objective_value"] == 0.0
    assert rows[0]["objective_unit"] == "dimensionless"
    assert rows[0]["is_mock"] is True


def test_optimization_export_revalidates_mutable_nested_data():
    result = parse_artifact(
        (FIXTURES / "optimization_result_p09.json").read_bytes(), "OptimizationResult"
    )
    assert isinstance(result, OptimizationResult)
    result.ranked_designs[0].simulation.state_points.clear()

    with pytest.raises(ValidationError, match="Converged result requires"):
        export_artifact(result)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda data: data.pop("is_mock"), "is_mock"),
        (
            lambda data: data["ranked_designs"][0]["constraints"].update(
                design_id="different-design"
            ),
            "Design/result identifiers differ",
        ),
        (
            lambda data: data["ranked_designs"][0]["simulation"].update(is_mock=False),
            "Mixed mock and real artifacts",
        ),
    ],
    ids=["missing-required", "id-mismatch", "mixed-mock"],
)
def test_invalid_optimization_contracts_are_rejected(mutate, message):
    data = json.loads((FIXTURES / "optimization_result_p09.json").read_text(encoding="utf-8"))
    mutate(data)

    with pytest.raises(ValidationError, match=message):
        parse_artifact(json.dumps(data), "OptimizationResult")
