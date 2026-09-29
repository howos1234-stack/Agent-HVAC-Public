"""S2 physical roots, conservation, numerical-domain failures and reproducibility."""

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_hvac.properties.coolprop_backend import CoolPropBackend
from agent_hvac.solvers.system_cycle import (
    CircuitResult,
    ConvergenceRequest,
    ConvergenceResult,
    convergence,
    evaluate_circuit,
    solve_circuit,
)

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples/system_cycle/r744_closed_loop.json"


@pytest.fixture(scope="module")
def request_data():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def request_model(request_data):
    return ConvergenceRequest.model_validate(request_data)


@pytest.fixture(scope="module")
def solved(request_model):
    return solve_circuit(CoolPropBackend(), request_model)


def _request(data, **settings):
    changed = copy.deepcopy(data)
    changed["settings"].update(settings)
    return ConvergenceRequest.model_validate(changed)


def test_real_r744_root_closes_states_and_independent_balances(request_model, solved):
    assert solved.status == "converged" and solved.cycle_converged
    assert solved.is_mock and solved.reason == "closure-satisfied"
    circuit, performance = solved.last_evaluation, solved.performance
    assert circuit is not None and performance is not None
    assert circuit.cycle_converged is False  # Inner object is still a single traversal.
    start, end = circuit.nodes["suction_trial"], circuit.nodes["suction_return"]
    assert start.phase == end.phase == "gas"
    assert abs(end.enthalpy.value - start.enthalpy.value) <= 0.01
    assert abs(end.temperature.value - start.temperature.value) <= 1e-4
    assert end.pressure == start.pressure == request_model.scenario.suction_pressure
    assert abs(start.enthalpy.value - 464453.5446166992) <= 0.02
    assert start.temperature.value == pytest.approx(289.8571983311086, abs=2e-5, rel=0)
    assert performance.cooling_cop == pytest.approx(0.5199018793926933, abs=2e-6, rel=0)
    q = [c.heat_to_refrigerant.value for c in circuit.components]
    w = [c.work_to_refrigerant.value for c in circuit.components]
    assert abs(sum(q) + sum(w)) / max(abs(x) for x in q + w) <= 1e-6
    assert performance.relative_energy_error <= 1e-6
    assert performance.relative_mass_error <= 1e-12
    assert solved.bisection_iterations <= request_model.settings.max_iterations
    assert len(solved.history) <= (
        request_model.settings.scan_intervals + 1 + request_model.settings.max_iterations
    )
    assert solved.history[0].status == "infeasible"  # 430 kJ/kg: wet suction, not clamped.
    assert solved.history[0].residual is None
    assert ConvergenceResult.model_validate_json(solved.model_dump_json()) == solved


def test_h_trial_path_preserves_s1_and_does_not_use_temperature_boundary(request_model):
    scenario = request_model.scenario
    backend = CoolPropBackend()
    old = evaluate_circuit(backend, scenario)
    h = old.nodes["suction_trial"].enthalpy
    by_h = evaluate_circuit(backend, scenario, trial_suction_enthalpy=h)
    assert old.status == by_h.status == "evaluated"
    assert old.trial_suction_enthalpy is None and by_h.trial_suction_enthalpy == h
    for name in old.nodes:
        assert old.nodes[name].enthalpy.value == pytest.approx(
            by_h.nodes[name].enthalpy.value, rel=1e-10
        )
    assert not old.cycle_converged and not by_h.cycle_converged


def test_repeat_and_alternative_bracket_reach_same_root(request_model, request_data, solved):
    assert solve_circuit(CoolPropBackend(), request_model) == solved
    changed = copy.deepcopy(request_data)
    changed["scenario"]["trial_suction_temperature"] = {"value": 300, "unit": "K"}
    changed["settings"].update(
        lower_enthalpy={"value": 450000, "unit": "J/kg"},
        upper_enthalpy={"value": 480000, "unit": "J/kg"},
        scan_intervals=3,
    )
    other = solve_circuit(CoolPropBackend(), ConvergenceRequest.model_validate(changed))
    assert other.cycle_converged
    assert (
        abs(
            other.last_evaluation.nodes["suction_trial"].enthalpy.value
            - solved.last_evaluation.nodes["suction_trial"].enthalpy.value
        )
        < 0.03
    )
    assert other.performance.cooling_cop == pytest.approx(solved.performance.cooling_cop, abs=2e-6)


