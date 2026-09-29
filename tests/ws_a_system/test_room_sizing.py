"""Real R410A closure plus explicitly scripted outer-search failure-policy tests."""

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_hvac.properties.coolprop_backend import CoolPropBackend
from agent_hvac.solvers.system_cycle import (
    ConvergenceRequest,
    ConvergenceResult,
    room_sizing,
    solve_circuit,
)
from agent_hvac.solvers.system_cycle.harness import evaluate_circuit
from agent_hvac.solvers.system_cycle.models import SyntheticScenario
from agent_hvac.solvers.system_cycle.operating_map import (
    OperatingMapRequest,
    operating_map_csv,
    solve_operating_map,
)
from agent_hvac.solvers.system_cycle.room_sizing import (
    RoomSizingRequest,
    RoomSizingResult,
    size_room_cooling,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def data():
    return json.loads(
        (ROOT / "examples/system_cycle/r410a_room21_diagnostic_air15.json").read_text()
    )


@pytest.fixture(scope="module")
def solved(data):
    return solve_circuit(CoolPropBackend(), ConvergenceRequest.model_validate(data["base"]))


def test_real_condenser_network_preserves_user_flow_and_conservation(solved):
    assert solved.cycle_converged
    c = solved.last_evaluation
    assert [t.component for t in c.components] == [
        "compressor",
        "discharge_pipe",
        "condenser",
        "high_side_pipe",
        "valve",
        "evaporator",
        "suction_pipe",
    ]
    assert all(t.refrigerant_mass_flow.value == 0.05 for t in c.components)
    assert c.nodes["condenser_outlet"].phase == "liquid"
    assert c.nodes["suction_return"].phase == "gas"
    assert c.nodes["suction_trial"] != c.nodes["suction_return"]
    assert c.diagnostics.gas_cooler_heat_rejection is None
    assert c.diagnostics.condenser_heat_rejection.value > 0
    assert solved.performance.relative_energy_error <= 1e-6
    assert solved.performance.relative_mass_error <= 1e-12
    assert abs(c.diagnostics.enthalpy_return_minus_trial.value) <= 0.01
    assert abs(c.diagnostics.pressure_return_minus_trial.value) <= 0.01
    hx = c.components[2].heat_exchanger
    assert hx.mode == "condenser" and "twophase" in hx.phase_profile


def test_s1_zero_loss_reduces_to_same_nodes(data, solved):
    d = copy.deepcopy(data["base"]["scenario"])
    d["network"] = None
    result = evaluate_circuit(
        CoolPropBackend(),
        SyntheticScenario.model_validate(d),
        trial_suction_enthalpy=solved.last_evaluation.nodes["suction_trial"].enthalpy,
    )
    assert result.status == "evaluated" and not result.cycle_converged
    for name in ["compressor_outlet", "condenser_outlet", "valve_outlet", "suction_return"]:
        assert result.nodes[name].enthalpy.value == pytest.approx(
            solved.last_evaluation.nodes[name].enthalpy.value, abs=0.01
        )


def test_initial_two_phase_pipe_failure_is_not_bypassed():
    d = json.loads((ROOT / "examples/system_cycle/r410a_room21_cycle.json").read_text())
    result = evaluate_circuit(CoolPropBackend(), ConvergenceRequest.model_validate(d).scenario)
    assert result.status == "component-numerical-failure"
    assert any(
        p.failed_stage == "high_side_pipe" and "two-phase" in p.message
        for p in result.pressure_history
    )
    assert not result.cycle_converged and result.diagnostics is None


def test_real_room_evaluation_separates_cycle_from_load(data, solved, monkeypatch):
    # Reuse one genuinely calculated cycle; this test checks load postprocessing.
    monkeypatch.setattr(room_sizing, "solve_circuit", lambda backend, req: solved)
    result = size_room_cooling(CoolPropBackend(), RoomSizingRequest.model_validate(data))
    assert result.cycle_converged and not result.load_balance_satisfied
    assert not result.design_target_satisfied
    assert result.history[-1].load_residual.value > 3000
    assert abs(result.history[-1].air_balance_error.value) < 1e-6
    assert RoomSizingResult.model_validate_json(result.model_dump_json()) == result


def _scripted(solved, request, q):
    """Deliberate outer-solver test double; not a physical cycle benchmark."""
    d = solved.model_dump(mode="json")
    d["request"] = request.model_dump(mode="json")
    if q is None:
        d.update(
            status="unconverged",
            cycle_converged=False,
            performance=None,
            reason="scripted-invalid-domain",
        )
    else:
        d["last_evaluation"]["diagnostics"]["evaporator_heat"] = {"value": q, "unit": "W"}
        cfg = request.scenario.evaporator
        supply = cfg.secondary_inlet_temperature.value - q / (
            cfg.secondary_mass_flow.value * cfg.secondary_specific_heat_capacity.value
        )
        for trace in d["last_evaluation"]["components"]:
            if trace["component"] == "evaporator":
                trace["heat_exchanger"]["secondary_outlet_temperature"] = {
                    "value": supply,
                    "unit": "K",
                }
    return ConvergenceResult.model_validate(d)


@pytest.mark.parametrize("mode", ["success", "hole", "midpoint-invalid", "budget", "exception"])
def test_bounded_outer_search_and_failure_policies(data, solved, monkeypatch, mode):
    d = copy.deepcopy(data)
    d["ua_samples"] = [
        {"value": v, "unit": "W/K"} for v in ([100, 200, 400] if mode == "hole" else [100, 400])
    ]
    if mode == "budget":
        d["max_iterations"] = 1
    visited = []

    def stub(backend, req):
        ua = req.scenario.evaporator.total_thermal_conductance.value
        visited.append(ua)
        if mode == "exception":
            raise RuntimeError("unexpected backend defect")
        q = 10 * ua
        if (mode == "hole" and ua == 200) or (mode == "midpoint-invalid" and ua == 250):
            q = None
        return _scripted(solved, req, q)

    monkeypatch.setattr(room_sizing, "solve_circuit", stub)
    if mode == "exception":
        with pytest.raises(RuntimeError, match="unexpected"):
            size_room_cooling(CoolPropBackend(), RoomSizingRequest.model_validate(d))
        return
    r = size_room_cooling(CoolPropBackend(), RoomSizingRequest.model_validate(d))
    assert r.design_target_satisfied == (mode == "success")
    assert all(100 <= u <= 400 for u in visited)
    if mode == "hole":
        assert visited == [100, 200, 400]
    if mode == "midpoint-invalid":
        assert r.reason == "invalid-cycle-in-load-bracket"
    if mode == "budget":
        assert r.reason == "max-iterations"


@pytest.mark.parametrize(
    "field,value",
    [
        ("room_temperature", {"value": 22, "unit": "degC"}),
        ("sensible_load", {"value": -1, "unit": "W"}),
        ("load_tolerance", {"value": 2, "unit": "W"}),
        ("ua_samples", [{"value": 200, "unit": "W/K"}, {"value": 100, "unit": "W/K"}]),
    ],
)
def test_invalid_room_boundaries_rejected(data, field, value):
    d = copy.deepcopy(data)
    d[field] = value
    with pytest.raises(ValidationError):
        RoomSizingRequest.model_validate(d)


def test_condenser_map_labels(data, solved, monkeypatch):
    import agent_hvac.solvers.system_cycle.operating_map as module

    monkeypatch.setattr(module, "solve_circuit", lambda backend, req: solved)
    r = solve_operating_map(
        CoolPropBackend(),
        OperatingMapRequest.model_validate(
            {
                "base": data["base"],
                "discharge_pressures": [{"value": 3.5e6, "unit": "Pa"}],
                "sink_inlet_temperatures": [{"value": 308.15, "unit": "K"}],
                "max_points": 1,
            }
        ),
    )
    header = operating_map_csv(r).splitlines()[0]
    assert "condenser_rejection_W" in header and "gas_cooler" not in header
