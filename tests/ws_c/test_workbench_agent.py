"""WS-C tests for the deterministic Agent-to-workbench boundary."""

from unittest.mock import patch

from agent_hvac.agents.workbench import (
    WorkbenchCommandRequest,
    run_workbench_command,
)
from agent_hvac.utils.exceptions import InvalidPropertyStateError

COMPLETE_COMMAND = (
    "R134a 기본 냉동사이클을 구성하고 압축기에 등엔트로피 효율 0.75 모델을 적용해줘. "
    "증발압력 3 bar(a), 고압 12 bar(a), 흡입온도 10°C, 응축기 출구온도 35°C, "
    "냉매 질량유량 0.05 kg/s."
)


def test_incomplete_command_preserves_missing_inputs_without_execution() -> None:
    with patch("agent_hvac.agents.workbench.simulate_project") as simulate:
        response = run_workbench_command(
            WorkbenchCommandRequest(
                prompt="R134a 냉동사이클을 구성하고 압축기에 등엔트로피 효율 모델을 적용해줘",
                execute=True,
            )
        )

    assert response.status == "needs_input"
    assert response.project is not None
    assert response.result is None
    assert set(response.missing_inputs) == {
        "evaporator_pressure",
        "high_side_pressure",
        "compressor_inlet_temperature",
        "heat_rejection_outlet_temperature",
        "refrigerant_mass_flow",
        "compressor_isentropic_efficiency",
    }
    simulate.assert_not_called()


def test_complete_command_builds_project_without_implicit_execution() -> None:
    with patch("agent_hvac.agents.workbench.simulate_project") as simulate:
        response = run_workbench_command(
            WorkbenchCommandRequest(prompt=COMPLETE_COMMAND, execute=False)
        )

    assert response.status == "project_ready"
    assert response.project is not None
    assert response.project.refrigerant == "R134a"
    assert response.result is None
    assert response.missing_inputs == ()
    simulate.assert_not_called()


def test_explicit_complete_command_runs_existing_baseline_solver() -> None:
    response = run_workbench_command(WorkbenchCommandRequest(prompt=COMPLETE_COMMAND, execute=True))

    assert response.status == "completed"
    assert response.project is not None
    assert response.result is not None
    assert response.result.design_id.startswith("WORKBENCH-R134a")
    assert not response.result.is_mock
    assert response.result.status.value == "converged"


def test_ambiguous_refrigerant_is_needs_input_and_gauge_pressure_is_rejected() -> None:
    ambiguous = run_workbench_command(
        WorkbenchCommandRequest(prompt="R134a와 R744 냉동사이클을 구성해줘", execute=True)
    )
    rejected = run_workbench_command(
        WorkbenchCommandRequest(prompt="R744 저압 30 bar(g)", execute=True)
    )

    assert ambiguous.status == "needs_input"
    assert "refrigerant" in ambiguous.missing_inputs
    assert "refrigerant_mass_flow" in ambiguous.missing_inputs
    assert rejected.status == "rejected"
    assert "게이지압" in rejected.messages[0]


def test_solver_service_failure_is_returned_as_failed_without_a_result() -> None:
    with patch(
        "agent_hvac.agents.workbench.simulate_project",
        side_effect=InvalidPropertyStateError("synthetic property failure"),
    ):
        response = run_workbench_command(
            WorkbenchCommandRequest(prompt=COMPLETE_COMMAND, execute=True)
        )

    assert response.status == "failed"
    assert response.project is not None
    assert response.result is None
    assert response.messages == ("synthetic property failure",)
