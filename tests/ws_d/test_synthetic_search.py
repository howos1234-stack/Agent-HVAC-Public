"""P09 tests prove search behavior only; all services and data are synthetic."""

from copy import deepcopy
from unittest.mock import Mock, patch

import pytest

from agent_hvac.optimization.optimizer import DesignOptimizer
from agent_hvac.optimization.synthetic_search import (
    DeterministicSolverStub,
    QuadraticObjectiveStub,
    SyntheticGridOptimizer,
    SyntheticSearchSettings,
    UpperBoundConstraintStub,
)
from agent_hvac.schemas.components import ProductRecord
from agent_hvac.schemas.design import DesignProblem, DesignSpecification


def _problem(fixture_data, *, points: int = 5) -> tuple[DesignProblem, SyntheticGridOptimizer]:
    data = deepcopy(fixture_data("design_spec_r744"))
    data["design_id"] = "P09-MOCK"
    data["selected_products"] = []
    data["decision_variables"] = [
        {
            "name": "synthetic_x",
            "lower": {"value": -1.0, "unit": "dimensionless"},
            "upper": {"value": 1.0, "unit": "dimensionless"},
            "provenance": {
                "source_type": "AGENT_ASSUMPTION",
                "source_ref": "P09 synthetic bounds; NOT PHYSICS",
            },
        }
    ]
    data["objectives"] = [
        {
            "metric": "synthetic_score",
            "direction": "minimize",
            "provenance": {
                "source_type": "AGENT_ASSUMPTION",
                "source_ref": "P09 quadratic objective; NOT PHYSICS",
            },
        }
    ]
    design = DesignSpecification.model_validate(data)
    optimizer = SyntheticGridOptimizer(
        solver=DeterministicSolverStub(),
        constraints=UpperBoundConstraintStub(),
        objective=QuadraticObjectiveStub(targets={"synthetic_x": 0.0}),
        settings=SyntheticSearchSettings(grid_points=points),
    )
    return DesignProblem(baseline=design, random_seed=73), optimizer


def _fixed_value(design: DesignSpecification, name: str) -> float:
    parameter = next(parameter for parameter in design.fixed if parameter.name == name)
    assert not isinstance(parameter.value, str)
    return parameter.value.value


def test_known_optimum_and_fixed_user_value_are_preserved(fixture_data):
    problem, optimizer = _problem(fixture_data)

    result = optimizer.optimize(problem)

    assert result.status == "completed"
    assert len(result.ranked_designs) == 5
    selected = result.ranked_designs[0]
    assert selected.objective_value.value == pytest.approx(0.0, abs=0.0)
    assert _fixed_value(selected.design, "synthetic_x") == pytest.approx(0.0, abs=0.0)
    assert _fixed_value(selected.design, "specified_pipe_length") == pytest.approx(0.5, abs=0.0)
    assert not selected.design.decision_variables
    assert selected.design.is_mock
    assert "MOCK ONLY" in result.messages[0]
    assert "seed=73" in result.messages[0]


def test_impossible_hard_constraint_returns_no_ranked_designs(fixture_data):
    problem, _ = _problem(fixture_data)
    optimizer = SyntheticGridOptimizer(
        solver=DeterministicSolverStub(),
        constraints=UpperBoundConstraintStub(upper_bounds={"synthetic_x": -2.0}),
        objective=QuadraticObjectiveStub(targets={"synthetic_x": 0.0}),
    )

    result = optimizer.optimize(problem)

    assert result.status == "infeasible"
    assert result.ranked_designs == ()
    assert sum("[infeasible]" in message for message in result.messages) == 5


def test_solver_failure_is_excluded_from_ranking(fixture_data):
    problem, _ = _problem(fixture_data)
    optimizer = SyntheticGridOptimizer(
        solver=DeterministicSolverStub(fail_at={"synthetic_x": (0.0,)}),
        constraints=UpperBoundConstraintStub(),
        objective=QuadraticObjectiveStub(targets={"synthetic_x": 0.0}),
    )

    result = optimizer.optimize(problem)

    assert result.status == "completed"
    assert len(result.ranked_designs) == 4
    assert result.ranked_designs[0].objective_value.value == pytest.approx(0.25)
    assert all(_fixed_value(item.design, "synthetic_x") != 0.0 for item in result.ranked_designs)
    assert any("[solver-failure]" in message for message in result.messages)


