"""Parsed requirements preserve unresolved values instead of fabricating them."""

from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from agent_hvac.schemas.base import ContractModel, NonEmptyStr
from agent_hvac.schemas.provenance import Parameter


class HITLMode(StrEnum):
    AUTO = "AUTO"
    REVIEW = "REVIEW"
    INTERACTIVE = "INTERACTIVE"


class MissingInput(ContractModel):
    name: NonEmptyStr
    classification: str = Field(pattern="^(essential|defaultable|free_variable)$")
    reason: NonEmptyStr


class UserRequirements(ContractModel):
    raw_prompt: NonEmptyStr
    parameters: tuple[Parameter, ...] = ()
    missing: tuple[MissingInput, ...] = ()
    requested_objective: Parameter | None = None
    mandatory_components: tuple[NonEmptyStr, ...] = ()
    forbidden_components: tuple[NonEmptyStr, ...] = ()
    hitl_mode: HITLMode

    @model_validator(mode="after")
    def no_conflicts(self) -> Self:
        names = [p.name for p in self.parameters]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate requirement parameter")
        missing_names = [m.name for m in self.missing]
        if len(missing_names) != len(set(missing_names)):
            raise ValueError("Duplicate missing input name")
        if set(names) & set(missing_names):
            raise ValueError("A supplied requirement cannot also be missing")
        if set(self.mandatory_components) & set(self.forbidden_components):
            raise ValueError("Component is both mandatory and forbidden")
        return self