def test_stricter_energy_check_refines_beyond_enthalpy_tolerance(request_data, solved):
    request = _request(request_data, relative_energy_tolerance=1e-10)
    result = solve_circuit(CoolPropBackend(), request)
    assert result.cycle_converged
    assert result.performance.relative_energy_error <= 1e-10
    assert len(result.history) > len(solved.history)


@pytest.mark.parametrize("cells", [160])
def test_grid_refinement_stays_close_without_changing_solver_tolerances(
    request_data, solved, cells
):
    changed = copy.deepcopy(request_data)
    changed["scenario"]["gas_cooler"]["cell_count"] = cells
    changed["scenario"]["evaporator"]["cell_count"] = cells
    result = solve_circuit(CoolPropBackend(), ConvergenceRequest.model_validate(changed))
    assert result.cycle_converged
    # Keep the original 1% criterion for the supported 80-cell example vs 160 cells.
    # The rejected 40-cell experiment is recorded in S2_CONVERGENCE_VALIDATION.md.
    assert abs(result.performance.cooling_cop / solved.performance.cooling_cop - 1) < 0.01
    assert result.performance.relative_energy_error <= 1e-6


def test_no_bracket_is_not_global_infeasibility_and_budget_is_enforced(request_data):
    result = solve_circuit(
        CoolPropBackend(),
        _request(
            request_data,
            lower_enthalpy={"value": 480, "unit": "kJ/kg"},
            upper_enthalpy={"value": 490, "unit": "kJ/kg"},
            scan_intervals=2,
        ),
    )
    assert result.reason == "no-bracket" and not result.cycle_converged
    assert result.performance is None and result.bisection_iterations == 0
    assert all(s.residual is not None for s in result.history)
    budget = solve_circuit(CoolPropBackend(), _request(request_data, max_iterations=1))
    assert budget.reason == "max-iterations" and not budget.cycle_converged
    assert budget.bisection_iterations == 1 and budget.performance is None


def test_property_failure_records_all_trials_and_never_changes_fluid(request_data):
    changed = copy.deepcopy(request_data)
    changed["scenario"]["refrigerant"] = "not-a-fluid"
    changed["settings"]["scan_intervals"] = 2
    result = solve_circuit(CoolPropBackend(), ConvergenceRequest.model_validate(changed))
    assert result.reason == "no-valid-evaluations" and result.performance is None
    assert len(result.history) == 3
    assert all(
        s.status == "invalid-property-state" and s.failed_stage == "suction" for s in result.history
    )
    assert result.last_evaluation.scenario.refrigerant == "not-a-fluid"


@pytest.mark.parametrize(
    "field,value",
    [
        ("scan_intervals", 0),
        ("max_iterations", True),
        ("lower_enthalpy", {"value": 500, "unit": "kJ/kg"}),
        ("enthalpy_tolerance", {"value": 0, "unit": "J/kg"}),
        ("enthalpy_tolerance", {"value": 1, "unit": "K"}),
        ("pressure_tolerance", {"value": 0, "unit": "Pa"}),
        ("temperature_tolerance", {"value": -1, "unit": "K"}),
        ("relative_energy_tolerance", 1e-3),
        ("relative_mass_tolerance", float("nan")),
    ],
)
def test_invalid_settings_rejected(request_data, field, value):
    with pytest.raises(ValidationError):
        _request(request_data, **{field: value})


def test_settings_equivalent_units(request_data, request_model):
    alternate = _request(
        request_data,
        lower_enthalpy={"value": 430000, "unit": "J/kg"},
        upper_enthalpy={"value": 500000, "unit": "J/kg"},
    )
    assert alternate == request_model
    with pytest.raises(ValidationError, match="finite positive span"):
        _request(
            request_data,
            lower_enthalpy={"value": -1e308, "unit": "J/kg"},
            upper_enthalpy={"value": 1e308, "unit": "J/kg"},
        )


