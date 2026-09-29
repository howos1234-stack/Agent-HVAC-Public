import pytest
from pydantic import ValidationError

from agent_hvac.schemas.design import DesignSpecification
from agent_hvac.schemas.requirements import UserRequirements
from agent_hvac.schemas.results import SimulationResult
from agent_hvac.utils.units import PressureDifference


@pytest.mark.parametrize("unit", ["Pa", "kPa", "bar"])
def test_negative_pressure_loss_rejected_after_conversion(unit):
    with pytest.raises(ValidationError, match="nonnegative"):
        PressureDifference(value=-1, unit=unit)


@pytest.mark.parametrize("value", [0, 1])
def test_nonnegative_pressure_loss_roundtrip(value):
    q = PressureDifference(value=value, unit="kPa")
    assert q.value == value * 1000
    assert PressureDifference.model_validate_json(q.model_dump_json()) == q


def test_nested_negative_pressure_loss_rejected(fixture_data):
    data = fixture_data("simulation_result_r744")
    data["pressure_drops"] = {"pipe": {"value": -1, "unit": "Pa"}}
    with pytest.raises(ValidationError, match="nonnegative"):
        SimulationResult.model_validate(data)


@pytest.mark.parametrize("classification", ["essential", "defaultable", "free_variable"])
def test_missing_name_unique_even_for_same_classification(classification):
    with pytest.raises(ValidationError, match="Duplicate missing"):
        UserRequirements.model_validate(
            {
                "raw_prompt": "review",
                "hitl_mode": "AUTO",
                "missing": [
                    {"name": "capacity", "classification": c, "reason": "unspecified"}
                    for c in ("essential", classification)
                ],
            }
        )


def test_different_missing_names_allowed():
    value = UserRequirements.model_validate(
        {
            "raw_prompt": "review",
            "hitl_mode": "AUTO",
            "missing": [
                {"name": name, "classification": "essential", "reason": "unspecified"}
                for name in ("capacity", "source_temperature")
            ],
        }
    )
    assert len(value.missing) == 2


@pytest.mark.parametrize("design_mock", [True, False])
def test_product_mock_mismatch_rejected_in_both_directions(fixture_data, design_mock):
    data = fixture_data("design_spec_r744")
    data["is_mock"] = design_mock
    for p in data["selected_products"]:
        p["is_mock"] = design_mock
    data["selected_products"][0]["is_mock"] = not design_mock
    with pytest.raises(ValidationError, match="matching mock flags"):
        DesignSpecification.model_validate(data)


@pytest.mark.parametrize("design_mock", [True, False])
def test_matching_product_flags_allowed(fixture_data, design_mock):
    data = fixture_data("design_spec_r744")
    data["is_mock"] = design_mock
    for p in data["selected_products"]:
        p["is_mock"] = design_mock
    # Synthetic payload exercising flags only, not asserting a real product/design exists.
    value = DesignSpecification.model_validate(data)
    assert value.is_mock == design_mock


@pytest.mark.parametrize(
    "field,value", [("name", "not_topology"), ("value", {"value": 1, "unit": "m"})]
)
def test_topology_requires_named_string_identifier(fixture_data, field, value):
    data = fixture_data("design_spec_r744")
    data["topology"][field] = value
    with pytest.raises(ValidationError, match="Topology"):
        DesignSpecification.model_validate(data)
