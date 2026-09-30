"""Deterministic mock search for P09 contract and failure-path validation.

This module deliberately contains no HVAC physics.  It resolves a finite synthetic
grid, invokes injected mock services, and ranks only converged feasible artifacts.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import random
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from agent_hvac.physics.state import ThermoState
from agent_hvac.schemas.components import ProductRecord
from agent_hvac.schemas.design import DesignProblem, DesignSpecification
from agent_hvac.schemas.provenance import Parameter, Provenance, SourceType
from agent_hvac.schemas.results import (
    ConstraintCheck,
    ConstraintReport,
    OptimizationResult,
    RankedDesign,
    SimulationResult,
    SolverStatus,
)
from agent_hvac.utils.units import (
    Density,
    MassFlow,
    Power,
    Pressure,
    Quantity,
    SpecificEnthalpy,
    Temperature,
)


class SyntheticSolver(Protocol):
    def simulate(self, design: DesignSpecification) -> SimulationResult: ...


class SyntheticConstraintEvaluator(Protocol):
    def evaluate(
        self, design: DesignSpecification, result: SimulationResult
    ) -> ConstraintReport: ...


class SyntheticObjectiveEvaluator(Protocol):
    metric: str

    def evaluate(self, design: DesignSpecification, result: SimulationResult) -> Quantity: ...


@dataclass(frozen=True)
class SyntheticSearchSettings:
    grid_points: int = 5
    max_candidates: int = 10_000
    version: str = "p09-synthetic-grid-v1"

    def __post_init__(self) -> None:
        if self.grid_points < 2:
            raise ValueError("grid_points must be at least 2")
        if self.max_candidates < 1:
            raise ValueError("max_candidates must be positive")
        if not self.version.strip():
            raise ValueError("version must be non-empty")


@dataclass(frozen=True)
class QuadraticObjectiveStub:
    """Synthetic scalar objective with a known target in normalized SI values."""

    targets: Mapping[str, float]
    metric: str = "synthetic_score"
    product_offsets: Mapping[str, float] = field(default_factory=dict)

    def evaluate(self, design: DesignSpecification, result: SimulationResult) -> Quantity:
        del result
        values = _quantity_parameters(design)
        missing = sorted(set(self.targets) - set(values))
        if missing:
            raise ValueError(f"Objective inputs missing: {', '.join(missing)}")
        score = sum((values[name].value - target) ** 2 for name, target in self.targets.items())
        score += sum(
            self.product_offsets.get(product.product_id, 0.0)
            for product in design.selected_products
        )
        return Quantity(value=score, unit="dimensionless")


@dataclass(frozen=True)
class DeterministicSolverStub:
    """Mock converged result, with configured decision values producing explicit failures."""

    fail_at: Mapping[str, tuple[float, ...]] = field(default_factory=dict)
    tolerance: float = 1e-12

    def simulate(self, design: DesignSpecification) -> SimulationResult:
        values = _quantity_parameters(design)
        failures = [
            name
            for name, rejected in self.fail_at.items()
            if name in values
            and any(
                abs(values[name].value - rejected_value) <= self.tolerance
                for rejected_value in rejected
            )
        ]
        if failures:
            return SimulationResult(
                design_id=design.design_id,
                status=SolverStatus.UNCONVERGED,
                is_mock=True,
                messages=(f"MOCK solver failure at: {', '.join(sorted(failures))}",),
            )
        return SimulationResult(
            design_id=design.design_id,
            status=SolverStatus.CONVERGED,
            is_mock=True,
            state_points={
                "synthetic": ThermoState(
                    fluid=str(design.refrigerant.value),
                    pressure=Pressure(value=1_000_000.0, unit="Pa"),
                    temperature=Temperature(value=300.0, unit="K"),
                    enthalpy=SpecificEnthalpy(value=100_000.0, unit="J/kg"),
                    density=Density(value=1.0, unit="kg/m^3"),
                    phase="mock-synthetic",
                )
            },
            mass_flow=MassFlow(value=1.0, unit="kg/s"),
            compressor_power=Power(value=1.0, unit="W"),
            evaporator_capacity=Power(value=1.0, unit="W"),
            heat_rejection=Power(value=1.0, unit="W"),
            cop=1.0,
            energy_balance_error=0.0,
            mass_balance_error=0.0,
            messages=("MOCK ONLY: deterministic P09 solver stub; no HVAC physics",),
        )


@dataclass(frozen=True)
class UpperBoundConstraintStub:
    """Synthetic hard upper bounds in the already-normalized units of each variable."""

    upper_bounds: Mapping[str, float] = field(default_factory=dict)

    def evaluate(self, design: DesignSpecification, result: SimulationResult) -> ConstraintReport:
        del result
        values = _quantity_parameters(design)
        checks: list[ConstraintCheck] = []
        for name, limit in sorted(self.upper_bounds.items()):
            if name not in values:
                raise ValueError(f"Constraint input missing: {name}")
            margin = limit - values[name].value
            checks.append(
                ConstraintCheck(
                    rule_id=f"P09_MOCK_MAX_{name}",
                    passed=margin >= 0.0,
                    hard=True,
                    message=f"MOCK ONLY: {name} <= {limit}",
                    margin=Quantity(value=margin, unit=values[name].unit),
                )
            )
        if not checks:
            checks.append(
                ConstraintCheck(
                    rule_id="P09_MOCK_FEASIBLE",
                    passed=True,
                    hard=True,
                    message="MOCK ONLY: no synthetic rejection configured",
                )
            )
        return ConstraintReport(
            design_id=design.design_id,
            checks=tuple(checks),
            feasible=all(check.passed for check in checks if check.hard),
            is_mock=True,
        )


class SyntheticGridOptimizer:
    """Exhaustive finite mock search implementing the frozen optimizer Protocol."""

    def __init__(
        self,
        solver: SyntheticSolver,
        constraints: SyntheticConstraintEvaluator,
        objective: SyntheticObjectiveEvaluator,
        settings: SyntheticSearchSettings | None = None,
    ) -> None:
        self._solver = solver
        self._constraints = constraints
        self._objective = objective
        self._settings = settings or SyntheticSearchSettings()

    def optimize(self, problem: DesignProblem) -> OptimizationResult:
        validation_error = self._validate_problem(problem)
        if validation_error:
            return self._failed(validation_error)

        seed = problem.random_seed if problem.random_seed is not None else 0
        candidate_count = self._candidate_count(problem)
        if candidate_count > self._settings.max_candidates:
            return self._failed(
                f"candidate count {candidate_count} exceeds limit {self._settings.max_candidates}"
            )

        assignments = self._assignments(problem)
        product_combinations = self._product_combinations(problem)
        candidates = list(itertools.product(assignments, product_combinations))
        random.Random(seed).shuffle(candidates)
        ranked: list[RankedDesign] = []
        rejected: list[tuple[str, str, str]] = []
        objective_unit: str | None = None

        for assignment, products in candidates:
            design = self._candidate_design(problem.baseline, assignment, products)
            try:
                simulation = self._solver.simulate(design)
                artifact_error = _simulation_error(design, simulation)
                if artifact_error:
                    rejected.append((design.design_id, "solver-failure", artifact_error))
                    continue
                constraint_report = self._constraints.evaluate(design, simulation)
                artifact_error = _constraint_error(design, constraint_report)
                if artifact_error:
                    rejected.append((design.design_id, "execution-error", artifact_error))
                    continue
                if not constraint_report.feasible:
                    failed_rules = sorted(
                        check.rule_id
                        for check in constraint_report.checks
                        if check.hard and not check.passed
                    )
                    rejected.append(
                        (
                            design.design_id,
                            "infeasible",
                            f"hard constraints: {', '.join(failed_rules)}",
                        )
                    )
                    continue
                objective_value = self._objective.evaluate(design, simulation)
                if objective_unit is None:
                    objective_unit = objective_value.unit
                elif objective_value.unit != objective_unit:
                    rejected.append(
                        (
                            design.design_id,
                            "execution-error",
                            f"objective unit {objective_value.unit} differs from {objective_unit}",
                        )
                    )
                    continue
                ranked.append(
                    RankedDesign(
                        design=design,
                        simulation=simulation,
                        constraints=constraint_report,
                        objective_value=objective_value,
                    )
                )
            except Exception as exc:  # Candidate-level service failures must not abort the search.
                rejected.append((design.design_id, "execution-error", str(exc)))

        direction = problem.baseline.objectives[0].direction
        ranked.sort(key=lambda item: _ranking_key(item, direction))
        messages = self._messages(seed, candidate_count, rejected)
        if ranked:
            return OptimizationResult(
                status="completed",
                ranked_designs=tuple(ranked),
                messages=messages,
                is_mock=True,
            )
        failure_kinds = {kind for _, kind, _ in rejected}
        status = (
            "failed"
            if failure_kinds and failure_kinds <= {"solver-failure", "execution-error"}
            else "infeasible"
        )
        return OptimizationResult(status=status, messages=messages, is_mock=True)

    def _validate_problem(self, problem: DesignProblem) -> str | None:
        if not problem.baseline.is_mock:
            return "P09 synthetic search requires a mock baseline"
        if any(not product.is_mock for product in problem.candidate_products):
            return "P09 synthetic search requires mock candidate products"
        if len(problem.baseline.objectives) != 1:
            return "P09 supports exactly one scalar objective"
        if problem.baseline.objectives[0].metric != self._objective.metric:
            return "objective metric does not match the configured synthetic evaluator"
        product_id_counts = Counter(product.product_id for product in problem.candidate_products)
        duplicate_product_ids = sorted(
            product_id for product_id, count in product_id_counts.items() if count > 1
        )
        if duplicate_product_ids:
            return f"candidate product_id must be unique: {', '.join(duplicate_product_ids)}"
        selected_types = {product.component_type for product in problem.baseline.selected_products}
        candidate_types = {product.component_type for product in problem.candidate_products}
        if selected_types & candidate_types:
            return "candidate product type overlaps an already selected baseline product"
        return None

    def _candidate_count(self, problem: DesignProblem) -> int:
        """Count the Cartesian search space without materializing any candidates."""

        assignment_count = 1
        for _ in problem.baseline.decision_variables:
            assignment_count *= self._settings.grid_points
        product_counts: defaultdict[str, int] = defaultdict(int)
        for product in problem.candidate_products:
            product_counts[str(product.component_type)] += 1
        product_combination_count = 1
        for count in product_counts.values():
            product_combination_count *= count
        return assignment_count * product_combination_count

    def _assignments(self, problem: DesignProblem) -> tuple[dict[str, Quantity], ...]:
        variables = problem.baseline.decision_variables
        if not variables:
            return ({},)
        axes: list[tuple[Quantity, ...]] = []
        for variable in variables:
            step = (variable.upper.value - variable.lower.value) / (self._settings.grid_points - 1)
            axes.append(
                tuple(
                    Quantity(
                        value=variable.lower.value + index * step,
                        unit=variable.lower.unit,
                    )
                    for index in range(self._settings.grid_points)
                )
            )
        return tuple(
            {variable.name: value for variable, value in zip(variables, values, strict=True)}
            for values in itertools.product(*axes)
        )

    @staticmethod
    def _product_combinations(problem: DesignProblem) -> tuple[tuple[ProductRecord, ...], ...]:
        if not problem.candidate_products:
            return ((),)
        grouped: defaultdict[str, list[ProductRecord]] = defaultdict(list)
        for product in problem.candidate_products:
            grouped[str(product.component_type)].append(product)
        axes = [
            tuple(sorted(grouped[key], key=lambda item: item.product_id)) for key in sorted(grouped)
        ]
        return tuple(itertools.product(*axes))

    def _candidate_design(
        self,
        baseline: DesignSpecification,
        assignment: Mapping[str, Quantity],
        products: tuple[ProductRecord, ...],
    ) -> DesignSpecification:
        optimized = tuple(
            Parameter(
                name=name,
                value=value,
                provenance=Provenance(
                    source_type=SourceType.OPTIMIZED,
                    source_ref=self._settings.version,
                    confidence=1.0,
                    note="MOCK ONLY: finite synthetic grid value",
                ),
            )
            for name, value in assignment.items()
        )
        signature = {
            "variables": {name: value.value for name, value in assignment.items()},
            "products": [product.product_id for product in products],
        }
        digest = hashlib.sha256(
            json.dumps(signature, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
        data = baseline.model_dump()
        data.update(
            design_id=f"{baseline.design_id}-p09-{digest}",
            fixed=baseline.fixed + optimized,
            decision_variables=(),
            selected_products=baseline.selected_products + products,
        )
        return DesignSpecification.model_validate(data)

    def _messages(
        self, seed: int, candidate_count: int, rejected: list[tuple[str, str, str]]
    ) -> tuple[str, ...]:
        summary = (
            f"MOCK ONLY: {self._settings.version}; seed={seed}; "
            f"grid_points={self._settings.grid_points}; evaluated={candidate_count}; "
            f"rejected={len(rejected)}; no HVAC physics or product validation"
        )
        rejection_messages = tuple(
            f"REJECTED {design_id} [{kind}]: {reason}"
            for design_id, kind, reason in sorted(rejected)
        )
        return (summary,) + rejection_messages

    @staticmethod
    def _failed(message: str) -> OptimizationResult:
        return OptimizationResult(
            status="failed",
            messages=(f"MOCK ONLY: P09 synthetic search failed: {message}",),
            is_mock=True,
        )


def _quantity_parameters(design: DesignSpecification) -> dict[str, Quantity]:
    return {
        parameter.name: parameter.value
        for parameter in design.fixed + design.boundary_conditions
        if isinstance(parameter.value, Quantity)
    }


def _simulation_error(design: DesignSpecification, result: SimulationResult) -> str | None:
    if result.design_id != design.design_id:
        return "solver returned a different design_id"
    if not result.is_mock:
        return "solver returned a non-mock artifact"
    if result.status != SolverStatus.CONVERGED:
        detail = "; ".join(result.messages) if result.messages else result.status.value
        return f"{result.status.value}: {detail}"
    return None


def _constraint_error(design: DesignSpecification, report: ConstraintReport) -> str | None:
    if report.design_id != design.design_id:
        return "constraint evaluator returned a different design_id"
    if not report.is_mock:
        return "constraint evaluator returned a non-mock artifact"
    return None


def _ranking_key(item: RankedDesign, direction: str) -> tuple[float, str]:
    value = item.objective_value.value
    return ((value if direction == "minimize" else -value), item.design.design_id)
