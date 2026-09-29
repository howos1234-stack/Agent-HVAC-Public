"""Design problem definitions, without candidate generation or optimization."""

from typing import Self

from pydantic import Field, model_validator

from agent_hvac.schemas.base import ContractModel, NonEmptyStr
from agent_hvac.schemas.components import ProductRecord
from agent_hvac.schemas.provenance import Parameter, Provenance
from agent_hvac.schemas.requirements import UserRequirements
from agent_hvac.utils.units import Quantity


class DecisionVariable(ContractModel):
    name: NonEmptyStr
    lower: Quantity
    upper: Quantity
    provenance: Provenance

    @model_validator(mode="after")
    def valid_bounds(self) -> Self:
        if self.lower.unit != self.upper.unit:
            raise ValueError("Bounds must have compatible dimensions")
        if self.lower.value >= self.upper.value:
            raise ValueError("Lower bound must be less than upper bound")
        return self


class Objective(ContractModel):
    metric: NonEmptyStr
    direction: str = Field(pattern="^(minimize|maximize)$")
    provenance: Provenance


class ConstraintDefinition(ContractModel):
    rule_id: NonEmptyStr
    parameter: NonEmptyStr
    operator: str = Field(pattern="^(le|ge|eq)$")
    limit: Quantity
    provenance: Provenance
    hard: bool


class DesignSpecification(ContractModel):
    design_id: NonEmptyStr
    requirements: UserRequirements
    refrigerant: Parameter
    topology: Parameter
    fixed: tuple[Parameter, ...] = ()
    boundary_conditions: tuple[Parameter, ...] = ()
    decision_variables: tuple[DecisionVariable, ...] = ()
    objectives: tuple[Objective, ...] = ()
    constraints: tuple[ConstraintDefinition, ...] = ()
    selected_products: tuple[ProductRecord, ...] = ()
    is_mock: bool

    @model_validator(mode="after")
    def coherent_design(self) -> Self:
        if self.refrigerant.name != "refrigerant" or not isinstance(self.refrigerant.value, str):
            raise ValueError("Refrigerant must be a named, sourced identifier")
        if self.topology.name != "topology" or not isinstance(self.topology.value, str):
            raise ValueError("Topology must be a named, sourced identifier")
        names = [p.name for p in self.fixed + self.boundary_conditions]
        names += [v.name for v in self.decision_variables]
        if len(names) != len(set(names)):
            raise ValueError("A design variable cannot occur in multiple categories")
        supplied = {p.name: p.value for p in self.requirements.parameters}
        resolved = {p.name: p.value for p in self.fixed + self.boundary_conditions}
        resolved["refrigerant"] = self.refrigerant.value
        if set(supplied) - set(resolved):
            raise ValueError("Supplied user constraints must remain in the design")
        for name, value in resolved.items():
            if name in supplied and supplied[name] != value:
                raise ValueError(f"User constraint changed: {name}")
        if set(supplied) & {v.name for v in self.decision_variables}:
            raise ValueError("A supplied user constraint cannot be a free variable")
        if any(p.is_mock != self.is_mock for p in self.selected_products):
            raise ValueError("Design and selected products must have matching mock flags")
        return self


class DesignProblem(ContractModel):
    baseline: DesignSpecification
    candidate_products: tuple[ProductRecord, ...] = ()
    random_seed: int | None = None
