"""Compact synthetic requirements and deterministic, bounded candidate expansion."""

import itertools
import json
import math
from importlib.resources import files
from typing import Literal, Self

from pydantic import Field, model_validator

from agent_hvac.components.heat_exchanger_1d import ThermalConductance
from agent_hvac.schemas.base import ContractModel, NonEmptyStr
from agent_hvac.solvers.system_cycle.analysis_manager import AdjustmentPermission, AnalysisRequest
from agent_hvac.solvers.system_cycle.design_study import DesignCase, DesignStudyRequest
from agent_hvac.utils.units import (
    MassFlow,
    Power,
    Pressure,
    Quantity,
    SpecificEnthalpy,
    Temperature,
)

AxisName = Literal[
    "suction_pressure",
    "discharge_pressure",
    "indoor_air_flow",
    "outdoor_air_flow",
    "condenser_ua",
    "evaporator_ua",
]
AXIS_PATHS = {
    "suction_pressure": "suction_pressure",
    "discharge_pressure": "discharge_pressure",
    "indoor_air_flow": "evaporator.secondary_mass_flow",
    "outdoor_air_flow": "condenser.secondary_mass_flow",
    "condenser_ua": "condenser.total_thermal_conductance",
    "evaporator_ua": "evaporator.total_thermal_conductance",
}
AXIS_TYPES: dict[str, type[Quantity]] = {
    "suction_pressure": Pressure,
    "discharge_pressure": Pressure,
    "indoor_air_flow": MassFlow,
    "outdoor_air_flow": MassFlow,
    "condenser_ua": ThermalConductance,
    "evaporator_ua": ThermalConductance,
}
AXIS_UNITS = {
    "suction_pressure": "Pa",
    "discharge_pressure": "Pa",
    "indoor_air_flow": "kg/s",
    "outdoor_air_flow": "kg/s",
    "condenser_ua": "W/K",
    "evaporator_ua": "W/K",
}


class OperatingPoint(ContractModel):
    suction_pressure: Pressure
    discharge_pressure: Pressure
    indoor_air_flow: MassFlow
    outdoor_air_flow: MassFlow
    condenser_ua: ThermalConductance
    evaporator_ua: ThermalConductance


class SearchAxis(ContractModel):
    name: AxisName
    minimum: Quantity
    maximum: Quantity
    samples: int = Field(ge=1, le=100, strict=True)
    authorization_ref: NonEmptyStr

    @model_validator(mode="after")
    def dimension_and_order(self) -> Self:
        kind = AXIS_TYPES[self.name]
        low = kind.model_validate(self.minimum.model_dump(mode="json"))
        high = kind.model_validate(self.maximum.model_dump(mode="json"))
        if low.value > high.value:
            raise ValueError("axis minimum must not exceed maximum")
        if (self.samples == 1) != (low.value == high.value):
            raise ValueError("one sample requires equal bounds; nonzero span requires >=2 samples")
        object.__setattr__(self, "minimum", low)
        object.__setattr__(self, "maximum", high)
        return self

    def values(self) -> tuple[float, ...]:
        if self.samples == 1:
            return (self.minimum.value,)
        span = self.maximum.value - self.minimum.value
        return tuple(
            self.minimum.value
            if i == 0
            else self.maximum.value
            if i == self.samples - 1
            else self.minimum.value + span * i / (self.samples - 1)
            for i in range(self.samples)
        )


class CompactAnalysisInput(ContractModel):
    """New run specification; adjusting these fixed values is never a retry permission."""

    raw_requirement: NonEmptyStr
    authorization_ref: NonEmptyStr
    preset: Literal["synthetic-condenser-v1"]
    refrigerant: NonEmptyStr
    refrigerant_mass_flow: MassFlow
    room_temperature: Temperature
    outdoor_temperature: Temperature
    sensible_load: Power
    boundary_source_type: Literal["USER", "AGENT_ASSUMPTION", "HUMAN_CONFIRMED"]
    boundary_source_ref: NonEmptyStr
    baseline: OperatingPoint
    lower_enthalpy: SpecificEnthalpy
    upper_enthalpy: SpecificEnthalpy
    valve_pressure_lower: Pressure
    valve_pressure_upper: Pressure
    axes: tuple[SearchAxis, ...] = Field(default=(), max_length=6)
    max_cases: int = Field(ge=1, le=100, strict=True)

    @property
    def candidate_count(self) -> int:
        if not self.axes:
            return 1
        includes_baseline = all(
            getattr(self.baseline, a.name).value in a.values() for a in self.axes
        )
        return math.prod(a.samples for a in self.axes) + int(not includes_baseline)

    @model_validator(mode="after")
    def validate_search(self) -> Self:
        if self.sensible_load.value <= 0 or self.upper_enthalpy.value <= self.lower_enthalpy.value:
            raise ValueError("positive load and ordered enthalpy bracket required")
        names = [a.name for a in self.axes]
        if len(set(names)) != len(names):
            raise ValueError("duplicate search axis")
        for axis in self.axes:
            baseline = getattr(self.baseline, axis.name).value
            if not axis.minimum.value <= baseline <= axis.maximum.value:
                raise ValueError("baseline must lie inside every authorized axis")
        if self.candidate_count > self.max_cases:
            raise ValueError(
                f"candidate budget exceeded: {self.candidate_count} > {self.max_cases}"
            )
        bounds = {a.name: (a.minimum.value, a.maximum.value) for a in self.axes}
        ps = self.baseline.suction_pressure.value
        pd = self.baseline.discharge_pressure.value
        low, high = bounds.get("suction_pressure", (ps, ps))
        if bounds.get("discharge_pressure", (pd, pd))[0] <= high:
            raise ValueError("every discharge pressure must exceed every suction pressure")
        if not self.valve_pressure_lower.value <= low <= high <= self.valve_pressure_upper.value:
            raise ValueError(
                "explicit valve pressure bracket must cover suction pressure candidates"
            )
        if self.valve_pressure_lower.value >= self.valve_pressure_upper.value:
            raise ValueError("valve bracket requires positive span")
        return self


