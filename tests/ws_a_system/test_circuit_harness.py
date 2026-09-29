"""Physical connection, boundary, failure and CLI tests for the synthetic S1 harness."""

import copy
import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_hvac.components.compressor import evaluate_compressor
from agent_hvac.components.expansion_valve import evaluate_expansion_valve
from agent_hvac.components.heat_exchanger_1d import (
    HeatExchanger1DInput,
    HeatExchangerMode,
    evaluate_heat_exchanger_1d,
)
from agent_hvac.properties.coolprop_backend import CoolPropBackend
from agent_hvac.solvers.system_cycle import (
    CircuitResult,
    SyntheticScenario,
    evaluate_circuit,
    harness,
)
from agent_hvac.utils.units import PressureDifference

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples/system_cycle/r744_single_pass.json"


@pytest.fixture
def raw():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


@pytest.fixture
def scenario(raw):
    return SyntheticScenario.model_validate(raw)


def test_connects_unchanged_components_preserves_open_loop_and_profiles(scenario):
    backend = CoolPropBackend()
    result = evaluate_circuit(backend, scenario)
    assert result.status == "evaluated"
    assert result.cycle_converged is False
    assert result.is_mock is True
    assert [c.component for c in result.components] == [
        "compressor",
        "gas_cooler",
        "valve",
        "evaporator",
    ]
    suction = backend.state_pt(
        scenario.refrigerant, scenario.suction_pressure, scenario.trial_suction_temperature
    )
    comp = evaluate_compressor(
        backend,
        suction,
        scenario.discharge_pressure,
        scenario.compressor_isentropic_efficiency.value,
    )
    gc = evaluate_heat_exchanger_1d(
        backend,
        HeatExchanger1DInput(
            mode=HeatExchangerMode.GAS_COOLER,
            refrigerant_inlet_state=comp.outlet,
            refrigerant_mass_flow=scenario.refrigerant_mass_flow,
            refrigerant_pressure_drop=PressureDifference(value=0, unit="Pa"),
            **scenario.gas_cooler.model_dump(exclude={"source_ref"}),
        ),
    )
    valve = evaluate_expansion_valve(
        backend, gc.refrigerant_outlet_state, scenario.suction_pressure
    )
    ev = evaluate_heat_exchanger_1d(
        backend,
        HeatExchanger1DInput(
            mode=HeatExchangerMode.EVAPORATOR,
            refrigerant_inlet_state=valve,
            refrigerant_mass_flow=scenario.refrigerant_mass_flow,
            refrigerant_pressure_drop=PressureDifference(value=0, unit="Pa"),
            **scenario.evaporator.model_dump(exclude={"source_ref"}),
        ),
    )
    assert result.nodes == {
        "suction_trial": suction,
        "compressor_outlet": comp.outlet,
        "gas_cooler_outlet": gc.refrigerant_outlet_state,
        "valve_outlet": valve,
        "suction_return": ev.refrigerant_outlet_state,
    }
    assert result.components[1].heat_exchanger == gc
    assert result.components[3].heat_exchanger == ev
    assert len(gc.cells) == len(ev.cells) == 80
    assert result.nodes["valve_outlet"].phase == "twophase"
    d = result.diagnostics
    assert d is not None
    # P02 compressor reference and new S1 CoolProp-8 regression, not manufacturer truth.
    assert d.compressor_power.value == pytest.approx(6388.690872445994, rel=1e-9)
    assert d.gas_cooler_heat_rejection.value == pytest.approx(9419.30248152867, rel=1e-9)
    assert d.evaporator_heat.value == pytest.approx(4062.7768765939477, rel=1e-9)
    assert d.enthalpy_return_minus_trial.value == pytest.approx(10321.652675112535, rel=1e-9)
    assert d.temperature_return_minus_trial.value == pytest.approx(7.991656320454467, rel=1e-9)
    assert d.pressure_return_minus_trial.value == 0
    assert d.relative_transport_energy_error < 1e-10
    # Good transfer accounting does not close the loop: about 1 kW remains unbalanced.
    assert d.net_heat_and_work_to_refrigerant.value > 1000
    assert result.nodes["suction_return"] != result.nodes["suction_trial"]
    assert CircuitResult.model_validate_json(result.model_dump_json()) == result
    assert evaluate_circuit(backend, scenario) == result


def test_equivalent_units_and_scenario_json_roundtrip(raw):
    normalized = copy.deepcopy(raw)
    normalized["suction_pressure"] = {"value": 3e6, "unit": "Pa"}
    normalized["discharge_pressure"] = {"value": 9e6, "unit": "Pa"}
    normalized["refrigerant_mass_flow"] = {"value": 0.1, "unit": "kg/s"}
    normalized["gas_cooler"]["total_thermal_conductance"] = {"value": 200, "unit": "W/K"}
    first = SyntheticScenario.model_validate(raw)
    second = SyntheticScenario.model_validate(normalized)
    assert first == second
    assert SyntheticScenario.model_validate_json(first.model_dump_json()) == first
    assert evaluate_circuit(CoolPropBackend(), first) == evaluate_circuit(CoolPropBackend(), second)


