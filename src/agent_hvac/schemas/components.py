"""Stable product-contract imports and repository query models."""

from pydantic import Field

from agent_hvac.schemas.base import ContractModel, NonEmptyStr
from agent_hvac.schemas.product_data import (
    AccuracyValidationStatus,
    AutomaticSelectionStatus,
    AxisPhysicalKind,
    AxisRole,
    CanonicalAxisName,
    CanonicalValueName,
    ComponentType,
    DataOrigin,
    DataUseStatus,
    DerivedMethod,
    EnvelopeVertex,
    InterpolationPolicy,
    MapAxis,
    OperatingEnvelope,
    OperatingMode,
    PerformanceMap,
    PerformanceMapKind,
    PerformancePoint,
    PhysicsDerivedDataSource,
    ProductDataSource,
    ProductDataValue,
    ProductRecord,
    ProductSource,
    ProductTopology,
    RatedPoint,
    RecordId,
    ToleranceAbsenceReason,
    ToleranceInfo,
    ToleranceKind,
    ToleranceReference,
    ToleranceSpec,
    UseRestrictionReason,
    WorkbookProductDataSource,
)
from agent_hvac.schemas.provenance import Parameter

__all__ = [
    "AccuracyValidationStatus",
    "AutomaticSelectionStatus",
    "AxisPhysicalKind",
    "AxisRole",
    "CanonicalAxisName",
    "CanonicalValueName",
    "ComponentQuery",
    "ComponentType",
    "DataOrigin",
    "DataUseStatus",
    "DerivedMethod",
    "EnvelopeVertex",
    "InterpolationPolicy",
    "MapAxis",
    "OperatingEnvelope",
    "OperatingMode",
    "PerformanceMap",
    "PerformanceMapKind",
    "PerformancePoint",
    "PhysicsDerivedDataSource",
    "ProductDataSource",
    "ProductDataValue",
    "ProductRecord",
    "ProductSource",
    "ProductTopology",
    "RatedPoint",
    "RecordId",
    "ReloadSummary",
    "ToleranceAbsenceReason",
    "ToleranceInfo",
    "ToleranceKind",
    "ToleranceReference",
    "ToleranceSpec",
    "UseRestrictionReason",
    "WorkbookProductDataSource",
]


class ComponentQuery(ContractModel):
    component_type: ComponentType
    refrigerant: NonEmptyStr
    filters: tuple[Parameter, ...] = ()


class ReloadSummary(ContractModel):
    valid_files: int = Field(ge=0)
    rejected_files: int = Field(ge=0)
    loaded_products: int = Field(ge=0)
    database_version: NonEmptyStr
    errors: tuple[str, ...] = ()
