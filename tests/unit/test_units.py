import pytest
from pydantic import ValidationError

from agent_hvac.utils.units import (
    Length,
    MassFlow,
    Pressure,
    Quantity,
    SpecificEntropy,
    Temperature,
    TemperatureDifference,
)


@pytest.mark.parametrize(
    "schema,value,unit,expected",
    [
        (Length, 50, "cm", 0.5),
        (Pressure, 10, "bar", 1_000_000),
        (Temperature, 25, "degC", 298.15),
        (TemperatureDifference, 9, "delta_degF", 5),
        (MassFlow, 3600, "kg/hour", 1),
    ],
)
def test_si_normalization(schema, value, unit, expected):
    q = schema(value=value, unit=unit)
    assert q.value == pytest.approx(expected)
    assert schema.model_validate_json(q.model_dump_json()) == q


@pytest.mark.parametrize(
    "schema,value,unit",
    [
        (Length, 1, "kg"),
        (Pressure, 1, "m"),
        (Temperature, -274, "degC"),
        (Temperature, 20, "delta_degC"),
        (TemperatureDifference, 20, "degC"),
        (Pressure, 0, "Pa"),
        (Length, -1, "m"),
        (MassFlow, 0, "kg/s"),
        (Quantity, float("nan"), "m"),
        (Quantity, float("inf"), "m"),
        (Quantity, 1, "not_a_unit"),
    ],
)
def test_reject_invalid_quantities(schema, value, unit):
    with pytest.raises(ValidationError):
        schema(value=value, unit=unit)


def test_unit_is_required():
    with pytest.raises(ValidationError):
        Quantity(value=50)


def test_specific_entropy_normalizes_mass_specific_units_and_round_trips():
    entropy = SpecificEntropy(value=1.25, unit="kJ/(kg*K)")

    assert entropy.value == pytest.approx(1_250.0)
    assert entropy.unit == "joule / kelvin / kilogram"
    assert SpecificEntropy.model_validate_json(entropy.model_dump_json()) == entropy


@pytest.mark.parametrize("value", [0.0, -100.0])
def test_specific_entropy_unit_type_does_not_impose_a_positive_constraint(value):
    entropy = SpecificEntropy(value=value, unit="J/(kg*K)")

    assert entropy.value == value


@pytest.mark.parametrize(
    ("value", "unit"),
    [
        (float("nan"), "J/(kg*K)"),
        (float("inf"), "J/(kg*K)"),
        (1.0, "J/(mol*K)"),
        (1.0, "J/kg"),
    ],
)
def test_specific_entropy_rejects_nonfinite_molar_or_wrong_dimensions(value, unit):
    with pytest.raises(ValidationError):
        SpecificEntropy(value=value, unit=unit)