def test_all_solver_failures_return_failed(fixture_data):
    problem, _ = _problem(fixture_data)
    optimizer = SyntheticGridOptimizer(
        solver=DeterministicSolverStub(fail_at={"synthetic_x": (-1.0, -0.5, 0.0, 0.5, 1.0)}),
        constraints=UpperBoundConstraintStub(),
        objective=QuadraticObjectiveStub(targets={"synthetic_x": 0.0}),
    )

    result = optimizer.optimize(problem)

    assert result.status == "failed"
    assert result.ranked_designs == ()
    assert sum("[solver-failure]" in message for message in result.messages) == 5


def test_same_seed_replays_identical_serialized_result(fixture_data):
    problem, optimizer = _problem(fixture_data)

    first = optimizer.optimize(problem)
    second = optimizer.optimize(problem)

    assert first.model_dump_json() == second.model_dump_json()


def test_candidate_limit_fails_before_generation_or_solver_call(fixture_data):
    problem, _ = _problem(fixture_data)
    solver = Mock(spec=DeterministicSolverStub)
    optimizer = SyntheticGridOptimizer(
        solver=solver,
        constraints=UpperBoundConstraintStub(),
        objective=QuadraticObjectiveStub(targets={"synthetic_x": 0.0}),
        settings=SyntheticSearchSettings(grid_points=5, max_candidates=4),
    )

    with (
        patch.object(
            SyntheticGridOptimizer,
            "_assignments",
            side_effect=AssertionError("assignment generation must not run"),
        ) as assignments,
        patch.object(
            SyntheticGridOptimizer,
            "_product_combinations",
            side_effect=AssertionError("product combination generation must not run"),
        ) as product_combinations,
    ):
        result = optimizer.optimize(problem)

    assert result.status == "failed"
    assert result.ranked_designs == ()
    assert "candidate count 5 exceeds limit 4" in result.messages[0]
    assignments.assert_not_called()
    product_combinations.assert_not_called()
    solver.simulate.assert_not_called()


def test_component_type_product_combinations_are_complete_and_ranked(fixture_data):
    problem, _ = _problem(fixture_data)
    design = problem.baseline.model_copy(update={"decision_variables": ()})
    products = [
        ProductRecord.model_validate(item)
        for item in fixture_data("design_spec_r744")["selected_products"]
    ]
    compressor_a, evaporator_a = products
    compressor_b = ProductRecord.model_validate(
        {
            **compressor_a.model_dump(),
            "product_id": "MOCK-compressor-b",
            "model": "MOCK-compressor-b",
        }
    )
    evaporator_b = ProductRecord.model_validate(
        {
            **evaporator_a.model_dump(),
            "product_id": "MOCK-evaporator-b",
            "model": "MOCK-evaporator-b",
        }
    )
    offsets = {
        compressor_a.product_id: 2.0,
        compressor_b.product_id: 0.0,
        evaporator_a.product_id: 1.0,
        evaporator_b.product_id: 0.0,
    }
    optimizer = SyntheticGridOptimizer(
        solver=DeterministicSolverStub(),
        constraints=UpperBoundConstraintStub(),
        objective=QuadraticObjectiveStub(targets={}, product_offsets=offsets),
    )

    result = optimizer.optimize(
        DesignProblem(
            baseline=design,
            candidate_products=(compressor_a, compressor_b, evaporator_a, evaporator_b),
            random_seed=9,
        )
    )

    assert result.status == "completed"
    assert len(result.ranked_designs) == 4
    assert {
        product.product_id for product in result.ranked_designs[0].design.selected_products
    } == {
        "MOCK-compressor-b",
        "MOCK-evaporator-b",
    }
    assert [item.objective_value.value for item in result.ranked_designs] == [0.0, 1.0, 2.0, 3.0]


def test_frozen_optimizer_protocol_is_satisfied(fixture_data):
    problem, implementation = _problem(fixture_data)
    optimizer: DesignOptimizer = implementation

    assert optimizer.optimize(problem).status == "completed"


def test_non_mock_and_multiple_objectives_fail_without_evaluation(fixture_data):
    problem, optimizer = _problem(fixture_data)
    real_baseline = DesignSpecification.model_validate(
        {**problem.baseline.model_dump(), "is_mock": False}
    )
    non_mock = optimizer.optimize(DesignProblem(baseline=real_baseline, random_seed=1))

    objective = problem.baseline.objectives[0].model_dump()
    multi_baseline = DesignSpecification.model_validate(
        {**problem.baseline.model_dump(), "objectives": [objective, objective]}
    )
    multiple = optimizer.optimize(DesignProblem(baseline=multi_baseline, random_seed=1))

    assert non_mock.status == "failed"
    assert "requires a mock baseline" in non_mock.messages[0]
    assert multiple.status == "failed"
    assert "exactly one scalar objective" in multiple.messages[0]
