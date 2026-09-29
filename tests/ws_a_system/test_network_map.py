"""Network conservation, zero-loss reduction, grid completeness and failure policies."""

import copy
import csv
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_hvac.properties.coolprop_backend import CoolPropBackend
from agent_hvac.solvers.system_cycle import (
    ConvergenceRequest,
    ConvergenceResult,
    network,
    solve_circuit,
)
from agent_hvac.solvers.system_cycle.models import CircuitResult
from agent_hvac.solvers.system_cycle.operating_map import (
    OperatingMapRequest,
    OperatingMapResult,
    operating_map_csv,
    solve_operating_map,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def network_data():
    return json.loads((ROOT / "examples/system_cycle/r744_network.json").read_text())


@pytest.fixture(scope="module")
def network_result(network_data):
    return solve_circuit(CoolPropBackend(), ConvergenceRequest.model_validate(network_data))


def test_real_network_closes_pressure_energy_and_preserves_all_pipe_nodes(network_result):
    solved = network_result
    assert solved.cycle_converged, solved.model_dump_json()
    circuit = solved.last_evaluation
    assert len(circuit.nodes) == 8 and len(circuit.components) == 7
    assert abs(circuit.diagnostics.pressure_return_minus_trial.value) <= 0.01
    assert abs(circuit.diagnostics.enthalpy_return_minus_trial.value) <= 0.01
    assert solved.performance.relative_energy_error <= 1e-6
    assert solved.performance.relative_mass_error <= 1e-12
    assert (
        circuit.nodes["valve_outlet"].pressure.value
        > circuit.scenario.suction_pressure.value + 5000
    )
    pipe_traces = [t for t in circuit.components if t.pipe]
    assert len(pipe_traces) == 3 and all(t.pipe.total_pressure_drop.value > 0 for t in pipe_traces)
    assert any(t.heat_to_refrigerant.value > 0 for t in pipe_traces)
    assert any(t.heat_to_refrigerant.value < 0 for t in pipe_traces)
    for a, b in zip(circuit.components, circuit.components[1:], strict=False):
        assert a.outlet_node == b.inlet_node
    net = sum(t.heat_to_refrigerant.value + t.work_to_refrigerant.value for t in circuit.components)
    assert abs(net) < 0.001
    assert sum(len(h.pressure_history) for h in solved.history) > len(solved.history)
    assert ConvergenceResult.model_validate_json(solved.model_dump_json()) == solved


def test_zero_loss_network_reduces_to_s2_without_return_overwrite(network_data):
    data = copy.deepcopy(network_data)
    config = data["scenario"]["network"]
    for name in ("discharge_pipe", "high_side_pipe", "suction_pipe"):
        config[name]["length"]["value"] = 0
    for name in ("gas_cooler_pressure_drop", "evaporator_pressure_drop"):
        config[name]["value"] = 0
    result = solve_circuit(CoolPropBackend(), ConvergenceRequest.model_validate(data))
    assert result.cycle_converged
    assert result.performance.cooling_cop == pytest.approx(0.5199018794, abs=2e-6)
    assert (
        result.last_evaluation.nodes["suction_return"]
        != result.last_evaluation.nodes["suction_trial"]
    )
    assert all(len(s.pressure_history) == 1 for s in result.history)


def test_small_heat_pipe_failure_is_retained_not_relaxed(network_data):
    from agent_hvac.utils.units import Pressure, SpecificEnthalpy

    data = copy.deepcopy(network_data)
    for key in ("discharge_pipe", "high_side_pipe", "suction_pipe"):
        data["scenario"]["network"][key]["linear_heat_transfer_coefficient"]["value"] = 0.5
    req = ConvergenceRequest.model_validate(data)
    result = network.traverse_network(
        CoolPropBackend(),
        req.scenario,
        SpecificEnthalpy(value=450000, unit="J/kg"),
        Pressure(value=3e6, unit="Pa"),
    )
    # At this tiny heat flow, CoolProp/binary64 rounding can put the suction
    # pipe residual on either side of the unchanged 1e-12 closure limit.
    if result.status == "component-numerical-failure":
        assert result.failed_stage == "suction_pipe" and "energy closure" in result.message
        assert result.diagnostics is None
    else:
        assert result.status == "evaluated", result.model_dump_json()
        assert result.diagnostics is not None
        assert len(result.components) == 7
        assert all(
            trace.pipe.relative_energy_residual <= 1e-12
            for trace in result.components
            if trace.pipe is not None
        )


def test_pipe_energy_closure_failure_retains_network_stage(network_data, monkeypatch):
    from agent_hvac.utils.exceptions import ConvergenceError
    from agent_hvac.utils.units import Pressure, SpecificEnthalpy

    data = copy.deepcopy(network_data)
    for key in ("discharge_pipe", "high_side_pipe", "suction_pipe"):
        data["scenario"]["network"][key]["linear_heat_transfer_coefficient"]["value"] = 0.5
    req = ConvergenceRequest.model_validate(data)
    actual_evaluate = network.evaluate_pipe_1d
    pipe_calls = 0

    def closure_failure_at_suction(*args, **kwargs):
        nonlocal pipe_calls
        pipe_calls += 1
        if pipe_calls == 3:
            raise ConvergenceError("pipe energy closure residual 2e-12 exceeds 1e-12")
        return actual_evaluate(*args, **kwargs)

    monkeypatch.setattr(network, "evaluate_pipe_1d", closure_failure_at_suction)
    result = network.traverse_network(
        CoolPropBackend(),
        req.scenario,
        SpecificEnthalpy(value=450000, unit="J/kg"),
        Pressure(value=3e6, unit="Pa"),
    )
    assert pipe_calls == 3
    assert result.status == "component-numerical-failure"
    assert result.failed_stage == "suction_pipe"
    assert "energy closure" in result.message
    assert result.diagnostics is None


def _numerical_traversal(network_result, scenario, h, p, residual):
    data = network_result.last_evaluation.model_dump(mode="json")
    data["scenario"] = scenario.model_dump(mode="json")
    data["diagnostics"]["pressure_return_minus_trial"] = {"value": residual, "unit": "Pa"}
    return CircuitResult.model_validate(data)


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("gap", "pressure-invalid-domain"),
        ("positive", "pressure-no-valid-bracket"),
        ("jump", "pressure-max-iterations"),
    ],
)
def test_pressure_solver_does_not_accept_gaps_or_iteration_limits(
    network_data, network_result, monkeypatch, mode, expected
):
    data = copy.deepcopy(network_data)
    data["scenario"]["network"]["pressure_scan_intervals"] = 1
    data["scenario"]["network"]["pressure_max_iterations"] = 2
    req = ConvergenceRequest.model_validate(data)

    def fake(backend, scenario, h, p):
        if mode == "gap" and 3e6 < p.value < 3.1e6:
            return CircuitResult(
                scenario=scenario,
                status="invalid-property-state",
                nodes={},
                components=(),
                failed_stage="evaporator",
                message="synthetic invalid gap",
            )
        residual = 1 if mode == "positive" or p.value >= 3.04e6 else -1
        return _numerical_traversal(network_result, scenario, h, p, residual)

    monkeypatch.setattr(network, "traverse_network", fake)
    result = network.evaluate_network(CoolPropBackend(), req.scenario, None)
    assert result.status != "evaluated" and expected in result.message
    assert result.pressure_history and result.diagnostics is None


