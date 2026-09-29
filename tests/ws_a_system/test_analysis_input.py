"""Bounded expansion, fixed requirements, numerical outcomes and compact CLI integration."""

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_hvac.properties.coolprop_backend import CoolPropBackend
from agent_hvac.solvers.system_cycle.analysis_input import CompactAnalysisInput, expand_analysis
from agent_hvac.solvers.system_cycle.analysis_manager import run_analysis

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def data():
    return json.loads((ROOT / "examples/system_cycle/compact_analysis.json").read_text())


def test_expansion_order_units_bounds_and_preserved_fixed_values(data):
    r = CompactAnalysisInput.model_validate(data)
    expanded = expand_analysis(r)
    assert len(expanded.study.cases) == r.candidate_count == 2
    assert expanded.study.cases[0].family == "baseline"
    assert [c.cycle_request.scenario.discharge_pressure.value for c in expanded.study.cases] == [
        3500000,
        2800000,
    ]
    for c in expanded.study.cases:
        assert c.sensible_load.value == 3000
        assert c.cycle_request.scenario.refrigerant == "R410A"
        assert c.cycle_request.scenario.refrigerant_mass_flow.value == 0.05
        assert c.cycle_request.scenario.evaporator.secondary_inlet_temperature.value == 294.15
    assert expanded == expand_analysis(
        CompactAnalysisInput.model_validate_json(r.model_dump_json())
    )


@pytest.mark.parametrize(
    "bad",
    [
        "budget",
        "dimension",
        "duplicates",
        "fixed_axis",
        "reversed",
        "nan",
        "baseline",
        "pressure",
        "valve",
        "one_sample",
        "zero_load",
    ],
)
def test_invalid_search_rejected_before_expansion(data, bad):
    if bad == "budget":
        data["axes"][0]["samples"] = 100
    elif bad == "dimension":
        data["axes"][0]["minimum"]["unit"] = "kg/s"
    elif bad == "duplicates":
        data["axes"].append(copy.deepcopy(data["axes"][0]))
    elif bad == "fixed_axis":
        data["axes"][0]["name"] = "refrigerant_mass_flow"
    elif bad == "reversed":
        data["axes"][0]["minimum"]["value"] = 4
    elif bad == "nan":
        data["axes"][0]["minimum"]["value"] = float("nan")
    elif bad == "baseline":
        data["baseline"]["discharge_pressure"]["value"] = 4
    elif bad == "pressure":
        data["axes"][0]["minimum"]["value"] = 0.5
    elif bad == "valve":
        data["valve_pressure_upper"]["value"] = 0.9
    elif bad == "one_sample":
        data["axes"][0]["samples"] = 1
    else:
        data["sensible_load"]["value"] = 0
    with pytest.raises(ValidationError):
        CompactAnalysisInput.model_validate(data)


def test_baseline_not_on_grid_is_preserved_once_and_counted(data):
    data["baseline"]["discharge_pressure"]["value"] = 3.2
    data["max_cases"] = 3
    r = CompactAnalysisInput.model_validate(data)
    assert r.candidate_count == 3
    pressures = [
        c.cycle_request.scenario.discharge_pressure.value for c in expand_analysis(r).study.cases
    ]
    assert pressures == [3200000, 2800000, 3500000]


def test_cartesian_order_independent_of_axis_declaration(data):
    data["axes"].append(
        {
            "name": "condenser_ua",
            "minimum": {"value": 400, "unit": "W/K"},
            "maximum": {"value": 800, "unit": "W/K"},
            "samples": 2,
            "authorization_ref": "explicit test axis",
        }
    )
    data["max_cases"] = 4
    r = expand_analysis(CompactAnalysisInput.model_validate(data))
    data["axes"].reverse()
    assert expand_analysis(CompactAnalysisInput.model_validate(data)) == r
    assert len(r.study.cases) == 4


def test_no_axes_is_single_baseline_and_unlisted_values_are_preset(data):
    data["axes"] = []
    data["max_cases"] = 1
    r = expand_analysis(CompactAnalysisInput.model_validate(data))
    assert len(r.study.cases) == 1 and r.permissions == ()
    scenario = r.study.cases[0].cycle_request.scenario
    assert scenario.compressor_isentropic_efficiency.value == 0.75
    assert scenario.network.suction_pipe.length.value == 0
    assert scenario.evaporator.cell_count == 80
    assert any("AGENT_ASSUMPTION" in a for a in scenario.assumptions)


@pytest.mark.parametrize(
    "load,found,sign", [(3000, False, 1), (9000, False, -1), (7608.861253860285, True, 0)]
)
def test_real_excess_shortage_and_target_match(data, load, found, sign):
    data["axes"] = []
    data["sensible_load"]["value"] = load
    data["raw_requirement"] = f"Independent regression target {load} W; synthetic."
    request = expand_analysis(CompactAnalysisInput.model_validate(data))
    report = run_analysis(CoolPropBackend(), request)
    point = report.study_result.points[0]
    assert point.cycle.cycle_converged and point.cooling_design_eligible
    assert report.target_found is found
    if sign:
        assert point.load_residual.value * sign > 0
    else:
        assert abs(point.load_residual.value) <= 1
    assert point.cooling.value == pytest.approx(7608.861253860285, abs=0.01)


def test_real_unavailable_fluid_is_not_substituted(data):
    data["refrigerant"] = "R407C"
    data["axes"] = []
    request = expand_analysis(CompactAnalysisInput.model_validate(data))
    report = run_analysis(CoolPropBackend(), request)
    assert not report.target_found
    assert report.study_result.points[0].cooling is None
    assert report.study_result.points[0].case.cycle_request.scenario.refrigerant == "R407C"
    assert report.assessments[0].outcome == "PROPERTY_STATE_FAILURE"


def test_large_cartesian_product_rejected_before_materialization(data):
    data["max_cases"] = 100
    data["axes"] *= 1
    data["axes"][0]["samples"] = 100
    data["axes"].append(
        {
            "name": "condenser_ua",
            "minimum": {"value": 1, "unit": "W/K"},
            "maximum": {"value": 800, "unit": "W/K"},
            "samples": 100,
            "authorization_ref": "test budget",
        }
    )
    with pytest.raises(ValidationError, match="10000"):
        CompactAnalysisInput.model_validate(data)


def test_cli_compact_input_archive_and_expansion(data, tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "compact_cli", ROOT / "scripts/run_analysis_manager.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "compact.json"
    source.write_text(json.dumps(data), encoding="utf-8")
    out = tmp_path / "run"
    monkeypatch.setattr(
        sys,
        "argv",
        ["cli", "--format", "compact", "--input", str(source), "--output-dir", str(out)],
    )

    # Verify expansion reaches the same manager without paying for a duplicate numerical solve.
    def stop(backend, request, **kwargs):
        assert request == expand_analysis(CompactAnalysisInput.model_validate(data))
        raise RuntimeError("intentional test interruption")

    monkeypatch.setattr(module, "run_analysis", stop)
    assert module.main() == 3
    meta = json.loads((out / "metadata.json").read_text())
    assert meta["original_input"] == data and meta["input_format"] == "compact"
    assert len(meta["expanded_request"]["study"]["cases"]) == 2
    assert meta["preset_sha256"]