@pytest.mark.parametrize(
    "field,value",
    [
        ("is_mock", False),
        ("suction_pressure", {"value": 0, "unit": "Pa"}),
        ("discharge_pressure", {"value": 20, "unit": "bar"}),
        ("trial_suction_temperature", {"value": 0, "unit": "K"}),
        ("refrigerant_mass_flow", {"value": 1, "unit": "m"}),
        ("refrigerant_mass_flow", {"value": float("inf"), "unit": "kg/s"}),
        ("compressor_isentropic_efficiency", {"value": 1.1, "unit": "dimensionless"}),
        ("compressor_isentropic_efficiency", {"value": 0.8, "unit": "m"}),
        ("assumptions", []),
        ("source_ref", ""),
        ("product_id", "unexpected-db-field"),
    ],
)
def test_rejects_invalid_or_nonmock_inputs(raw, field, value):
    raw[field] = value
    with pytest.raises(ValidationError):
        SyntheticScenario.model_validate(raw)


def test_missing_boundary_and_invalid_hx_parameters(raw):
    del raw["gas_cooler"]["secondary_mass_flow"]
    with pytest.raises(ValidationError, match="secondary_mass_flow"):
        SyntheticScenario.model_validate(raw)
    raw["gas_cooler"]["secondary_mass_flow"] = {"value": 1, "unit": "kg/s"}
    raw["evaporator"]["cell_count"] = True
    with pytest.raises(ValidationError, match="cell_count"):
        SyntheticScenario.model_validate(raw)
    raw["evaporator"]["cell_count"] = 80
    raw["evaporator"]["total_thermal_conductance"] = {"value": -1, "unit": "W/K"}
    with pytest.raises(ValidationError, match="nonnegative"):
        SyntheticScenario.model_validate(raw)


@pytest.mark.parametrize(
    "stage,field,value,completed",
    [
        ("suction", "refrigerant", "not-a-fluid", 0),
        ("compressor", "trial_suction_temperature", {"value": 250, "unit": "K"}, 0),
        ("gas_cooler", "gas_cooler", {"value": 400, "unit": "K"}, 1),
        ("evaporator", "evaporator", {"value": 260, "unit": "K"}, 3),
    ],
)
def test_failures_keep_stage_and_prior_results_without_fallback(
    raw, stage, field, value, completed
):
    if field in ("gas_cooler", "evaporator"):
        raw[field]["secondary_inlet_temperature"] = value
    else:
        raw[field] = value
    result = evaluate_circuit(CoolPropBackend(), SyntheticScenario.model_validate(raw))
    assert result.status == ("invalid-property-state" if stage == "suction" else "infeasible")
    assert result.failed_stage == stage
    assert result.message
    assert len(result.components) == completed
    assert result.diagnostics is None
    assert not result.cycle_converged
    assert result.scenario.refrigerant == raw["refrigerant"]
    assert "suction_return" not in result.nodes


def test_bad_component_energy_is_rejected_and_unknown_errors_are_not_hidden(scenario, monkeypatch):
    def bad_energy(*args):
        correct = evaluate_compressor(*args)
        return replace(correct, specific_work_j_kg=correct.specific_work_j_kg * 2)

    monkeypatch.setattr(harness, "evaluate_compressor", bad_energy)
    result = evaluate_circuit(CoolPropBackend(), scenario)
    assert result.status == "component-numerical-failure"
    assert result.failed_stage == "compressor"
    assert "energy" in result.message
    assert result.components == ()

    def bug(*args):
        raise RuntimeError("unexpected implementation defect")

    monkeypatch.setattr(harness, "evaluate_compressor", bug)
    with pytest.raises(RuntimeError, match="implementation defect"):
        evaluate_circuit(CoolPropBackend(), scenario)


def test_zero_ua_is_explicit_and_does_not_imply_closed_cycle(raw):
    raw["evaporator"]["total_thermal_conductance"] = {"value": 0, "unit": "W/K"}
    result = evaluate_circuit(CoolPropBackend(), SyntheticScenario.model_validate(raw))
    assert result.status == "evaluated"
    assert result.diagnostics.evaporator_heat.value == 0
    assert result.nodes["suction_return"].phase == "twophase"
    assert not result.cycle_converged


def _cli(input_path, output_path):
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/run_system_cycle.py"),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_archives_original_units_fingerprints_and_typed_result(tmp_path):
    output = tmp_path / "run.json"
    process = _cli(EXAMPLE, output)
    assert process.returncode == 0, process.stderr
    artifact = json.loads(output.read_text(encoding="utf-8"))
    assert artifact["original_input"]["suction_pressure"]["unit"] == "bar"
    assert artifact["metadata"]["input_sha256"] == hashlib.sha256(EXAMPLE.read_bytes()).hexdigest()
    assert artifact["metadata"]["coolprop"] == "8.0.0"
    assert artifact["metadata"]["db_version"] == "N/A - no DB"
    assert artifact["metadata"]["source_sha256"]
    result = CircuitResult.model_validate(artifact["result"])
    assert result.status == "evaluated" and not result.cycle_converged


def test_cli_failure_input_and_output_safety(raw, tmp_path):
    input_path, output = tmp_path / "input.json", tmp_path / "out.json"
    raw["refrigerant"] = "not-a-fluid"
    input_path.write_text(json.dumps(raw), encoding="utf-8")
    assert _cli(input_path, output).returncode == 1
    assert json.loads(output.read_text())["result"]["failed_stage"] == "suction"
    before = input_path.read_bytes()
    assert _cli(input_path, input_path).returncode == 2
    assert input_path.read_bytes() == before
    raw["is_mock"] = False
    input_path.write_text(json.dumps(raw), encoding="utf-8")
    before = output.read_bytes()
    assert _cli(input_path, output).returncode == 2
    assert output.read_bytes() == before
    assert _cli(tmp_path / "missing.json", output).returncode == 2
