"""Deterministic Agent-to-workbench adapter with explicit execution boundaries."""

from typing import Literal

from agent_hvac.app.design_workbench import WorkbenchProject
from agent_hvac.app.workbench_command import (
    CommandPlan,
    interpret_command,
    missing_solver_inputs,
    project_from_command,
    simulate_project,
)
from agent_hvac.schemas.base import ContractModel, NonEmptyStr
from agent_hvac.schemas.results import SimulationResult, SolverStatus
from agent_hvac.utils.exceptions import HVACError


class WorkbenchCommandRequest(ContractModel):
    prompt: NonEmptyStr
    execute: bool = False


class WorkbenchCommandResponse(ContractModel):
    status: Literal["rejected", "needs_input", "project_ready", "completed", "failed"]
    plan: CommandPlan | None = None
    project: WorkbenchProject | None = None
    result: SimulationResult | None = None
    missing_inputs: tuple[str, ...] = ()
    messages: tuple[str, ...] = ()


def run_workbench_command(request: WorkbenchCommandRequest) -> WorkbenchCommandResponse:
    """Interpret a supported command and run only when explicitly requested and complete."""

    try:
        plan = interpret_command(request.prompt)
    except ValueError as exc:
        return WorkbenchCommandResponse(status="rejected", messages=(str(exc),))

    if plan.refrigerant is None:
        return WorkbenchCommandResponse(
            status="needs_input",
            plan=plan,
            missing_inputs=plan.missing,
            messages=plan.notes,
        )

    try:
        project = project_from_command(plan)
    except ValueError as exc:
        return WorkbenchCommandResponse(
            status="rejected",
            plan=plan,
            messages=(str(exc),),
        )

    missing = missing_solver_inputs(project)
    if missing:
        return WorkbenchCommandResponse(
            status="needs_input",
            plan=plan,
            project=project,
            missing_inputs=missing,
            messages=plan.notes,
        )
    if not request.execute:
        return WorkbenchCommandResponse(
            status="project_ready",
            plan=plan,
            project=project,
            messages=("Calculation was not requested.",),
        )

    try:
        result = simulate_project(project)
    except (HVACError, RuntimeError, ValueError) as exc:
        return WorkbenchCommandResponse(
            status="failed",
            plan=plan,
            project=project,
            messages=(str(exc),),
        )
    return WorkbenchCommandResponse(
        status=("completed" if result.status == SolverStatus.CONVERGED else "failed"),
        plan=plan,
        project=project,
        result=result,
        messages=result.messages,
    )
