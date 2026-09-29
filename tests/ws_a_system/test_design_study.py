"""Study invariants, real case evidence, and continuous-flow control restrictions."""

import copy
import csv
import io
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_hvac.properties.coolprop_backend import CoolPropBackend
from agent_hvac.solvers.system_cycle import design_study as module
from agent_hvac.solvers.system_cycle.design_study import (
    DesignCase,
    DesignPoint,
    DesignStudyRequest,
    DesignStudyResult,
    assess_fan_control,
    design_study_csv,
    evaluate_design_case,
    solve_design_study,
)
from agent_hvac.utils.units import Power

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def request_data():
    return json.loads((ROOT / "examples/system_cycle/r410a_design_study.json").read_text())


@pytest.fixture(scope="module")
def point(request_data):
    case = next(c for c in request_data["cases"] if c["case_id"] == "grid-p3.5-air1.5-ua800")
    return evaluate_design_case(CoolPropBackend(), DesignCase.model_validate(case))


@pytest.mark.parametrize(
    "field,value",
    [("refrigerant", "R744"), ("refrigerant_mass_flow", {"value": 0.04, "unit": "kg/s"})],
)
def test_case_cannot_change_user_fixed_requirements(request_data, field, value):
    d = copy.deepcopy(request_data)
    d["cases"][0]["cycle_request"]["scenario"][field] = value
    with pytest.raises(ValidationError, match="fixed"):
        DesignStudyRequest.model_validate(d)


def test_room_boundary_and_duplicate_cases_rejected(request_data):
    d = copy.deepcopy(request_data)
    d["room_temperature"] = {"value": 22, "unit": "degC"}
    with pytest.raises(ValidationError, match="fixed"):
        DesignStudyRequest.model_validate(d)
    d = copy.deepcopy(request_data)
    d["cases"].append(d["cases"][0])
    with pytest.raises(ValidationError, match="unique"):
        DesignStudyRequest.model_validate(d)


def test_real_cycle_has_air_balance_and_does_not_match_three_kw(point):
    assert point.cycle.cycle_converged and point.cooling_design_eligible
    assert not point.load_balance_satisfied
    assert abs(point.air_balance_error.value) < 1e-6
    assert point.cooling.value == pytest.approx(7608.8611, abs=0.01)
    assert point.load_residual.value == pytest.approx(4608.8611, abs=0.01)
    assert DesignPoint.model_validate_json(point.model_dump_json()) == point


@pytest.mark.parametrize(
    "field,value",
    [
        ("cooling_design_eligible", False),
        ("load_balance_satisfied", True),
        ("cooling", {"value": 3000, "unit": "W"}),
        ("supply_temperature", {"value": 294.15, "unit": "K"}),
    ],
)
def test_tampered_result_is_rejected(point, field, value):
    d = point.model_dump(mode="json")
    d[field] = value
    with pytest.raises(ValidationError):
        DesignPoint.model_validate(d)


def _study_data(request_data, cases):
    d = copy.deepcopy(request_data)
    d["cases"] = cases
    return DesignStudyRequest.model_validate(d)


def test_study_preserves_failure_and_callback(request_data, point, monkeypatch):
    success = point.case.model_dump(mode="json")
    failure = copy.deepcopy(success)
    failure["case_id"] = "failure"
    failed_cycle = point.cycle.model_dump(mode="json")
    failed_cycle.update(
        status="unconverged", cycle_converged=False, performance=None, reason="test-domain-hole"
    )
    from agent_hvac.solvers.system_cycle.convergence_models import ConvergenceResult

    failed = DesignPoint(
        case=DesignCase.model_validate(failure),
        cycle=ConvergenceResult.model_validate(failed_cycle),
        cooling_design_eligible=False,
        eligibility_reason="test-domain-hole",
        load_balance_satisfied=False,
    )
    monkeypatch.setattr(
        module,
        "evaluate_design_case",
        lambda backend, c: point if c.case_id == success["case_id"] else failed,
    )
    seen = []
    r = solve_design_study(
        CoolPropBackend(), _study_data(request_data, [success, failure]), on_point=seen.append
    )
    assert len(r.points) == len(seen) == 2 and r.points[1].cooling is None
    rows = list(csv.DictReader(io.StringIO(design_study_csv(r))))
    assert rows[1]["cooling_W"] == rows[1]["COP"] == ""
    d = r.model_dump(mode="json")
    d["points"].pop()
    with pytest.raises(ValidationError, match="every"):
        DesignStudyResult.model_validate(d)


def test_control_cannot_claim_on_off_satisfies_continuous_flow(request_data, point):
    req = _study_data(request_data, [point.case.model_dump(mode="json")])
    r = DesignStudyResult(request=req, points=(point,))
    decisions = assess_fan_control(
        r,
        point.case.case_id,
        (Power(value=3000, unit="W"), Power(value=point.cooling.value, unit="W")),
    )
    low, exact = decisions
    assert not low.continuous_flow_solution_found
    assert low.reference_on_fraction == pytest.approx(3000 / point.cooling.value)
    assert low.reference_time_average_mass_flow.value < 0.05
    assert low.on_off_satisfies_continuous_flow is False
    assert exact.continuous_flow_solution_found and exact.matched_case_id == point.case.case_id
    with pytest.raises(ValueError, match="positive"):
        assess_fan_control(r, point.case.case_id, (Power(value=-1, unit="W"),))


def test_unexpected_errors_propagate(request_data, monkeypatch):
    def broken(*args):
        raise RuntimeError("backend defect")

    monkeypatch.setattr(module, "solve_circuit", broken)
    with pytest.raises(RuntimeError, match="defect"):
        evaluate_design_case(CoolPropBackend(), DesignCase.model_validate(request_data["cases"][0]))


def test_fan_control_does_not_select_different_pressure_design(request_data, point):
    data = next(c for c in request_data["cases"] if c["case_id"] == "grid-p4.5-air1.5-ua800")
    other = evaluate_design_case(CoolPropBackend(), DesignCase.model_validate(data))
    assert other.cooling_design_eligible and abs(other.cooling.value - point.cooling.value) > 1
    request = _study_data(
        request_data, [point.case.model_dump(mode="json"), other.case.model_dump(mode="json")]
    )
    result = DesignStudyResult(request=request, points=(point, other))
    decision = assess_fan_control(
        result, point.case.case_id, (Power(value=other.cooling.value, unit="W"),)
    )[0]
    assert decision.matched_case_id is None and not decision.continuous_flow_solution_found
