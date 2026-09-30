"""P06 HX rated-point connection to the unchanged P05 constant-UA model."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_hvac.components.candidate_trials import (
    ComponentCandidateTrial,
    HeatExchangerTrialInput,
    evaluate_synthetic_component_trials,
)
from agent_hvac.components.heat_exchanger_1d import (
    HeatExchanger1DInput,
    HeatExchanger1DResult,
    SpecificHeatCapacity,
    evaluate_heat_exchanger_1d,
)
from agent_hvac.components.heat_exchanger_rated_point import (
    HeatExchangerBoundaryInput,
    HeatExchangerRatedPointError,
    HeatExchangerRatedPointSelection,
    HeatExchangerRatedPointView,
    evaluate_heat_exchanger_rated_point,
    select_heat_exchanger_rated_point,
)
from agent_hvac.properties.coolprop_backend import CoolPropBackend
from agent_hvac.schemas.components import (
    AutomaticSelectionStatus,
    DataUseStatus,
    OperatingMode,
    ProductRecord,
    ProductTopology,
    UseRestrictionReason,
)
from agent_hvac.utils.exceptions import ConvergenceError, InfeasibleDesignError
from agent_hvac.utils.units import MassFlow, Pressure, Quantity, Temperature

FIXTURE = Path(__file__).parents[1] / "fixtures" / "hx_product_v020.json"


@pytest.fixture
def product() -> ProductRecord:
    return ProductRecord.model_validate_json(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def conditions() -> dict[str, Quantity]:
    return {
        "inlet_pressure": Quantity(value=90.0, unit="bar"),
        "inlet_temperature": Quantity(value=375.0, unit="K"),
        "mass_flow": Quantity(value=360.0, unit="kg/h"),
    }


def _selection(
    product: ProductRecord,
    conditions: dict[str, Quantity],
) -> HeatExchangerRatedPointSelection:
    return HeatExchangerRatedPointSelection(
        product=product,
        rated_point_id="hx-rated-1",
        refrigerant="R744",
        topology=ProductTopology.R744_TRANSCRITICAL,
        operating_mode=OperatingMode.COOLING,
        conditions=conditions,
    )


def _boundaries(*, secondary_temperature_k: float = 290.0) -> HeatExchangerBoundaryInput:
    backend = CoolPropBackend()
    return HeatExchangerBoundaryInput(
        refrigerant_inlet_state=backend.state_pt(
            "R744",
            Pressure(value=9_000_000.0, unit="Pa"),
            Temperature(value=375.0, unit="K"),
        ),
        refrigerant_mass_flow=MassFlow(value=0.1, unit="kg/s"),
        secondary_inlet_temperature=Temperature(value=secondary_temperature_k, unit="K"),
        secondary_mass_flow=MassFlow(value=1.0, unit="kg/s"),
        secondary_specific_heat_capacity=SpecificHeatCapacity(
            value=1_000.0,
            unit="J/(kg*K)",
        ),
        cell_count=80,
    )


def _mode_product(
    component_type: str,
    *,
    pressure_pa: float,
    temperature_k: float,
    ua_w_k: float = 100.0,
    pressure_drop_pa: float = 0.0,
) -> tuple[ProductRecord, dict[str, Quantity]]:
    """Build a production-validated synthetic HX product for one exact rated point."""
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    point_id = f"hx-rated-{component_type}"
    raw["product_id"] = f"mock-r744-{component_type}-1"
    raw["component_type"] = component_type
    raw["model"] = f"HX-MOCK-{component_type.upper()}"
    raw["rated_points"][0]["rated_point_id"] = point_id
    raw["rated_points"][0]["topology"] = "SUBCRITICAL"
    condition_by_name = {
        value["canonical_name"]: value for value in raw["rated_points"][0]["conditions"]
    }
    condition_by_name["inlet_pressure"].update(
        original_value=pressure_pa,
        original_unit="Pa",
        value_si={"value": pressure_pa, "unit": "Pa"},
    )
    condition_by_name["inlet_temperature"].update(
        original_value=temperature_k,
        original_unit="K",
        value_si={"value": temperature_k, "unit": "K"},
    )
    condition_by_name["mass_flow"].update(
        original_value=0.1,
        original_unit="kg/s",
        value_si={"value": 0.1, "unit": "kg/s"},
    )
    output_by_name = {value["canonical_name"]: value for value in raw["rated_points"][0]["outputs"]}
    output_by_name["ua"].update(
        original_value=ua_w_k,
        original_unit="W/K",
        value_si={"value": ua_w_k, "unit": "W/K"},
    )
    output_by_name["refrigerant_pressure_drop"].update(
        original_value=pressure_drop_pa,
        original_unit="Pa",
        value_si={"value": pressure_drop_pa, "unit": "Pa"},
    )
    product = ProductRecord.model_validate(raw)
    return product, {
        "inlet_pressure": Quantity(value=pressure_pa, unit="Pa"),
        "inlet_temperature": Quantity(value=temperature_k, unit="K"),
        "mass_flow": Quantity(value=0.1, unit="kg/s"),
    }


def _mode_selection(
    product: ProductRecord,
    conditions: dict[str, Quantity],
) -> HeatExchangerRatedPointSelection:
    return HeatExchangerRatedPointSelection(
        product=product,
        rated_point_id=product.rated_points[0].rated_point_id,
        refrigerant="R744",
        topology=product.rated_points[0].topology,
        operating_mode=product.rated_points[0].mode,
        conditions=conditions,
    )


def _mode_boundaries(
    *,
    pressure_pa: float,
    temperature_k: float,
    secondary_temperature_k: float,
    cell_count: int = 40,
) -> HeatExchangerBoundaryInput:
    backend = CoolPropBackend()
    return HeatExchangerBoundaryInput(
        refrigerant_inlet_state=backend.state_pt(
            "R744",
            Pressure(value=pressure_pa, unit="Pa"),
            Temperature(value=temperature_k, unit="K"),
        ),
        refrigerant_mass_flow=MassFlow(value=0.1, unit="kg/s"),
        secondary_inlet_temperature=Temperature(value=secondary_temperature_k, unit="K"),
        secondary_mass_flow=MassFlow(value=1.0, unit="kg/s"),
        secondary_specific_heat_capacity=SpecificHeatCapacity(
            value=1_000.0,
            unit="J/(kg*K)",
        ),
        cell_count=cell_count,
    )


def _direct_result(
    backend: CoolPropBackend,
    rated: HeatExchangerRatedPointView,
    boundaries: HeatExchangerBoundaryInput,
) -> HeatExchanger1DResult:
    return evaluate_heat_exchanger_1d(
        backend,
        HeatExchanger1DInput(
            mode=rated.heat_exchanger_mode,
            refrigerant_inlet_state=boundaries.refrigerant_inlet_state,
            refrigerant_mass_flow=boundaries.refrigerant_mass_flow,
            secondary_inlet_temperature=boundaries.secondary_inlet_temperature,
            secondary_mass_flow=boundaries.secondary_mass_flow,
            secondary_specific_heat_capacity=boundaries.secondary_specific_heat_capacity,
            total_thermal_conductance=rated.total_thermal_conductance,
            refrigerant_pressure_drop=rated.refrigerant_pressure_drop,
            cell_count=boundaries.cell_count,
        ),
    )


def test_synthetic_fixture_passes_production_product_record_validation(
    product: ProductRecord,
) -> None:
    assert product.product_id == "mock-r744-gas-cooler-1"
    assert product.is_mock is True
    assert len(product.rated_points) == 1


def test_selected_rated_point_preserves_values_conditions_sources_and_mock_status(
    product: ProductRecord,
    conditions: dict[str, Quantity],
) -> None:
    rated = select_heat_exchanger_rated_point(_selection(product, conditions))

    assert rated.product_id == "mock-r744-gas-cooler-1"
    assert rated.rated_point_id == "hx-rated-1"
    assert rated.rated_point_source_id == "src-rated-parent"
    assert rated.is_mock is True
    assert rated.total_thermal_conductance.value == 200.0
    assert rated.total_thermal_conductance.unit == "watt / kelvin"
    assert rated.refrigerant_pressure_drop.value == 10_000.0
    assert rated.refrigerant_pressure_drop.unit == "pascal"
    ua_trace = next(value for value in rated.rated_outputs if value.canonical_name == "ua")
    assert (ua_trace.original_value, ua_trace.original_unit) == (200.0, "W/K")
    assert {value.value_id: value.source_id for value in rated.rated_conditions} == {
        "condition-inlet-pressure": "src-rated-conditions",
        "condition-inlet-temperature": "src-rated-conditions",
        "condition-mass-flow": "src-rated-conditions",
    }
    assert {value.value_id: value.source_id for value in rated.rated_outputs} == {
        "output-ua": "src-rated-ua",
        "output-refrigerant-dp": "src-rated-dp",
        "output-rated-heat-rejection": "src-rated-capacity",
    }


def test_connection_matches_direct_p05_call_and_keeps_rated_performance_separate(
    product: ProductRecord,
    conditions: dict[str, Quantity],
) -> None:
    backend = CoolPropBackend()
    rated = select_heat_exchanger_rated_point(_selection(product, conditions))
    boundaries = _boundaries()

    connected = evaluate_heat_exchanger_rated_point(backend, rated, boundaries)
    direct = evaluate_heat_exchanger_1d(
        backend,
        HeatExchanger1DInput(
            mode=rated.heat_exchanger_mode,
            refrigerant_inlet_state=boundaries.refrigerant_inlet_state,
            refrigerant_mass_flow=boundaries.refrigerant_mass_flow,
            secondary_inlet_temperature=boundaries.secondary_inlet_temperature,
            secondary_mass_flow=boundaries.secondary_mass_flow,
            secondary_specific_heat_capacity=boundaries.secondary_specific_heat_capacity,
            total_thermal_conductance=rated.total_thermal_conductance,
            refrigerant_pressure_drop=rated.refrigerant_pressure_drop,
            cell_count=boundaries.cell_count,
        ),
    )

    assert connected.model_path == "RATED_POINT_CONSTANT_UA"
    assert connected.calculation == direct
    rated_heat_rejection = next(
        output
        for output in connected.rated_data.rated_outputs
        if output.canonical_name == "heat_rejection"
    )
    assert rated_heat_rejection.value == 10_000.0
    assert connected.calculation.total_heat_to_refrigerant.value != -rated_heat_rejection.value


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ({"inlet_pressure": Quantity(value=89.0, unit="bar")}, "does not exactly match"),
        ({"inlet_temperature": Quantity(value=1.0, unit="m")}, "incompatible"),
    ],
)
def test_condition_value_and_unit_mismatch_are_rejected(
    product: ProductRecord,
    conditions: dict[str, Quantity],
    replacement: dict[str, Quantity],
    message: str,
) -> None:
    invalid = {**conditions, **replacement}
    with pytest.raises(HeatExchangerRatedPointError, match=message):
        select_heat_exchanger_rated_point(_selection(product, invalid))


def test_missing_or_extra_applicability_conditions_are_rejected(
    product: ProductRecord,
    conditions: dict[str, Quantity],
) -> None:
    missing = dict(conditions)
    missing.pop("mass_flow")
    with pytest.raises(HeatExchangerRatedPointError, match="supplied exactly"):
        select_heat_exchanger_rated_point(_selection(product, missing))

    extra = {**conditions, "air_volume_flow": Quantity(value=1.0, unit="m^3/s")}
    with pytest.raises(HeatExchangerRatedPointError, match="supplied exactly"):
        select_heat_exchanger_rated_point(_selection(product, extra))


def test_wrong_id_refrigerant_topology_and_mode_are_rejected(
    product: ProductRecord,
    conditions: dict[str, Quantity],
) -> None:
    base = _selection(product, conditions)
    with pytest.raises(HeatExchangerRatedPointError, match="does not contain"):
        select_heat_exchanger_rated_point(replace(base, rated_point_id="missing"))
    with pytest.raises(HeatExchangerRatedPointError, match="refrigerant"):
        select_heat_exchanger_rated_point(replace(base, refrigerant="R134a"))
    with pytest.raises(HeatExchangerRatedPointError, match="topology"):
        select_heat_exchanger_rated_point(replace(base, topology=ProductTopology.SUBCRITICAL))
    with pytest.raises(HeatExchangerRatedPointError, match="operating mode"):
        select_heat_exchanger_rated_point(replace(base, operating_mode=OperatingMode.HEATING))


def test_ineligible_and_missing_required_outputs_are_rejected(
    product: ProductRecord,
    conditions: dict[str, Quantity],
) -> None:
    ineligible_status = DataUseStatus(
        source_preserved=True,
        structure_valid=True,
        automatic_selection=AutomaticSelectionStatus.INELIGIBLE,
        reasons=(UseRestrictionReason.UA_NOT_AVAILABLE,),
    )
    rated_point = product.rated_points[0]
    ineligible = product.model_copy(
        update={"rated_points": (rated_point.model_copy(update={"use_status": ineligible_status}),)}
    )
    with pytest.raises(HeatExchangerRatedPointError, match="not eligible"):
        select_heat_exchanger_rated_point(_selection(ineligible, conditions))

    for missing_name in ("ua", "refrigerant_pressure_drop"):
        incomplete = product.model_copy(
            update={
                "rated_points": (
                    rated_point.model_copy(
                        update={
                            "outputs": tuple(
                                value
                                for value in rated_point.outputs
                                if value.canonical_name.value != missing_name
                            )
                        }
                    ),
                )
            }
        )
        with pytest.raises(
            HeatExchangerRatedPointError,
            match=f"missing required output '{missing_name}'",
        ):
            select_heat_exchanger_rated_point(_selection(incomplete, conditions))

    without_mass_flow_condition = product.model_copy(
        update={
            "rated_points": (
                rated_point.model_copy(update={"conditions": rated_point.conditions[:-1]}),
            )
        }
    )
    incomplete_request = _selection(without_mass_flow_condition, conditions)
    with pytest.raises(HeatExchangerRatedPointError, match="lacks required.*mass_flow"):
        select_heat_exchanger_rated_point(incomplete_request)


def test_invalid_source_reference_is_rejected_by_contract_and_connection_boundary(
    product: ProductRecord,
    conditions: dict[str, Quantity],
) -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["rated_points"][0]["outputs"][0]["source_id"] = "missing-source"
    with pytest.raises(ValidationError, match="unresolved value source_id"):
        ProductRecord.model_validate(raw)

    rated_point = product.rated_points[0]
    bad_output = rated_point.outputs[0].model_copy(update={"source_id": "missing-source"})
    bypassed = product.model_copy(
        update={
            "rated_points": (
                rated_point.model_copy(update={"outputs": (bad_output, *rated_point.outputs[1:])}),
            )
        }
    )
    with pytest.raises(HeatExchangerRatedPointError, match="unresolved source_id"):
        select_heat_exchanger_rated_point(_selection(bypassed, conditions))


def test_p05_calculation_failures_are_not_hidden(
    product: ProductRecord,
    conditions: dict[str, Quantity],
) -> None:
    rated = select_heat_exchanger_rated_point(_selection(product, conditions))
    with pytest.raises(InfeasibleDesignError, match="colder than the refrigerant"):
        evaluate_heat_exchanger_rated_point(
            CoolPropBackend(),
            rated,
            _boundaries(secondary_temperature_k=400.0),
        )


def test_hx_candidate_trial_does_not_reuse_prior_prediction_on_failure(
    product: ProductRecord,
    conditions: dict[str, Quantity],
) -> None:
    selection = _selection(product, conditions)
    backend = CoolPropBackend()
    candidates = (
        ComponentCandidateTrial("hx-a", HeatExchangerTrialInput(backend, selection, _boundaries())),
        ComponentCandidateTrial(
            "hx-b",
            HeatExchangerTrialInput(backend, selection, _boundaries(secondary_temperature_k=400.0)),
        ),
        ComponentCandidateTrial("hx-c", HeatExchangerTrialInput(backend, selection, _boundaries())),
    )

    first, rejected, last = evaluate_synthetic_component_trials(candidates)

    assert (first.status, rejected.status, last.status) == (
        "EVALUATED",
        "REJECTED",
        "EVALUATED",
    )
    assert all(outcome.is_mock for outcome in (first, rejected, last))
    assert all(outcome.record_id == "hx-rated-1" for outcome in (first, rejected, last))
    assert rejected.selected_source_ids == ("src-rated-parent",)
    assert first.result is not None and last.result is not None
    assert first.result.calculation == last.result.calculation
    assert first.result.rated_data.rated_point_source_id == "src-rated-parent"
    assert rejected.result is None
    assert rejected.failure_type == "InfeasibleDesignError"
    assert "colder than the refrigerant" in (rejected.failure_message or "")


def test_boundary_refrigerant_must_match_selected_rated_point(
    product: ProductRecord,
    conditions: dict[str, Quantity],
) -> None:
    rated = select_heat_exchanger_rated_point(_selection(product, conditions))
    boundaries = _boundaries()
    wrong_state = boundaries.refrigerant_inlet_state.model_copy(update={"fluid": "R134a"})
    with pytest.raises(HeatExchangerRatedPointError, match="does not match"):
        evaluate_heat_exchanger_rated_point(
            CoolPropBackend(),
            rated,
            replace(boundaries, refrigerant_inlet_state=wrong_state),
        )


def test_p05_boundaries_must_match_selected_rated_conditions(
    product: ProductRecord,
    conditions: dict[str, Quantity],
) -> None:
    rated = select_heat_exchanger_rated_point(_selection(product, conditions))
    boundaries = _boundaries()
    with pytest.raises(HeatExchangerRatedPointError, match="mass_flow.*does not match"):
        evaluate_heat_exchanger_rated_point(
            CoolPropBackend(),
            rated,
            replace(
                boundaries,
                refrigerant_mass_flow=MassFlow(value=0.2, unit="kg/s"),
            ),
        )


@pytest.mark.parametrize(
    ("component_type", "pressure_pa", "temperature_k", "secondary_temperature_k"),
    [
        ("evaporator", 3_000_000.0, 260.0, 280.0),
        ("condenser", 5_500_000.0, 300.0, 280.0),
    ],
)
def test_evaporator_and_condenser_fixtures_validate_and_match_direct_p05(
    component_type: str,
    pressure_pa: float,
    temperature_k: float,
    secondary_temperature_k: float,
) -> None:
    product, requested_conditions = _mode_product(
        component_type,
        pressure_pa=pressure_pa,
        temperature_k=temperature_k,
    )
    assert ProductRecord.model_validate(product.model_dump()) == product
    rated = select_heat_exchanger_rated_point(_mode_selection(product, requested_conditions))
    boundaries = _mode_boundaries(
        pressure_pa=pressure_pa,
        temperature_k=temperature_k,
        secondary_temperature_k=secondary_temperature_k,
    )
    backend = CoolPropBackend()

    connected = evaluate_heat_exchanger_rated_point(backend, rated, boundaries)

    assert connected.calculation == _direct_result(backend, rated, boundaries)
    assert connected.rated_data.product_id == f"mock-r744-{component_type}-1"
    assert connected.rated_data.is_mock is True


@pytest.mark.parametrize("ua_w_k", [0.0, -1.0])
def test_nonpositive_rated_ua_is_rejected_after_production_validation(
    ua_w_k: float,
) -> None:
    product, requested_conditions = _mode_product(
        "evaporator",
        pressure_pa=3_000_000.0,
        temperature_k=260.0,
        ua_w_k=ua_w_k,
    )
    with pytest.raises(HeatExchangerRatedPointError, match="ua must be finite and positive"):
        select_heat_exchanger_rated_point(_mode_selection(product, requested_conditions))


def test_negative_pressure_drop_is_rejected_and_zero_is_preserved() -> None:
    negative, negative_conditions = _mode_product(
        "evaporator",
        pressure_pa=3_000_000.0,
        temperature_k=260.0,
        pressure_drop_pa=-1.0,
    )
    with pytest.raises(HeatExchangerRatedPointError, match="must be nonnegative"):
        select_heat_exchanger_rated_point(_mode_selection(negative, negative_conditions))

    zero, zero_conditions = _mode_product(
        "evaporator",
        pressure_pa=3_000_000.0,
        temperature_k=260.0,
        pressure_drop_pa=0.0,
    )
    rated = select_heat_exchanger_rated_point(_mode_selection(zero, zero_conditions))
    boundaries = _mode_boundaries(
        pressure_pa=3_000_000.0,
        temperature_k=260.0,
        secondary_temperature_k=280.0,
    )
    result = evaluate_heat_exchanger_rated_point(CoolPropBackend(), rated, boundaries)
    assert result.calculation.total_refrigerant_pressure_drop.value == pytest.approx(0.0, abs=0.0)


def test_pressure_drop_that_reaches_zero_absolute_pressure_is_not_hidden() -> None:
    product, requested_conditions = _mode_product(
        "evaporator",
        pressure_pa=3_000_000.0,
        temperature_k=260.0,
        pressure_drop_pa=3_000_000.0,
    )
    rated = select_heat_exchanger_rated_point(_mode_selection(product, requested_conditions))
    boundaries = _mode_boundaries(
        pressure_pa=3_000_000.0,
        temperature_k=260.0,
        secondary_temperature_k=280.0,
        cell_count=1,
    )
    with pytest.raises(ConvergenceError, match="nonpositive pressure"):
        evaluate_heat_exchanger_rated_point(CoolPropBackend(), rated, boundaries)


@pytest.mark.parametrize(
    ("pressure_pa", "temperature_k", "message"),
    [
        (2_900_000.0, 260.0, "inlet_pressure.*does not match"),
        (3_000_000.0, 261.0, "inlet_temperature.*does not match"),
    ],
)
def test_actual_p05_pressure_and_temperature_must_match_rated_conditions(
    pressure_pa: float,
    temperature_k: float,
    message: str,
) -> None:
    product, requested_conditions = _mode_product(
        "evaporator",
        pressure_pa=3_000_000.0,
        temperature_k=260.0,
    )
    rated = select_heat_exchanger_rated_point(_mode_selection(product, requested_conditions))
    boundaries = _mode_boundaries(
        pressure_pa=pressure_pa,
        temperature_k=temperature_k,
        secondary_temperature_k=280.0,
    )
    with pytest.raises(HeatExchangerRatedPointError, match=message):
        evaluate_heat_exchanger_rated_point(CoolPropBackend(), rated, boundaries)


@pytest.mark.parametrize(
    ("component_type", "pressure_pa", "temperature_k", "secondary_temperature_k"),
    [
        ("evaporator", 3_000_000.0, 260.0, 250.0),
        ("condenser", 5_500_000.0, 300.0, 310.0),
    ],
)
def test_wrong_heat_transfer_direction_is_not_hidden(
    component_type: str,
    pressure_pa: float,
    temperature_k: float,
    secondary_temperature_k: float,
) -> None:
    product, requested_conditions = _mode_product(
        component_type,
        pressure_pa=pressure_pa,
        temperature_k=temperature_k,
    )
    rated = select_heat_exchanger_rated_point(_mode_selection(product, requested_conditions))
    boundaries = _mode_boundaries(
        pressure_pa=pressure_pa,
        temperature_k=temperature_k,
        secondary_temperature_k=secondary_temperature_k,
    )
    with pytest.raises(InfeasibleDesignError, match="secondary stream"):
        evaluate_heat_exchanger_rated_point(CoolPropBackend(), rated, boundaries)


def test_physical_state_incompatible_with_selected_mode_is_not_hidden() -> None:
    product, requested_conditions = _mode_product(
        "evaporator",
        pressure_pa=9_000_000.0,
        temperature_k=375.0,
    )
    rated = select_heat_exchanger_rated_point(_mode_selection(product, requested_conditions))
    boundaries = _mode_boundaries(
        pressure_pa=9_000_000.0,
        temperature_k=375.0,
        secondary_temperature_k=400.0,
    )
    with pytest.raises(InfeasibleDesignError, match="cannot be treated as evaporator"):
        evaluate_heat_exchanger_rated_point(CoolPropBackend(), rated, boundaries)


def test_multiple_rated_points_use_only_the_requested_id_without_fallback() -> None:
    product, requested_conditions = _mode_product(
        "condenser",
        pressure_pa=5_500_000.0,
        temperature_k=300.0,
        ua_w_k=100.0,
    )
    raw = product.model_dump(mode="json")
    second = deepcopy(raw["rated_points"][0])
    second["rated_point_id"] = "hx-rated-condenser-second"
    for value in second["conditions"] + second["outputs"]:
        value["value_id"] = f"{value['value_id']}-second"
    ua = next(value for value in second["outputs"] if value["canonical_name"] == "ua")
    ua["original_value"] = 300.0
    ua["value_si"] = {"value": 300.0, "unit": "W/K"}
    raw["rated_points"].append(second)
    multi = ProductRecord.model_validate(raw)

    first = select_heat_exchanger_rated_point(_mode_selection(multi, requested_conditions))
    assert first.rated_point_id == "hx-rated-condenser"
    assert first.total_thermal_conductance.value == 100.0

    missing = replace(
        _mode_selection(multi, requested_conditions),
        rated_point_id="missing-rated-point",
    )
    with pytest.raises(HeatExchangerRatedPointError, match="does not contain"):
        select_heat_exchanger_rated_point(missing)
