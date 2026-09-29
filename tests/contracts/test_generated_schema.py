import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from agent_hvac.physics.state import ThermoState
from agent_hvac.schemas.results import FinalDesignPackage, OptimizationResult, SimulationResult

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIRECTORY = ROOT / "docs" / "workstreams" / "schema"


@pytest.mark.parametrize(
    ("name", "model"),
    [
        ("ThermoState", ThermoState),
        ("SimulationResult", SimulationResult),
        ("OptimizationResult", OptimizationResult),
        ("FinalDesignPackage", FinalDesignPackage),
    ],
)
def test_generated_schema_matches_current_model(name: str, model: type[BaseModel]) -> None:
    generated = json.loads((SCHEMA_DIRECTORY / f"{name}.schema.json").read_text(encoding="utf-8"))

    assert generated == model.model_json_schema()
    if name != "ThermoState":
        assert "entropy" in generated["$defs"]["ThermoState"]["properties"]


@pytest.mark.parametrize(
    ("fixture_name", "model"),
    [
        ("simulation_result_r744", SimulationResult),
        ("optimization_result", OptimizationResult),
        ("final_design_package", FinalDesignPackage),
    ],
)
def test_existing_nested_json_without_entropy_remains_compatible(
    fixture_name: str,
    model: type[BaseModel],
    fixture_data,
) -> None:
    value = model.model_validate(fixture_data(fixture_name))
    dumped = value.model_dump(mode="json")

    assert "entropy" not in json.dumps(dumped)
