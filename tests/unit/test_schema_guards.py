import pytest
from pydantic import ValidationError

from agent_hvac.schemas.design import DecisionVariable, DesignSpecification
from agent_hvac.schemas.provenance import Parameter
from agent_hvac.schemas.results import (
    ConstraintReport,
    FinalDesignPackage,
    OptimizationResult,
    SimulationResult,
)


def test_reject_bare_numeric_parameter():
    with pytest.raises(ValidationError):
        Parameter(
            name="length", value=50, provenance={"source_type": "USER", "source_ref": "prompt"}
        )


def test_reject_missing_provenance():
    with pytest.raises(ValidationError):
        Parameter(name="refrigerant", value="R744")


@pytest.mark.parametrize(
    "lower,upper",
    [
        ({"value": 2, "unit": "m"}, {"value": 1, "unit": "m"}),
        ({"value": 1, "unit": "m"}, {"value": 2, "unit": "kg"}),
    ],
)
def test_invalid_bounds(lower, upper):
    with pytest.raises(ValidationError):
        DecisionVariable(
            name="length",
            lower=lower,
            upper=upper,
            provenance={"source_type": "USER", "source_ref": "prompt"},
        )


def test_user_constraint_cannot_change(fixture_data):
    data = fixture_data("design_spec_r744")
    data["fixed"][0]["value"]["value"] = 99
    with pytest.raises(ValidationError, match="User constraint changed"):
        DesignSpecification.model_validate(data)


def test_refrigerant_cannot_be_replaced(fixture_data):
    data = fixture_data("design_spec_r744")
    data["refrigerant"]["value"] = "R32"
    with pytest.raises(ValidationError, match="User constraint changed"):
        DesignSpecification.model_validate(data)


def test_duplicate_variable_rejected(fixture_data):
    data = fixture_data("design_spec_r744")
    data["boundary_conditions"] = data["fixed"]
    with pytest.raises(ValidationError, match="multiple categories"):
        DesignSpecification.model_validate(data)


def test_unknown_field_rejected(fixture_data):
    data = fixture_data("simulation_result_r744")
    data["pretend_success"] = True
    with pytest.raises(ValidationError):
        SimulationResult.model_validate(data)


def test_incomplete_success_rejected():
    with pytest.raises(ValidationError):
        SimulationResult(design_id="bad", status="converged", is_mock=False)


@pytest.mark.parametrize(
    "status",
    ["unconverged", "infeasible", "invalid-property-state", "component-envelope-violation"],
)
def test_failure_requires_explanation(status):
    with pytest.raises(ValidationError):
        SimulationResult(design_id="bad", status=status, is_mock=False)
    result = SimulationResult(
        design_id="bad", status=status, is_mock=False, messages=["explicit failure"]
    )
    assert result.status == status


def test_failed_simulation_cannot_be_optimum(fixture_data):
    data = fixture_data("optimization_result")
    data["ranked_designs"][0]["simulation"]["status"] = "unconverged"
    with pytest.raises(ValidationError, match="converged feasible"):
        OptimizationResult.model_validate(data)


def test_hard_constraint_failure_cannot_be_feasible(fixture_data):
    data = fixture_data("constraint_report")
    data["checks"][0]["passed"] = False
    with pytest.raises(ValidationError):
        ConstraintReport.model_validate(data)


def test_mock_cannot_be_released(fixture_data):
    data = fixture_data("final_design_package")
    data["release_ready"] = True
    data["approval_status"] = "approved"
    data["selected"]["design"]["requirements"]["missing"] = []
    with pytest.raises(ValidationError):
        FinalDesignPackage.model_validate(data)


def test_mixed_real_and_mock_rejected(fixture_data):
    data = fixture_data("final_design_package")
    data["metadata"]["is_mock"] = False
    with pytest.raises(ValidationError, match="mock flag"):
        FinalDesignPackage.model_validate(data)


def test_result_id_mismatch_rejected(fixture_data):
    data = fixture_data("optimization_result")
    data["ranked_designs"][0]["simulation"]["design_id"] = "another-run"
    with pytest.raises(ValidationError, match="identifiers"):
        OptimizationResult.model_validate(data)


def test_user_constraint_cannot_disappear(fixture_data):
    data = fixture_data("design_spec_r744")
    data["fixed"] = []
    with pytest.raises(ValidationError, match="must remain"):
        DesignSpecification.model_validate(data)


def test_unresolved_essential_input_blocks_release(fixture_data):
    data = fixture_data("final_design_package")
    data["release_ready"] = True
    with pytest.raises(ValidationError, match="Unresolved essential"):
        FinalDesignPackage.model_validate(data)


def test_pressure_drop_rejects_length(fixture_data):
    data = fixture_data("simulation_result_r744")
    data["pressure_drops"] = {"suction": {"value": 1, "unit": "m"}}
    with pytest.raises(ValidationError):
        SimulationResult.model_validate(data)


def test_zero_pressure_drop_is_allowed(fixture_data):
    data = fixture_data("simulation_result_r744")
    data["pressure_drops"] = {"suction": {"value": 0, "unit": "Pa"}}
    assert SimulationResult.model_validate(data).pressure_drops["suction"].value == 0
