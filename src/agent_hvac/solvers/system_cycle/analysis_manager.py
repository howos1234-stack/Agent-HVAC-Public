"""Bounded synthetic analysis orchestration; never alters physics or fixed requirements."""

from collections.abc import Callable
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from agent_hvac.properties.base import PropertyBackend
from agent_hvac.schemas.base import ContractModel, NonEmptyStr
from agent_hvac.solvers.system_cycle.design_study import (
    DesignCase,
    DesignPoint,
    DesignStudyRequest,
    DesignStudyResult,
    evaluate_design_case,
)

# Canonical SI leaf paths only. Everything not explicitly permitted remains fixed.
ALLOWED_UNITS = {
    "cycle_request.scenario.suction_pressure.value": "Pa",
    "cycle_request.scenario.discharge_pressure.value": "Pa",
    "cycle_request.scenario.evaporator.secondary_mass_flow.value": "kg/s",
    "cycle_request.scenario.condenser.secondary_mass_flow.value": "kg/s",
    "cycle_request.scenario.evaporator.total_thermal_conductance.value": "W/K",
    "cycle_request.scenario.condenser.total_thermal_conductance.value": "W/K",
    "cycle_request.settings.lower_enthalpy.value": "J/kg",
    "cycle_request.settings.upper_enthalpy.value": "J/kg",
    "cycle_request.settings.scan_intervals": "dimensionless",
    "cycle_request.settings.max_iterations": "dimensionless",
}
METADATA = {
    "case_id",
    "family",
    "source_ref",
    "cycle_request.scenario.scenario_id",
    "cycle_request.scenario.source_ref",
}


