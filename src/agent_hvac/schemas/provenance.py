"""Origins and reproducibility metadata; no invented default engineering values."""

from enum import StrEnum

from pydantic import AwareDatetime, Field, JsonValue

from agent_hvac.schemas.base import ContractModel, NonEmptyStr
from agent_hvac.utils.units import Quantity


class SourceType(StrEnum):
    USER = "USER"
    PRODUCT_DB = "PRODUCT_DB"
    DESIGN_GUIDELINE = "DESIGN_GUIDELINE"
    PHYSICS_DERIVED = "PHYSICS_DERIVED"
    OPTIMIZED = "OPTIMIZED"
    AGENT_ASSUMPTION = "AGENT_ASSUMPTION"
    HUMAN_CONFIRMED = "HUMAN_CONFIRMED"


class Provenance(ContractModel):
    source_type: SourceType
    source_ref: NonEmptyStr
    confidence: float | None = Field(default=None, ge=0, le=1)
    note: str | None = None


class Parameter(ContractModel):
    """Numbers require an explicit Quantity, including dimensionless values."""

    name: NonEmptyStr
    value: Quantity | NonEmptyStr
    provenance: Provenance


class RunMetadata(ContractModel):
    run_id: NonEmptyStr
    created_at: AwareDatetime
    code_version: NonEmptyStr
    dependency_lock_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    database_version: NonEmptyStr
    guideline_version: NonEmptyStr
    solver_settings: dict[str, JsonValue]
    random_seed: int | None = None
    is_mock: bool