def _fake_pass(solved, scenario, h, residual):
    """Numerical search test double; not a physical property model."""
    data = solved.last_evaluation.model_dump(mode="json")
    data["scenario"] = scenario.model_dump(mode="json")
    data["trial_suction_enthalpy"] = {"value": h, "unit": "J/kg"}
    data["nodes"]["suction_trial"]["enthalpy"] = {"value": h, "unit": "J/kg"}
    data["nodes"]["suction_return"]["enthalpy"] = {"value": h + residual, "unit": "J/kg"}
    return data


def _invalid(scenario, h):
    return CircuitResult(
        scenario=scenario,
        trial_suction_enthalpy=h,
        status="invalid-property-state",
        nodes={},
        components=(),
        failed_stage="suction",
        message="synthetic invalid domain gap",
    )


@pytest.mark.parametrize(
    "scan_intervals,expected", [(2, "no-bracket"), (1, "invalid-domain-in-bracket")]
)
def test_invalid_domain_is_never_bridged(
    request_data, solved, monkeypatch, scan_intervals, expected
):
    mid = 465000.0

    def gap(backend, scenario, *, trial_suction_enthalpy):
        h = trial_suction_enthalpy.value
        if h == mid:
            return _invalid(scenario, trial_suction_enthalpy)
        return CircuitResult.model_validate(_fake_pass(solved, scenario, h, -1 if h < mid else 1))

    monkeypatch.setattr(convergence, "evaluate_circuit", gap)
    result = solve_circuit(CoolPropBackend(), _request(request_data, scan_intervals=scan_intervals))
    assert result.reason == expected and result.performance is None
    assert any(s.residual is None for s in result.history)


@pytest.mark.parametrize("broken", ["energy", "mass", "temperature", "return_phase"])
def test_small_h_residual_alone_cannot_claim_convergence(
    request_model, solved, monkeypatch, broken
):
    def corrupt(backend, scenario, *, trial_suction_enthalpy):
        data = _fake_pass(solved, scenario, trial_suction_enthalpy.value, 0)
        if broken == "energy":
            data["components"][0]["work_to_refrigerant"]["value"] *= 2
        elif broken == "mass":
            data["components"][1]["refrigerant_mass_flow"]["value"] *= 2
        elif broken == "temperature":
            data["nodes"]["suction_return"]["temperature"]["value"] += 10
        else:
            data["nodes"]["suction_return"]["phase"] = "liquid"
        return CircuitResult.model_validate(data)

    monkeypatch.setattr(convergence, "evaluate_circuit", corrupt)
    result = solve_circuit(CoolPropBackend(), request_model)
    assert result.reason == "closure-check-failed" and result.performance is None
    assert not result.cycle_converged


def test_discontinuity_stagnates_instead_of_accepting_small_bracket(
    request_data, solved, monkeypatch
):
    def jump(backend, scenario, *, trial_suction_enthalpy):
        h = trial_suction_enthalpy.value
        return CircuitResult.model_validate(
            _fake_pass(solved, scenario, h, -1 if h < 460123 else 1)
        )

    monkeypatch.setattr(convergence, "evaluate_circuit", jump)
    result = solve_circuit(CoolPropBackend(), _request(request_data, scan_intervals=1))
    assert result.reason == "floating-point-stagnation" and result.performance is None


def test_closed_loop_cli_and_iteration_limit_exit_codes(request_data, tmp_path):
    output = tmp_path / "closed.json"
    command = [
        sys.executable,
        str(ROOT / "scripts/run_system_cycle.py"),
        "--mode",
        "closed-loop",
        "--input",
        str(EXAMPLE),
        "--output",
        str(output),
    ]
    process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    assert process.returncode == 0, process.stderr
    artifact = json.loads(output.read_text(encoding="utf-8"))
    assert artifact["mode"] == "closed-loop" and artifact["metadata"]["is_mock"]
    assert ConvergenceResult.model_validate(artifact["result"]).cycle_converged
    limited = copy.deepcopy(request_data)
    limited["settings"]["max_iterations"] = 1
    input_path = tmp_path / "limited.json"
    input_path.write_text(json.dumps(limited), encoding="utf-8")
    command[command.index("--input") + 1] = str(input_path)
    process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    assert process.returncode == 1
    assert json.loads(output.read_text())["result"]["reason"] == "max-iterations"
