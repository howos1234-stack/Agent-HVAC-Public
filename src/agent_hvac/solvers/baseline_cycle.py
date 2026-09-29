"""P02 adapter from frozen design contracts to the baseline cycle model."""

from pydantic import ValidationError

from agent_hvac.physics.cycle import BaselineCycleInputs, solve_baseline_cycle
from agent_hvac.properties.base import PropertyBackend
from agent_hvac.schemas.design import DesignSpecification
from agent_hvac.schemas.results import SimulationResult, SolverStatus
from agent_hvac.utils.exceptions import (
    ConvergenceError,
    InfeasibleDesignError,
    InvalidPropertyStateError,
)
from agent_hvac.utils.units import MassFlow, Power, Pressure, Quantity, Temperature

_TOPOLOGY = "single-stage-baseline"


class BaselineCycleSolver:
    def __init__(self, backend: PropertyBackend) -> None:
        self._backend = backend

    def simulate(self, design: DesignSpecification) -> SimulationResult:
        """Return an explicit structured outcome for every approved failure class."""
        try:
            inputs = self._parse_inputs(design)
            solution = solve_baseline_cycle(self._backend, inputs)
        except InvalidPropertyStateError as exc:
            return self._failure(design, SolverStatus.INVALID_PROPERTY_STATE, str(exc))
        except InfeasibleDesignError as exc:
            return self._failure(design, SolverStatus.INFEASIBLE, str(exc))
        except ConvergenceError as exc:
            return self._failure(design, SolverStatus.UNCONVERGED, str(exc))

        return SimulationResult(
            design_id=design.design_id,
            status=SolverStatus.CONVERGED,
            is_mock=design.is_mock,
            state_points=solution.state_points,
            mass_flow=inputs.refrigerant_mass_flow,
            compressor_power=Power(value=solution.compressor_power_w, unit="W"),
            evaporator_capacity=Power(value=solution.evaporator_capacity_w, unit="W"),
            heat_rejection=Power(value=solution.heat_rejection_w, unit="W"),
            heat_exchanger_duties={
                "evaporator": Power(value=solution.evaporator_capacity_w, unit="W"),
                "heat_rejection": Power(value=solution.heat_rejection_w, unit="W"),
            },
            cop=solution.cop,
            energy_balance_error=solution.energy_balance_error,
            mass_balance_error=solution.mass_balance_error,
        )

    @staticmethod
    def _parse_inputs(design: DesignSpecification) -> BaselineCycleInputs:
        if design.topology.value != _TOPOLOGY:
            raise InfeasibleDesignError(f"topology must be {_TOPOLOGY!r}")
        parameters = {
            parameter.name: parameter.value
            for parameter in design.fixed + design.boundary_conditions
        }

        def typed(name: str, model: type[Quantity]) -> Quantity:
            value = parameters.get(name)
            if value is None:
                raise InfeasibleDesignError(f"missing required input: {name}")
            if not isinstance(value, Quantity):
                raise InfeasibleDesignError(f"{name} must be a physical quantity")
            try:
                return model.model_validate(value.model_dump())
            except ValidationError as exc:
                raise InfeasibleDesignError(
                    f"{name} has an incompatible unit: {value.unit}"
                ) from exc

        efficiency_value = typed("compressor_isentropic_efficiency", Quantity)
        if efficiency_value.unit != "dimensionless":
            raise InfeasibleDesignError("compressor_isentropic_efficiency must be dimensionless")
        return BaselineCycleInputs(
            fluid=str(design.refrigerant.value),
            evaporator_pressure=Pressure.model_validate(
                typed("evaporator_pressure", Pressure).model_dump()
            ),
            high_side_pressure=Pressure.model_validate(
                typed("high_side_pressure", Pressure).model_dump()
            ),
            compressor_inlet_temperature=Temperature.model_validate(
                typed("compressor_inlet_temperature", Temperature).model_dump()
            ),
            heat_rejection_outlet_temperature=Temperature.model_validate(
                typed("heat_rejection_outlet_temperature", Temperature).model_dump()
            ),
            refrigerant_mass_flow=MassFlow.model_validate(
                typed("refrigerant_mass_flow", MassFlow).model_dump()
            ),
            compressor_isentropic_efficiency=efficiency_value.value,
        )

    @staticmethod
    def _failure(
        design: DesignSpecification,
        status: SolverStatus,
        message: str,
    ) -> SimulationResult:
        return SimulationResult(
            design_id=design.design_id,
            status=status,
            is_mock=design.is_mock,
            messages=(message,),
        )