def expand_analysis(request: CompactAnalysisInput) -> AnalysisRequest:
    """Baseline first, then lexically ordered Cartesian grid, without duplicate baseline.

    The packaged preset supplies explicitly disclosed synthetic geometry/settings.
    No product data, unbounded search, best-point extrapolation or tolerance edits.
    """
    request = CompactAnalysisInput.model_validate(request.model_dump(mode="json"))
    resource = files("agent_hvac.solvers.system_cycle").joinpath(
        "presets/synthetic-condenser-v1.json"
    )
    template = json.loads(resource.read_text(encoding="utf-8"))
    scenario = template["cycle_request"]["scenario"]
    scenario["refrigerant"] = request.refrigerant
    scenario["refrigerant_mass_flow"] = request.refrigerant_mass_flow.model_dump(mode="json")
    scenario["evaporator"]["secondary_inlet_temperature"] = request.room_temperature.model_dump(
        mode="json"
    )
    scenario["condenser"]["secondary_inlet_temperature"] = request.outdoor_temperature.model_dump(
        mode="json"
    )
    scenario["source_ref"] = request.authorization_ref
    scenario["assumptions"] = [
        f"USER fixed: {request.refrigerant}; continuous mass flow "
        f"{request.refrigerant_mass_flow.value} kg/s; room boundary "
        f"{request.room_temperature.value} K.",
        f"{request.boundary_source_type}: outdoor/load from {request.boundary_source_ref}.",
        "AGENT_ASSUMPTION: synthetic-condenser-v1; zero-length adiabatic single-phase pipes, "
        "eta_is=0.75, dry-air cp=1006 J/(kg K), co-current constant-UA HX with 80 cells. "
        "No products, room dynamics, fan/electrical power or independent manufacturer validation.",
        "Numerical settings from versioned preset; explicit enthalpy and valve brackets "
        "from this input. All tolerances unchanged.",
    ]
    scenario["network"]["valve_pressure_lower"] = request.valve_pressure_lower.model_dump(
        mode="json"
    )
    scenario["network"]["valve_pressure_upper"] = request.valve_pressure_upper.model_dump(
        mode="json"
    )
    settings = template["cycle_request"]["settings"]
    settings["lower_enthalpy"] = request.lower_enthalpy.model_dump(mode="json")
    settings["upper_enthalpy"] = request.upper_enthalpy.model_dump(mode="json")
    template["sensible_load"] = request.sensible_load.model_dump(mode="json")
    template["source_ref"] = request.authorization_ref
    baseline = {name: getattr(request.baseline, name).value for name in AXIS_PATHS}
    axes = sorted(request.axes, key=lambda a: a.name)
    coordinates = [baseline]
    if axes:
        for values in itertools.product(*(a.values() for a in axes)):
            point = baseline | dict(zip((a.name for a in axes), values, strict=True))
            if point != baseline:
                coordinates.append(point)
    cases = []
    for index, point in enumerate(coordinates):
        data = json.loads(json.dumps(template))
        data["case_id"] = f"candidate-{index:03}"
        data["family"] = "baseline" if index == 0 else "authorized-grid"
        s = data["cycle_request"]["scenario"]
        s["scenario_id"] = data["case_id"]
        for name, value in point.items():
            node = s
            segments = AXIS_PATHS[name].split(".")
            for segment in segments[:-1]:
                node = node[segment]
            node[segments[-1]] = {"value": value, "unit": AXIS_UNITS[name]}
        cases.append(DesignCase.model_validate(data))
    return AnalysisRequest(
        raw_requirement=request.raw_requirement,
        authorization_ref=request.authorization_ref,
        study=DesignStudyRequest(
            source_ref=request.authorization_ref,
            refrigerant=request.refrigerant,
            refrigerant_mass_flow=request.refrigerant_mass_flow,
            room_temperature=request.room_temperature,
            cases=tuple(cases),
        ),
        permissions=tuple(
            AdjustmentPermission(
                path=f"cycle_request.scenario.{AXIS_PATHS[a.name]}.value",
                unit=AXIS_UNITS[a.name],
                minimum=a.minimum.value,
                maximum=a.maximum.value,
                authorization_ref=a.authorization_ref,
            )
            for a in axes
        ),
        max_cases=request.max_cases,
    )
