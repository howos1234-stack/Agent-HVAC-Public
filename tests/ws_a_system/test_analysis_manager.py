"""Authorization boundaries and evidence-based outcomes for synthetic analysis."""

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_hvac.properties.coolprop_backend import CoolPropBackend
from agent_hvac.solvers.system_cycle import analysis_manager as manager
from agent_hvac.solvers.system_cycle.analysis_manager import (
    AnalysisReport,
    AnalysisRequest,
    assess_point,
    run_analysis,
)
from agent_hvac.solvers.system_cycle.design_study import (
    DesignCase,
    DesignPoint,
    evaluate_design_case,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def data():
    return json.loads((ROOT / "examples/system_cycle/r410a_analysis_manager.json").read_text())


@pytest.fixture(scope="module")
def real_point():
    data = json.loads((ROOT / "examples/system_cycle/r410a_analysis_manager.json").read_text())
    return evaluate_design_case(
        CoolPropBackend(), DesignCase.model_validate(data["study"]["cases"][1])
    )


def _set(data, path, value):
    node = data
    for key in path.split(".")[:-1]:
        node = node[key]
    node[path.split(".")[-1]] = value


@pytest.mark.parametrize(
    "path,value",
    [
        ("sensible_load.value", 5391),
        ("cycle_request.scenario.refrigerant_mass_flow.value", 0.04),
        ("cycle_request.scenario.refrigerant", "R744"),
        ("cycle_request.scenario.evaporator.secondary_inlet_temperature.value", 295),
        ("cycle_request.scenario.compressor_isentropic_efficiency.value", 0.8),
        ("cycle_request.settings.enthalpy_tolerance.value", 0.005),
        ("cycle_request.scenario.network.pressure_tolerance.value", 0.1),
        ("cycle_request.scenario.network.suction_pipe.length.value", 0.5),
    ],
)
def test_unlisted_changes_rejected_before_solver(data, path, value, monkeypatch):
    _set(data["study"]["cases"][1], path, value)
    calls = []
    monkeypatch.setattr(manager, "evaluate_design_case", lambda *args: calls.append(args))
    with pytest.raises(ValidationError):
        AnalysisRequest.model_validate(data)
    assert not calls


@pytest.mark.parametrize(
    "mutation", ["outside", "unit", "forbidden", "duplicate", "budget", "missing"]
)
def test_permissions_fail_closed(data, mutation):
    if mutation == "outside":
        data["permissions"][0]["maximum"] = 3.5e6
    elif mutation == "unit":
        data["permissions"][0]["unit"] = "bar"
    elif mutation == "forbidden":
        data["permissions"][0]["path"] = "sensible_load.value"
    elif mutation == "duplicate":
        data["permissions"].append(copy.deepcopy(data["permissions"][0]))
    elif mutation == "budget":
        data["max_cases"] = 2
    else:
        data["permissions"] = []
    with pytest.raises(ValidationError):
        AnalysisRequest.model_validate(data)


def test_normalized_equivalent_units_are_not_changes(data):
    data["study"]["cases"][1]["cycle_request"]["scenario"]["refrigerant_mass_flow"] = {
        "value": 50,
        "unit": "g/s",
    }
    assert AnalysisRequest.model_validate(data).study.refrigerant_mass_flow.value == 0.05


def test_preapproved_numeric_retry_keeps_physical_inputs(data):
    data["study"]["cases"] = [data["study"]["cases"][1]]
    retry = copy.deepcopy(data["study"]["cases"][0])
    retry["case_id"] = "approved-bracket-retry"
    retry["cycle_request"]["settings"]["lower_enthalpy"]["value"] = 425000
    data["study"]["cases"].append(retry)
    data["permissions"].append(
        {
            "path": "cycle_request.settings.lower_enthalpy.value",
            "unit": "J/kg",
            "minimum": 423500,
            "maximum": 425000,
            "authorization_ref": "test explicit retry",
        }
    )
    request = AnalysisRequest.model_validate(data)
    assert request.study.cases[0].cycle_request.scenario == retry_scenario(request)


def retry_scenario(request):
    return request.study.cases[1].cycle_request.scenario


def test_real_mismatch_and_exact_load_match_remain_distinct(real_point):
    a = assess_point(real_point, real_point.case)
    assert a.outcome == "TARGET_MISMATCH" and a.changed_paths == ()
    # A NEW synthetic load input matching actual Q; never an adjustment within the prior run.
    raw = real_point.model_dump(mode="json")
    raw["case"]["sensible_load"]["value"] = real_point.cooling.value
    raw["load_residual"]["value"] = 0
    raw["load_balance_satisfied"] = True
    matched = DesignPoint.model_validate(raw)
    assert assess_point(matched, matched.case).outcome == "TARGET_MET"


@pytest.mark.parametrize(
    "statuses,expected",
    [
        (["infeasible"], "MODEL_OR_CONSTRAINT_LIMIT"),
        (["invalid-property-state"], "PROPERTY_STATE_FAILURE"),
        (["component-numerical-failure"], "NUMERICAL_FAILURE"),
        (["evaluated"], "NUMERICAL_FAILURE"),
        (["infeasible", "evaluated"], "UNRESOLVED"),
        ([], "UNRESOLVED"),
    ],
)
def test_classification_uses_structured_evidence_not_keyword_guessing(
    real_point, statuses, expected
):
    raw = real_point.model_dump(mode="json")
    cycle = raw["cycle"]
    sample = cycle["history"][0]
    cycle.update(
        cycle_converged=False,
        status="unconverged",
        performance=None,
        last_evaluation=None,
        reason="no-root",
        message="No global impossibility claim",
    )
    cycle["history"] = [
        dict(sample, status=s, message="test structured evidence", residual=None) for s in statuses
    ]
    raw.update(
        cooling_design_eligible=False,
        eligibility_reason="test failure",
        cooling=None,
        load_residual=None,
        supply_temperature=None,
        air_balance_error=None,
        load_balance_satisfied=False,
    )
    point = DesignPoint.model_validate(raw)
    assessment = assess_point(point, point.case)
    assert assessment.outcome == expected


def _single_request(data, point):
    data["study"]["cases"] = [point.case.model_dump(mode="json")]
    return AnalysisRequest.model_validate(data)


def test_report_retains_evidence_rejects_forged_success(data, real_point, monkeypatch):
    monkeypatch.setattr(manager, "evaluate_design_case", lambda *args: real_point)
    seen = []
    report = run_analysis(
        CoolPropBackend(), _single_request(data, real_point), on_point=seen.append
    )
    assert seen == [real_point]
    assert report.conclusion == "NO_TARGET_IN_DECLARED_CASES"
    assert report.closest_eligible_case_id == real_point.case.case_id
    assert not report.requirement_change_applied and not report.global_infeasibility_proven
    assert AnalysisReport.model_validate_json(report.model_dump_json()) == report
    raw = report.model_dump(mode="json")
    raw["target_found"] = True
    with pytest.raises(ValidationError):
        AnalysisReport.model_validate(raw)


def test_mutated_nested_request_revalidated_before_any_solve(data, monkeypatch):
    request = AnalysisRequest.model_validate(data)
    raw = request.model_dump(mode="json")
    raw["study"]["cases"][1]["sensible_load"]["value"] = 4000
    bypass = AnalysisRequest.model_construct(**raw)
    calls = []
    monkeypatch.setattr(manager, "evaluate_design_case", lambda *args: calls.append(args))
    with pytest.warns(UserWarning, match="serializer warnings"), pytest.raises(ValidationError):
        run_analysis(CoolPropBackend(), bypass)
    assert calls == []


def test_unexpected_error_propagates_with_prior_callback(data, real_point, monkeypatch):
    data["study"]["cases"][0] = real_point.case.model_dump(mode="json")
    data["study"]["cases"][1]["case_id"] = "second-case"
    request = AnalysisRequest.model_validate(data)
    count = 0

    def broken(backend, case):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("synthetic backend defect")
        return real_point

    monkeypatch.setattr(manager, "evaluate_design_case", broken)
    seen = []
    with pytest.raises(RuntimeError, match="backend defect"):
        run_analysis(CoolPropBackend(), request, on_point=seen.append)
    assert seen == [real_point]


def _cli(monkeypatch, tmp_path, data):
    spec = importlib.util.spec_from_file_location(
        "analysis_cli", ROOT / "scripts/run_analysis_manager.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "input.json"
    source.write_text(json.dumps(data), encoding="utf-8")
    out = tmp_path / "run"
    monkeypatch.setattr(sys, "argv", ["cli", "--input", str(source), "--output-dir", str(out)])
    return module, out


def test_cli_archives_unexpected_error_and_does_not_overwrite(data, tmp_path, monkeypatch):
    module, out = _cli(monkeypatch, tmp_path, data)

    def broken(*args, **kwargs):
        raise RuntimeError("deterministic test defect")

    monkeypatch.setattr(module, "run_analysis", broken)
    assert module.main() == 3
    error = json.loads((out / "error.json").read_text())
    assert error["category"] == "UNEXPECTED_SOLVER_ERROR"
    assert not (out / "report.json").exists()
    before = (out / "error.json").read_bytes()
    assert module.main() == 2
    assert before == (out / "error.json").read_bytes()


def test_cli_input_error_never_runs_solver(data, tmp_path, monkeypatch):
    data["max_cases"] = 1
    module, out = _cli(monkeypatch, tmp_path, data)
    monkeypatch.setattr(module, "run_analysis", lambda *args: pytest.fail("must not solve"))
    assert module.main() == 2 and not out.exists()


def test_foreign_case_result_cannot_enter_archive(data, real_point, monkeypatch):
    request = AnalysisRequest.model_validate(data)
    monkeypatch.setattr(manager, "evaluate_design_case", lambda *args: real_point)
    seen = []
    with pytest.raises(ValueError, match="different requested case"):
        run_analysis(CoolPropBackend(), request, on_point=seen.append)
    assert not seen


def test_pressure_wrapper_does_not_hide_component_domain_failure(real_point):
    raw = real_point.model_dump(mode="json")
    cycle = raw["cycle"]
    sample = cycle["history"][0]
    sample.update(status="component-numerical-failure", failed_stage="pressure-solve")
    pressure = sample["pressure_history"][0]
    pressure.update(
        status="infeasible",
        failed_stage="high_side_pipe",
        message="two-phase pipe correlations not implemented",
        residual=None,
    )
    sample["pressure_history"] = [pressure]
    cycle.update(
        cycle_converged=False,
        status="unconverged",
        performance=None,
        last_evaluation=None,
        history=[sample],
    )
    raw.update(
        cooling_design_eligible=False,
        eligibility_reason="test nested failure",
        cooling=None,
        load_residual=None,
        supply_temperature=None,
        air_balance_error=None,
        load_balance_satisfied=False,
    )
    point = DesignPoint.model_validate(raw)
    assessment = assess_point(point, point.case)
    assert assessment.outcome == "MODEL_OR_CONSTRAINT_LIMIT"
    assert any("two-phase pipe" in evidence for evidence in assessment.evidence)