def test_map_grid_failures_csv_reproducibility_and_no_mutation(
    network_data, network_result, monkeypatch
):
    from agent_hvac.solvers.system_cycle import operating_map

    calls = []

    def fake(backend, request):
        calls.append(request)
        data = network_result.model_dump(mode="json")
        data["request"] = request.model_dump(mode="json")
        if request.scenario.gas_cooler.secondary_inlet_temperature.value == 400:
            data.update(
                status="unconverged",
                cycle_converged=False,
                performance=None,
                reason="no-bracket",
                message="No physical root sampled",
            )
        return ConvergenceResult.model_validate(data)

    monkeypatch.setattr(operating_map, "solve_circuit", fake)
    raw = {
        "base": network_data,
        "discharge_pressures": [{"value": 90, "unit": "bar"}, {"value": 20, "unit": "bar"}],
        "sink_inlet_temperatures": [{"value": 290, "unit": "K"}, {"value": 400, "unit": "K"}],
        "max_points": 4,
    }
    req = OperatingMapRequest.model_validate(raw)
    before = req.model_dump_json()
    result = solve_operating_map(CoolPropBackend(), req)
    assert [p.status for p in result.points] == [
        "converged",
        "unconverged",
        "invalid-input",
        "invalid-input",
    ]
    assert result.converged_count == 1 and result.failed_count == 3
    assert req.model_dump_json() == before
    assert all(r.settings == req.base.settings for r in calls)
    assert solve_operating_map(CoolPropBackend(), req) == result
    assert OperatingMapResult.model_validate_json(result.model_dump_json()) == result
    rows = list(csv.DictReader(io.StringIO(operating_map_csv(result))))
    assert len(rows) == 4 and rows[0]["cooling_COP"]
    assert all(row["cooling_COP"] == "" for row in rows[1:])
    assert all(row["reason"] for row in rows)
    broken = result.model_dump(mode="json")
    broken["points"].pop()
    with pytest.raises(ValidationError):
        OperatingMapResult.model_validate(broken)
    raw["max_points"] = 3
    with pytest.raises(ValidationError):
        OperatingMapRequest.model_validate(raw)
    raw["max_points"] = 4
    raw["discharge_pressures"][1] = {"value": 9e6, "unit": "Pa"}
    with pytest.raises(ValidationError):
        OperatingMapRequest.model_validate(raw)


