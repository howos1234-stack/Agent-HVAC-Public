"""Unit-bearing, mock-only inputs and diagnostics for the S1 circuit harness."""

import math
from typing import Literal, Self

from pydantic import Field, model_validator

from agent_hvac.components.heat_exchanger_1d import (
    HeatExchanger1DResult,
    SpecificHeatCapacity,
    ThermalConductance,
)
from agent_hvac.components.pipe import (
    DynamicViscosity,
    LinearHeatTransferCoefficient,
    NonnegativeLength,
    Pipe1DResult,
)
from agent_hvac.physics.state import ThermoState
from agent_hvac.schemas.base import ContractModel, NonEmptyStr
from agent_hvac.utils.units import (
    Length,
    MassFlow,
    Power,
    Pressure,
    PressureDifference,
    Quantity,
    SpecificEnthalpy,
    Temperature,
    TemperatureDifference,
)

CircuitStatus = Literal[
    "evaluated", "infeasible", "invalid-property-state", "component-numerical-failure"
]


class SignedPressure(Quantity):
    canonical_unit = "Pa"


class Efficiency(Quantity):
    canonical_unit = "dimensionless"
    positive = True

    @model_validator(mode="after")
    def at_most_one(self) -> Self:
        if self.value > 1.0:
            raise ValueError("isentropic efficiency must be in (0, 1]")
        return self


class HXScenario(ContractModel):
    source_ref: NonEmptyStr
    secondary_inlet_temperature: Temperature
    secondary_mass_flow: MassFlow
    secondary_specific_heat_capacity: SpecificHeatCapacity
    total_thermal_conductance: ThermalConductance
    cell_count: int = Field(ge=1, strict=True)


class PipeScenario(ContractModel):
    source_ref: NonEmptyStr
    length: NonnegativeLength
    inner_diameter: Length
    roughness: NonnegativeLength
    dynamic_viscosity: DynamicViscosity
    ambient_temperature: Temperature
    linear_heat_transfer_coefficient: LinearHeatTransferCoefficient
    cell_count: int = Field(ge=1, le=1000, strict=True)


class NetworkScenario(ContractModel):
    source_ref: NonEmptyStr
    discharge_pipe: PipeScenario
    high_side_pipe: PipeScenario
    suction_pipe: PipeScenario
    gas_cooler_pressure_drop: PressureDifference | None = None
    condenser_pressure_drop: PressureDifference | None = None

    @property
    def high_side_pressure_drop(self) -> PressureDifference:
        value = self.condenser_pressure_drop or self.gas_cooler_pressure_drop
        assert value is not None
        return value

    evaporator_pressure_drop: PressureDifference
    valve_pressure_lower: Pressure
    valve_pressure_upper: Pressure
    pressure_scan_intervals: int = Field(ge=1, le=100, strict=True)
    pressure_max_iterations: int = Field(ge=1, le=100, strict=True)
    pressure_tolerance: PressureDifference

    @model_validator(mode="after")
    def finite_bounds(self) -> Self:
        if (self.gas_cooler_pressure_drop is None) == (self.condenser_pressure_drop is None):
            raise ValueError("exactly one high-side HX pressure drop is required")
        span = self.valve_pressure_upper.value - self.valve_pressure_lower.value
        if not math.isfinite(span) or span <= 0:
            raise ValueError("valve pressure bounds require a finite positive span")
        if not 0 < self.pressure_tolerance.value <= 0.01:
            raise ValueError("network pressure tolerance must be in (0, 0.01] Pa")
        return self


class PressureSample(ContractModel):
    trial_valve_pressure: Pressure
    residual: SignedPressure | None
    status: CircuitStatus
    failed_stage: str | None
    message: NonEmptyStr


