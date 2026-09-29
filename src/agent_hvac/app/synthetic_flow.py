"""Reproducible P09 mock scenarios for P12/P13 presentation validation."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import cast

from agent_hvac.optimization.synthetic_search import (
    DeterministicSolverStub,
    QuadraticObjectiveStub,
    SyntheticGridOptimizer,
    SyntheticObjectiveEvaluator,
    SyntheticSearchSettings,
    UpperBoundConstraintStub,
)
from agent_hvac.reporting.optimization_reports import generate_optimization_report_bundle
from agent_hvac.schemas.design import DesignProblem
from agent_hvac.schemas.results import OptimizationResult


class SyntheticScenario(StrEnum):
    NORMAL = "normal"
    INFEASIBLE = "infeasible"
    PARTIAL_SOLVER_FAILURE = "partial-solver-failure"
    ALL_SOLVER_FAILURE = "all-solver-failure"
    CANDIDATE_LIMIT = "candidate-limit"


def run_synthetic_scenario(
    problem: DesignProblem, scenario: SyntheticScenario
) -> OptimizationResult:
    """Execute one documented mock scenario without altering the P09 implementation."""
    fail_at: Mapping[str, tuple[float, ...]] = {}
    upper_bounds: Mapping[str, float] = {}
    settings = SyntheticSearchSettings(grid_points=5)
    if scenario == SyntheticScenario.INFEASIBLE:
        upper_bounds = {"synthetic_x": -2.0}
    elif scenario == SyntheticScenario.PARTIAL_SOLVER_FAILURE:
        fail_at = {"synthetic_x": (0.0,)}
    elif scenario == SyntheticScenario.ALL_SOLVER_FAILURE:
        fail_at = {"synthetic_x": (-1.0, -0.5, 0.0, 0.5, 1.0)}
    elif scenario == SyntheticScenario.CANDIDATE_LIMIT:
        settings = SyntheticSearchSettings(grid_points=5, max_candidates=4)
    optimizer = SyntheticGridOptimizer(
        solver=DeterministicSolverStub(fail_at=fail_at),
        constraints=UpperBoundConstraintStub(upper_bounds=upper_bounds),
        objective=cast(
            SyntheticObjectiveEvaluator,
            QuadraticObjectiveStub(targets={"synthetic_x": 0.0}),
        ),
        settings=settings,
    )
    return optimizer.optimize(problem)


def run_all_scenarios(problem: DesignProblem) -> dict[SyntheticScenario, OptimizationResult]:
    return {scenario: run_synthetic_scenario(problem, scenario) for scenario in SyntheticScenario}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate P09 mock GUI/report examples")
    parser.add_argument("problem", type=Path, help="DesignProblem JSON")
    parser.add_argument("output_dir", type=Path, help="JSON/HTML output directory")
    args = parser.parse_args(argv)
    problem = DesignProblem.model_validate_json(args.problem.read_bytes())
    for scenario, result in run_all_scenarios(problem).items():
        artifacts = generate_optimization_report_bundle(result, args.output_dir, scenario.value)
        for artifact in artifacts:
            print(f"{scenario.value} {artifact.media_type}: {artifact.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
