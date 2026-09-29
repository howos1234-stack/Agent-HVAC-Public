import pytest

from agent_hvac.schemas.components import ProductRecord
from agent_hvac.schemas.design import DesignSpecification
from agent_hvac.schemas.results import (
    ConstraintReport,
    FinalDesignPackage,
    OptimizationResult,
    SimulationResult,
)


@pytest.mark.parametrize(
    "name,schema",
    [
        ("compressor_product", ProductRecord),
        ("compressor_product_v020", ProductRecord),
        ("evaporator_product", ProductRecord),
        ("design_spec_r744", DesignSpecification),
        ("simulation_result_r744", SimulationResult),
        ("constraint_report", ConstraintReport),
        ("optimization_result", OptimizationResult),
        ("final_design_package", FinalDesignPackage),
    ],
)
def test_fixture_roundtrip_uses_production_schema(name, schema, fixture_data):
    value = schema.model_validate(fixture_data(name))
    assert schema.model_validate_json(value.model_dump_json()) == value
    assert schema.model_json_schema()["type"] == "object"
    if isinstance(value, FinalDesignPackage):
        assert value.metadata.is_mock and not value.release_ready
    else:
        assert value.is_mock
    if isinstance(value, SimulationResult):
        assert all(state.entropy is None for state in value.state_points.values())