def test_real_invalid_map_cli_writes_every_point_and_returns_nonzero(network_data, tmp_path):
    raw = {
        "base": network_data,
        "discharge_pressures": [{"value": 20, "unit": "bar"}],
        "sink_inlet_temperatures": [{"value": 290, "unit": "K"}],
        "max_points": 1,
    }
    inp, out, summary = tmp_path / "input.json", tmp_path / "out.json", tmp_path / "out.csv"
    inp.write_text(json.dumps(raw))
    command = [
        sys.executable,
        str(ROOT / "scripts/run_system_cycle.py"),
        "--mode",
        "map",
        "--input",
        str(inp),
        "--output",
        str(out),
        "--csv",
        str(summary),
    ]
    run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert run.returncode == 1, run.stderr
    result = json.loads(out.read_text())["result"]
    assert result["failed_count"] == 1 and result["points"][0]["status"] == "invalid-input"
    assert len(list(csv.DictReader(io.StringIO(summary.read_text())))) == 1
    assert b"\r\r\n" not in summary.read_bytes()
    command[-1] = str(inp)
    run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert run.returncode == 2
    assert json.loads(inp.read_text()) == raw


def test_mass_axis_preserves_every_coordinate_and_failed_csv_flow(network_data, monkeypatch):
    from agent_hvac.solvers.system_cycle import operating_map

    calls = []

    def fail(backend, request):
        calls.append(request)
        return ConvergenceResult(
            request=request,
            cycle_converged=False,
            status="unconverged",
            reason="no-bracket",
            message="Controlled numerical test failure",
            bisection_iterations=0,
            history=(),
            last_evaluation=None,
        )

    monkeypatch.setattr(operating_map, "solve_circuit", fail)
    raw = {
        "base": network_data,
        "discharge_pressures": [{"value": 90, "unit": "bar"}, {"value": 20, "unit": "bar"}],
        "sink_inlet_temperatures": [{"value": 290, "unit": "K"}, {"value": 295, "unit": "K"}],
        "mass_flows": [{"value": 288, "unit": "kg/h"}, {"value": 0.12, "unit": "kg/s"}],
        "max_points": 8,
    }
    req = OperatingMapRequest.model_validate(raw)
    before = req.model_dump_json()
    result = solve_operating_map(CoolPropBackend(), req)
    assert result.failed_count == 8 and len(calls) == 4
    assert [p.prescribed_mass_flow.value for p in result.points] == [0.08, 0.12] * 4
    assert [p.status for p in result.points] == ["unconverged"] * 4 + ["invalid-input"] * 4
    assert [r.scenario.refrigerant_mass_flow.value for r in calls] == [0.08, 0.12] * 2
    assert req.model_dump_json() == before
    rows = list(csv.DictReader(io.StringIO(operating_map_csv(result))))
    assert [float(row["prescribed_mass_flow_kg_s"]) for row in rows] == [0.08, 0.12] * 4
    assert all(not row["cooling_COP"] for row in rows)
    assert OperatingMapResult.model_validate_json(result.model_dump_json()) == result
    assert solve_operating_map(CoolPropBackend(), req) == result
    for field, value in (
        ("prescribed_mass_flow", None),
        ("prescribed_mass_flow", {"value": 0.1, "unit": "kg/s"}),
    ):
        broken = result.model_dump(mode="json")
        broken["points"][0][field] = value
        with pytest.raises(ValidationError):
            OperatingMapResult.model_validate(broken)
    broken = result.model_dump(mode="json")
    broken["points"][0]["result"]["request"]["scenario"]["refrigerant_mass_flow"]["value"] = 0.1
    with pytest.raises(ValidationError, match="solved request differs"):
        OperatingMapResult.model_validate(broken)
    raw["max_points"] = 7
    with pytest.raises(ValidationError, match="exceeds"):
        OperatingMapRequest.model_validate(raw)
    raw["max_points"] = 8
    raw["mass_flows"][1] = {"value": 0.08, "unit": "kg/s"}
    with pytest.raises(ValidationError, match="duplicate"):
        OperatingMapRequest.model_validate(raw)
    for invalid in (
        [],
        [{"value": 0, "unit": "kg/s"}],
        [{"value": -1, "unit": "kg/s"}],
        [{"value": 1, "unit": "bar"}],
    ):
        raw["mass_flows"] = invalid
        with pytest.raises(ValidationError):
            OperatingMapRequest.model_validate(raw)


