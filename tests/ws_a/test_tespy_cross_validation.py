from dataclasses import replace

import pytest

from agent_hvac.physics.cycle import BaselineCycleInputs
from agent_hvac.solvers.tespy_reference import (
    P03_RELATIVE_TOLERANCE,
    TespyCrossValidationError,
    compare_cycle_results,
    run_p03_cross_validation,
    solve_tespy_reference,
)
from agent_hvac.utils.exceptions import InfeasibleDesignError
from agent_hvac.utils.units import MassFlow, Pressure, Temperature


def _inputs(*, fluid: str = "R744") -> BaselineCycleInputs:
    return BaselineCycleInputs(
        fluid=fluid,
        evaporator_pressure=Pressure(value=3_000_000.0, unit="Pa"),
        high_side_pressure=Pressure(value=9_000_000.0, unit="Pa"),
        compressor_inlet_temperature=Temperature(value=280.0, unit="K"),
        heat_rejection_outlet_temperature=Temperature(value=310.0, unit="K"),
        refrigerant_mass_flow=MassFlow(value=0.1, unit="kg/s"),
        compressor_isentropic_efficiency=0.8,
    )


def test_tespy_reference_cycle_matches_frozen_r744_values() -> None:
    result = solve_tespy_reference(_inputs())

    assert result.converged
    assert result.state_points["compressor_inlet"].temperature_k == pytest.approx(280.0)
    assert result.state_points["compressor_outlet"].temperature_k == pytest.approx(
        375.6681128336461, rel=1e-10
    )
    assert result.state_points["expansion_valve_outlet"].enthalpy_j_kg == pytest.approx(
        311_097.4821809954, rel=1e-10
    )
    assert result.compressor_power_w == pytest.approx(6_388.69087287793, rel=1e-10)
    assert result.evaporator_capacity_w == pytest.approx(14_072.21740023194, rel=1e-10)
    assert result.heat_rejection_w == pytest.approx(20_460.90827310987, rel=1e-10)
    assert result.cop == pytest.approx(2.202676210234726, rel=1e-10)


def test_p02_and_tespy_agree_for_every_required_metric() -> None:
    report = run_p03_cross_validation(_inputs())

    expected_metrics = {
        *(f"{state}.{field}" for state in report.state_names for field in ("T", "p", "h", "m")),
        "compressor_power",
        "evaporator_capacity",
        "heat_rejection",
        "cop",
        "energy_balance_error",
        "mass_balance_error",
    }
    assert set(report.metrics) == expected_metrics
    assert report.all_within_tolerance
    assert report.max_relative_error < P03_RELATIVE_TOLERANCE


def test_cross_validation_is_deterministic() -> None:
    first = run_p03_cross_validation(_inputs())
    second = run_p03_cross_validation(_inputs())

    assert first == second


def test_comparison_reports_discrepancy_without_relaxing_tolerance() -> None:
    report = run_p03_cross_validation(_inputs())
    changed_reference = replace(
        report.tespy,
        compressor_power_w=report.tespy.compressor_power_w * 1.01,
    )

    changed = compare_cycle_results(report.p02, changed_reference)

    assert not changed.all_within_tolerance
    assert not changed.metrics["compressor_power"].within_tolerance
    assert changed.metrics["compressor_power"].relative_error == pytest.approx(0.01 / 1.01)


def test_reference_rejects_out_of_scope_fluid() -> None:
    with pytest.raises(InfeasibleDesignError, match="R744"):
        solve_tespy_reference(_inputs(fluid="R134a"))


def test_comparison_rejects_nonfinite_reference_value() -> None:
    report = run_p03_cross_validation(_inputs())
    invalid_reference = replace(report.tespy, compressor_power_w=float("inf"))

    with pytest.raises(TespyCrossValidationError, match="finite"):
        compare_cycle_results(report.p02, invalid_reference)


def test_comparison_rejects_unconverged_reference_result() -> None:
    report = run_p03_cross_validation(_inputs())
    unconverged_reference = replace(report.tespy, converged=False)

    with pytest.raises(TespyCrossValidationError, match="converged"):
        compare_cycle_results(report.p02, unconverged_reference)
