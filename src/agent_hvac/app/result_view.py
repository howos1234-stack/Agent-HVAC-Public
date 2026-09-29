"""Read-only presentation of validated service artifacts; no solver or rule evaluation."""

from typing import Literal

from agent_hvac.schemas.results import FinalDesignPackage, OptimizationResult, SimulationResult
from agent_hvac.utils.units import Quantity

Artifact = FinalDesignPackage | SimulationResult | OptimizationResult
ArtifactKind = Literal["FinalDesignPackage", "SimulationResult", "OptimizationResult"]


def parse_artifact(data: str | bytes, kind: ArtifactKind) -> Artifact:
    """Use the frozen models, including their cross-field validators."""
    if kind == "FinalDesignPackage":
        return FinalDesignPackage.model_validate_json(data)
    if kind == "SimulationResult":
        return SimulationResult.model_validate_json(data)
    if kind == "OptimizationResult":
        return OptimizationResult.model_validate_json(data)
    raise ValueError(f"Unsupported artifact kind: {kind}")


def export_artifact(artifact: Artifact) -> str:
    """Revalidate even nested mutable values before exporting the original contract."""
    if isinstance(artifact, FinalDesignPackage):
        kind: ArtifactKind = "FinalDesignPackage"
    elif isinstance(artifact, OptimizationResult):
        kind = "OptimizationResult"
    else:
        kind = "SimulationResult"
    return parse_artifact(artifact.model_dump_json(), kind).model_dump_json(indent=2)


def quantity_text(value: Quantity | None) -> str:
    return "미제공" if value is None else f"{value.value:g} {value.unit}"


def state_rows(result: SimulationResult) -> list[dict[str, str | float | None]]:
    return [
        {
            "is_mock": str(result.is_mock).lower(),
            "상태점": name,
            "냉매": state.fluid,
            "p [Pa, absolute]": state.pressure.value,
            "T [K]": state.temperature.value,
            "h [J/kg]": state.enthalpy.value,
            "ρ [kg/m³]": state.density.value,
            "상": state.phase,
            "건도 [dimensionless]": state.vapor_quality,
        }
        for name, state in result.state_points.items()
    ]


def optimization_rows(result: OptimizationResult) -> list[dict[str, str | int | float | bool]]:
    """Preserve service rank order and supplied objective units for presentation."""
    return [
        {
            "rank": rank,
            "design_id": candidate.design.design_id,
            "objective_value": candidate.objective_value.value,
            "objective_unit": candidate.objective_value.unit,
            "solver_status": candidate.simulation.status.value,
            "feasible": candidate.constraints.feasible,
            "is_mock": candidate.design.is_mock,
        }
        for rank, candidate in enumerate(result.ranked_designs, start=1)
    ]