class SyntheticScenario(ContractModel):
    """Fixed pressures/flow, zero pressure loss, no products or implicit defaults."""

    scenario_id: NonEmptyStr
    is_mock: Literal[True]
    source_type: Literal["AGENT_ASSUMPTION"]
    source_ref: NonEmptyStr
    assumptions: tuple[NonEmptyStr, ...] = Field(min_length=1)
    refrigerant: NonEmptyStr
    suction_pressure: Pressure
    discharge_pressure: Pressure
    trial_suction_temperature: Temperature
    refrigerant_mass_flow: MassFlow
    compressor_isentropic_efficiency: Efficiency
    gas_cooler: HXScenario | None = None
    condenser: HXScenario | None = None

    @property
    def high_side_name(self) -> Literal["gas_cooler", "condenser"]:
        return "condenser" if self.condenser is not None else "gas_cooler"

    @property
    def high_side_hx(self) -> HXScenario:
        config = self.condenser if self.condenser is not None else self.gas_cooler
        assert config is not None
        return config

    evaporator: HXScenario
    network: NetworkScenario | None = None

    @model_validator(mode="after")
    def ordered_pressures(self) -> Self:
        if (self.gas_cooler is None) == (self.condenser is None):
            raise ValueError("exactly one of gas_cooler or condenser is required")
        if self.network is not None and (
            (self.condenser is not None) != (self.network.condenser_pressure_drop is not None)
        ):
            raise ValueError("network pressure drop must match high-side HX mode")
        if self.discharge_pressure.value <= self.suction_pressure.value:
            raise ValueError("discharge_pressure must exceed suction_pressure")
        return self


class ComponentTrace(ContractModel):
    component: Literal[
        "compressor",
        "gas_cooler",
        "condenser",
        "valve",
        "evaporator",
        "discharge_pipe",
        "high_side_pipe",
        "suction_pipe",
    ]
    model_path: NonEmptyStr
    inlet_node: NonEmptyStr
    outlet_node: NonEmptyStr
    refrigerant_mass_flow: MassFlow
    heat_to_refrigerant: Power
    work_to_refrigerant: Power
    heat_exchanger: HeatExchanger1DResult | None = None
    pipe: Pipe1DResult | None = None


class LoopDiagnostics(ContractModel):
    """Signed SI residuals; the return node is never overwritten by the trial."""

    enthalpy_return_minus_trial: SpecificEnthalpy
    pressure_return_minus_trial: SignedPressure
    temperature_return_minus_trial: TemperatureDifference
    net_heat_and_work_to_refrigerant: Power
    transported_enthalpy_difference: Power
    transport_energy_error: Power
    relative_transport_energy_error: float = Field(ge=0)
    compressor_power: Power
    evaporator_heat: Power
    gas_cooler_heat_rejection: Power | None = None
    condenser_heat_rejection: Power | None = None

    @model_validator(mode="after")
    def one_rejection(self) -> Self:
        if (self.gas_cooler_heat_rejection is None) == (self.condenser_heat_rejection is None):
            raise ValueError("exactly one high-side rejection is required")
        return self

    @property
    def high_side_heat_rejection(self) -> Power:
        value = self.condenser_heat_rejection or self.gas_cooler_heat_rejection
        assert value is not None
        return value


class CircuitResult(ContractModel):
    scenario: SyntheticScenario
    is_mock: Literal[True] = True
    cycle_converged: Literal[False] = False
    trial_suction_enthalpy: SpecificEnthalpy | None = None
    pressure_history: tuple[PressureSample, ...] = ()
    status: CircuitStatus
    nodes: dict[str, ThermoState]
    components: tuple[ComponentTrace, ...]
    diagnostics: LoopDiagnostics | None = None
    failed_stage: NonEmptyStr | None = None
    message: NonEmptyStr

    @model_validator(mode="after")
    def consistent_outcome(self) -> Self:
        if self.status == "evaluated":
            if self.diagnostics is None or self.failed_stage is not None:
                raise ValueError("evaluated requires diagnostics and no failed_stage")
            count = 7 if self.scenario.network is not None else 4
            if len(self.components) != count or len(self.nodes) != count + 1:
                raise ValueError("evaluated requires the complete component chain and nodes")
        elif self.diagnostics is not None or self.failed_stage is None:
            raise ValueError("failure requires failed_stage and no completed diagnostics")
        return self
