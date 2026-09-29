"""Report service interface; only the shared package is accepted."""

from typing import Protocol

from agent_hvac.schemas.base import ContractModel, NonEmptyStr
from agent_hvac.schemas.results import FinalDesignPackage


class ReportArtifact(ContractModel):
    path: NonEmptyStr
    media_type: NonEmptyStr
    is_mock: bool


class ReportGenerator(Protocol):
    def generate(self, package: FinalDesignPackage) -> ReportArtifact: ...