def test_legacy_two_axis_artifacts_keep_base_flow(network_data, monkeypatch):
    from agent_hvac.solvers.system_cycle import operating_map

    def fail(backend, request):
        return ConvergenceResult(
            request=request,
            cycle_converged=False,
            status="unconverged",
            reason="no-bracket",
            message="Controlled test failure",
            bisection_iterations=0,
            history=(),
            last_evaluation=None,
        )

    monkeypatch.setattr(operating_map, "solve_circuit", fail)
    req = OperatingMapRequest.model_validate(
        {
            "base": network_data,
            "discharge_pressures": [{"value": 90, "unit": "bar"}],
            "sink_inlet_temperatures": [{"value": 290, "unit": "K"}],
            "max_points": 1,
        }
    )
    data = solve_operating_map(CoolPropBackend(), req).model_dump(mode="json")
    del data["request"]["mass_flows"]
    del data["points"][0]["prescribed_mass_flow"]
    restored = OperatingMapResult.model_validate(data)
    row = next(csv.DictReader(io.StringIO(operating_map_csv(restored))))
    assert float(row["prescribed_mass_flow_kg_s"]) == 0.1


def test_map_does_not_hide_unexpected_solver_errors(network_data, monkeypatch):
    from agent_hvac.solvers.system_cycle import operating_map

    def broken(backend, request):
        raise RuntimeError("unexpected solver defect")

    monkeypatch.setattr(operating_map, "solve_circuit", broken)
    req = OperatingMapRequest.model_validate(
        {
            "base": network_data,
            "discharge_pressures": [{"value": 90, "unit": "bar"}],
            "sink_inlet_temperatures": [{"value": 290, "unit": "K"}],
            "mass_flows": [{"value": 0.08, "unit": "kg/s"}],
            "max_points": 1,
        }
    )
    with pytest.raises(RuntimeError, match="unexpected solver defect"):
        solve_operating_map(CoolPropBackend(), req)


@pytest.mark.parametrize(
    "pressure,temperature,enthalpy", [(90, 305, 468125), (100, 285, 454531.25), (100, 305, 466250)]
)
def test_pressure_audit_replays_real_mpa_cancellation_cases(
    network_data, pressure, temperature, enthalpy
):
    from agent_hvac.utils.units import Pressure, SpecificEnthalpy

    data = copy.deepcopy(network_data)
    data["scenario"]["discharge_pressure"] = {"value": pressure, "unit": "bar"}
    data["scenario"]["gas_cooler"]["secondary_inlet_temperature"] = {
        "value": temperature,
        "unit": "K",
    }
    data["scenario"]["refrigerant_mass_flow"] = {"value": 0.08, "unit": "kg/s"}
    req = ConvergenceRequest.model_validate(data)
    result = network.traverse_network(
        CoolPropBackend(),
        req.scenario,
        SpecificEnthalpy(value=enthalpy, unit="J/kg"),
        Pressure(value=3e6, unit="Pa"),
    )
    assert result.status == "evaluated", result.message
    assert not result.cycle_converged  # This is one traversal, not a root.
    for trace in result.components:
        if trace.pipe:
            network._audit_pipe_pressure(trace.pipe, result.nodes[trace.inlet_node])


def test_pressure_trace_audit_rejects_corrupt_outlet_loss_and_cell_chain(network_result):
    from dataclasses import replace

    from agent_hvac.utils.exceptions import ConvergenceError
    from agent_hvac.utils.units import Pressure, PressureDifference

    pipe = next(t.pipe for t in network_result.last_evaluation.components if t.pipe)
    inlet = pipe.inlet_state
    shifted = pipe.outlet_state.model_copy(
        update={"pressure": Pressure(value=pipe.outlet_state.pressure.value + 0.001, unit="Pa")}
    )
    with pytest.raises(ConvergenceError, match="outlet differs"):
        network._audit_pipe_pressure(replace(pipe, outlet_state=shifted), inlet)
    with pytest.raises(ConvergenceError, match="pressure loss sum"):
        network._audit_pipe_pressure(
            replace(
                pipe,
                total_pressure_drop=PressureDifference(
                    value=pipe.total_pressure_drop.value + 0.01, unit="Pa"
                ),
            ),
            inlet,
        )
    bad_cell = replace(pipe.cells[-1], outlet_state=shifted)
    with pytest.raises(ConvergenceError, match="marching identity"):
        network._audit_pipe_pressure(replace(pipe, cells=(*pipe.cells[:-1], bad_cell)), inlet)
    bad_cell = replace(pipe.cells[1], inlet_state=inlet)
    with pytest.raises(ConvergenceError, match="chain is discontinuous"):
        network._audit_pipe_pressure(
            replace(pipe, cells=(pipe.cells[0], bad_cell, *pipe.cells[2:])), inlet
        )