def _leaves(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        output = {}
        for key, child in value.items():
            output.update(_leaves(child, f"{prefix}.{key}" if prefix else key))
        return output
    return {prefix: value}


class AdjustmentPermission(ContractModel):
    path: NonEmptyStr
    unit: NonEmptyStr
    minimum: float
    maximum: float
    authorization_ref: NonEmptyStr

    @model_validator(mode="after")
    def supported_bound(self) -> Self:
        if self.path not in ALLOWED_UNITS or self.unit != ALLOWED_UNITS[self.path]:
            raise ValueError("unsupported adjustment path or noncanonical SI unit")
        if self.minimum > self.maximum:
            raise ValueError("adjustment minimum must not exceed maximum")
        return self


class AnalysisRequest(ContractModel):
    raw_requirement: NonEmptyStr
    authorization_ref: NonEmptyStr
    study: DesignStudyRequest
    permissions: tuple[AdjustmentPermission, ...] = ()
    max_cases: int = Field(default=20, ge=1, le=100, strict=True)

    @model_validator(mode="after")
    def authorized_cases_only(self) -> Self:
        if len(self.study.cases) > self.max_cases:
            raise ValueError("case budget exceeded; no silent truncation")
        permissions = {p.path: p for p in self.permissions}
        if len(permissions) != len(self.permissions):
            raise ValueError("duplicate adjustment permission")
        baseline = _leaves(self.study.cases[0].model_dump(mode="json"))
        for case in self.study.cases:
            leaves = _leaves(case.model_dump(mode="json"))
            for path in baseline.keys() | leaves.keys():
                if path in METADATA:
                    continue
                if path in permissions:
                    p = permissions[path]
                    value = leaves.get(path)
                    if not isinstance(value, (float, int)) or isinstance(value, bool):
                        raise ValueError(f"missing numeric adjustment: {path}")
                    if not p.minimum <= value <= p.maximum:
                        raise ValueError(f"adjustment outside authorized range: {path}")
                elif leaves.get(path) != baseline.get(path):
                    raise ValueError(f"fixed input changed: {path}")
            if any(path not in leaves for path in permissions):
                raise ValueError("permission does not refer to an existing input")
        return self


Outcome = Literal[
    "TARGET_MET",
    "TARGET_MISMATCH",
    "MODEL_OR_CONSTRAINT_LIMIT",
    "PROPERTY_STATE_FAILURE",
    "NUMERICAL_FAILURE",
    "UNRESOLVED",
]


class CaseAssessment(ContractModel):
    case_id: NonEmptyStr
    outcome: Outcome
    evidence: tuple[str, ...]
    changed_paths: tuple[str, ...]
    next_action: NonEmptyStr


def assess_point(point: DesignPoint, baseline: DesignCase) -> CaseAssessment:
    point = DesignPoint.model_validate(point.model_dump(mode="json"))
    original = _leaves(baseline.model_dump(mode="json"))
    current = _leaves(point.case.model_dump(mode="json"))
    changes = tuple(sorted(k for k in current if k not in METADATA and current[k] != original[k]))
    evidence = [f"cycle reason: {point.cycle.reason}", point.eligibility_reason]
    if point.load_balance_satisfied:
        outcome: Outcome = "TARGET_MET"
        action = "Steady synthetic load match only; room dynamics and products remain unverified."
    elif point.cycle.cycle_converged:
        if point.air_balance_error is not None and abs(point.air_balance_error.value) > 1e-6:
            outcome = "NUMERICAL_FAILURE"
            action = "Inspect independent air energy closure; do not relax its tolerance."
        elif point.cooling_design_eligible:
            outcome = "TARGET_MISMATCH"
            action = "Compare authorized design candidates; do not change the target load to pass."
        else:
            outcome = "MODEL_OR_CONSTRAINT_LIMIT"
            action = "Inspect phase constraints; retain guards and review model applicability."
    else:
        statuses: set[str] = set()
        details: set[str] = set()

        def add(status: str, stage: str | None, message: str) -> None:
            statuses.add(status)
            details.add(f"{status} at {stage}: {message}")

        for sample in point.cycle.history:
            details.add(f"{sample.status} at {sample.failed_stage}: {sample.message}")
            if sample.failed_stage == "pressure-solve" and sample.pressure_history:
                for pressure in sample.pressure_history:
                    add(pressure.status, pressure.failed_stage, pressure.message)
            else:
                add(sample.status, sample.failed_stage, sample.message)
        last = point.cycle.last_evaluation
        if last is not None:
            if last.failed_stage == "pressure-solve" and last.pressure_history:
                for pressure in last.pressure_history:
                    add(pressure.status, pressure.failed_stage, pressure.message)
            else:
                add(last.status, last.failed_stage, last.message)
        evidence.extend(sorted(details))
        if statuses == {"infeasible"}:
            outcome = "MODEL_OR_CONSTRAINT_LIMIT"
            action = (
                "Inspect rejected states; sampled rejection is not a global impossibility proof."
            )
        elif statuses == {"invalid-property-state"}:
            outcome = "PROPERTY_STATE_FAILURE"
            action = "Check property domain and inputs; never substitute another refrigerant."
        elif statuses and statuses <= {"evaluated", "component-numerical-failure"}:
            outcome = "NUMERICAL_FAILURE"
            action = "Use only preauthorized bracket/iteration candidates; keep tolerances fixed."
        else:
            outcome = "UNRESOLVED"
            action = "Inspect mixed or insufficient evidence before assigning a physical cause."
    return CaseAssessment(
        case_id=point.case.case_id,
        outcome=outcome,
        evidence=tuple(evidence),
        changed_paths=changes,
        next_action=action,
    )


class AnalysisReport(ContractModel):
    is_mock: Literal[True] = True
    request: AnalysisRequest
    study_result: DesignStudyResult
    assessments: tuple[CaseAssessment, ...]
    target_found: bool
    closest_eligible_case_id: str | None
    conclusion: Literal["TARGET_FOUND", "NO_TARGET_IN_DECLARED_CASES"]
    requirement_change_applied: Literal[False] = False
    global_infeasibility_proven: Literal[False] = False
    proposals: tuple[str, ...]

    @model_validator(mode="after")
    def consistent_report(self) -> Self:
        if self.study_result.request != self.request.study:
            raise ValueError("result must match the authorized study")
        expected = tuple(
            assess_point(p, self.request.study.cases[0]) for p in self.study_result.points
        )
        found = any(p.load_balance_satisfied for p in self.study_result.points)
        closest = _closest(self.study_result)
        if (
            self.assessments != expected
            or self.target_found != found
            or self.closest_eligible_case_id != closest
            or self.conclusion != ("TARGET_FOUND" if found else "NO_TARGET_IN_DECLARED_CASES")
            or self.proposals != _proposals(found)
        ):
            raise ValueError("report must preserve actual classification, selection and outcome")
        return self


def _closest(result: DesignStudyResult) -> str | None:
    points = [p for p in result.points if p.cooling_design_eligible and p.load_residual is not None]
    if not points:
        return None
    return min(
        points, key=lambda p: abs(p.load_residual.value) if p.load_residual else float("inf")
    ).case.case_id


def _proposals(found: bool) -> tuple[str, ...]:
    if found:
        return ("Validate selected synthetic case independently before product or control use.",)
    return (
        "Review sampled failure evidence; no target found does not prove global infeasibility.",
        "If changing fixed flow, refrigerant, room boundary, load assumption or allowed ranges, "
        "record explicit authorization in a NEW request; preserve the original run.",
        "Model extension or suspected code defects need a separate reproduction and validation; "
        "never remove phase guards or relax convergence tolerances to obtain a match.",
    )


def run_analysis(
    backend: PropertyBackend,
    request: AnalysisRequest,
    *,
    on_point: Callable[[DesignPoint], None] | None = None,
) -> AnalysisReport:
    """Validate ALL candidates before the first call; execute finite cold-start attempts.

    Candidate order is explicit (baseline first, then approved retries/design changes).
    Unexpected errors propagate. No LLM, hidden defaults, infinite retries or code mutation.
    """
    request = AnalysisRequest.model_validate(request.model_dump(mode="json"))
    points = []
    for case in request.study.cases:
        point = evaluate_design_case(backend, case)
        point = DesignPoint.model_validate(point.model_dump(mode="json"))
        if point.case != case:
            raise ValueError("solver returned evidence for a different requested case")
        points.append(point)
        if on_point is not None:
            on_point(point)
    result = DesignStudyResult(request=request.study, points=tuple(points))
    found = any(p.load_balance_satisfied for p in points)
    return AnalysisReport(
        request=request,
        study_result=result,
        assessments=tuple(assess_point(p, request.study.cases[0]) for p in points),
        target_found=found,
        closest_eligible_case_id=_closest(result),
        conclusion="TARGET_FOUND" if found else "NO_TARGET_IN_DECLARED_CASES",
        proposals=_proposals(found),
    )
