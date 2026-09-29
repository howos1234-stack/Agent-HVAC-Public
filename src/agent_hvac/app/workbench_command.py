"""Deterministic natural-language adapter for the app-private workbench.

The parser recognizes a deliberately small, documented command vocabulary. It
never supplies missing engineering values. Numerical work is delegated to the
existing baseline solver after all required inputs have been provided.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Literal

from pydantic import Field

from agent_hvac.app.design_workbench import (
    CanvasComponent,
    CanvasConnection,
    CanvasVisualAnchor,
    ComponentKind,
    PortSide,
    WorkbenchCondition,
    WorkbenchModel,
    WorkbenchProject,
    baseline_model_issues,
    generic_calculation_model,
    natural_connection_anchors,
)
from agent_hvac.properties.coolprop_backend import CoolPropBackend
from agent_hvac.schemas.design import DesignSpecification
from agent_hvac.schemas.provenance import Parameter, Provenance, SourceType
from agent_hvac.schemas.requirements import HITLMode, UserRequirements
from agent_hvac.schemas.results import SimulationResult
from agent_hvac.solvers.baseline_cycle import BaselineCycleSolver
from agent_hvac.utils.units import MassFlow, Pressure, Quantity, Temperature

SupportedRefrigerant = Literal["R744", "R134a", "R410A"]

_REQUIRED_SOLVER_INPUTS = (
    "evaporator_pressure",
    "high_side_pressure",
    "compressor_inlet_temperature",
    "heat_rejection_outlet_temperature",
    "refrigerant_mass_flow",
    "compressor_isentropic_efficiency",
)

_ALIASES = {
    "low_side_pressure": "evaporator_pressure",
    "suction_temperature": "compressor_inlet_temperature",
    "gas_cooler_outlet_temperature": "heat_rejection_outlet_temperature",
}


def required_solver_input_names() -> tuple[str, ...]:
    """Expose the exact baseline adapter requirements for GUI guidance."""
    return _REQUIRED_SOLVER_INPUTS


_LABELS = {
    ComponentKind.COMPRESSOR: "압축기",
    ComponentKind.GAS_COOLER: "Gas cooler",
    ComponentKind.CONDENSER: "응축기",
    ComponentKind.EXPANSION_VALVE: "팽창밸브",
    ComponentKind.EVAPORATOR: "증발기",
}

_COMPONENT_TERMS = {
    "압축기": ComponentKind.COMPRESSOR,
    "compressor": ComponentKind.COMPRESSOR,
    "응축기": ComponentKind.CONDENSER,
    "condenser": ComponentKind.CONDENSER,
    "가스쿨러": ComponentKind.GAS_COOLER,
    "가스 쿨러": ComponentKind.GAS_COOLER,
    "gas cooler": ComponentKind.GAS_COOLER,
    "gas-cooler": ComponentKind.GAS_COOLER,
    "팽창밸브": ComponentKind.EXPANSION_VALVE,
    "팽창 밸브": ComponentKind.EXPANSION_VALVE,
    "밸브": ComponentKind.EXPANSION_VALVE,
    "expansion valve": ComponentKind.EXPANSION_VALVE,
    "증발기": ComponentKind.EVAPORATOR,
    "evaporator": ComponentKind.EVAPORATOR,
}


class PipeInsertion(WorkbenchModel):
    first: ComponentKind
    second: ComponentKind


class CommandPlan(WorkbenchModel):
    raw_prompt: str = Field(min_length=1)
    refrigerant: SupportedRefrigerant | None
    compressor_model: Literal["constant-isentropic-efficiency"] | None = None
    conditions: tuple[WorkbenchCondition, ...] = ()
    pipe_insertions: tuple[PipeInsertion, ...] = ()
    missing: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


def _first_match(
    prompt: str,
    patterns: Iterable[str],
) -> tuple[float, str] | None:
    for pattern in patterns:
        match = re.search(pattern, prompt, flags=re.IGNORECASE)
        if match:
            return float(match.group("value")), match.group("unit")
    return None


def _condition(name: str, value: float, unit: str, prompt: str) -> WorkbenchCondition:
    return WorkbenchCondition(
        name=name,
        value=value,
        unit=unit,
        source_type="USER",
        source_ref=f"natural-language workbench input: {prompt}",
    )


def _pipe_insertions(prompt: str) -> tuple[PipeInsertion, ...]:
    terms = "|".join(re.escape(term) for term in sorted(_COMPONENT_TERMS, key=len, reverse=True))
    pattern = re.compile(
        rf"(?P<first>{terms})\s*(?:랑|과|와|하고)\s*"
        rf"(?P<second>{terms})\s*사이(?:에)?\s*(?:배관|파이프)(?:을|를)?\s*"
        rf"(?:넣어|추가해|설치해|삽입해)",
        flags=re.IGNORECASE,
    )
    insertions: list[PipeInsertion] = []
    for match in pattern.finditer(prompt):
        first = _COMPONENT_TERMS[match.group("first").lower()]
        second = _COMPONENT_TERMS[match.group("second").lower()]
        insertion = PipeInsertion(first=first, second=second)
        if insertion not in insertions:
            insertions.append(insertion)
    return tuple(insertions)


def interpret_command(prompt: str) -> CommandPlan:
    """Parse supported cycle terms without inventing omitted values."""
    cleaned = " ".join(prompt.strip().split())
    if not cleaned:
        raise ValueError("명령을 입력해 주세요.")

    fluids = []
    for pattern, canonical in (
        (r"(?i)(?<![A-Za-z0-9])R\s*[- ]?134\s*A(?![A-Za-z0-9])", "R134a"),
        (r"(?i)(?<![A-Za-z0-9])R\s*[- ]?410\s*A(?![A-Za-z0-9])", "R410A"),
        (r"(?i)(?<![A-Za-z0-9])(?:R\s*[- ]?744|CO2|CO₂)(?![A-Za-z0-9])", "R744"),
    ):
        if re.search(pattern, cleaned):
            fluids.append(canonical)
    unique_fluids = tuple(dict.fromkeys(fluids))
    refrigerant: SupportedRefrigerant | None = (
        unique_fluids[0] if len(unique_fluids) == 1 else None  # type: ignore[assignment]
    )

    notes: list[str] = []
    missing: list[str] = []
    if not unique_fluids:
        missing.append("refrigerant")
    elif len(unique_fluids) > 1:
        missing.append("refrigerant")
        notes.append("냉매가 둘 이상 감지되었습니다. 하나만 지정해 주세요.")

    model_requested = bool(re.search(r"등엔트로피|isentropic", cleaned, re.IGNORECASE))
    compressor_model: Literal["constant-isentropic-efficiency"] | None = (
        "constant-isentropic-efficiency" if model_requested else None
    )
    if not model_requested:
        notes.append("압축기 모델이 지정되지 않았습니다.")

    parsed: list[WorkbenchCondition] = []
    pipe_insertions = _pipe_insertions(cleaned)
    for insertion in pipe_insertions:
        notes.append(
            f"{insertion.first.value}와 {insertion.second.value} 사이에 배관을 삽입합니다."
        )
    efficiency_match = re.search(
        r"(?:등엔트로피\s*효율|isentropic\s*efficiency)"
        r"(?:\s*모델)?[^0-9+%.\-]{0,24}"
        r"(?P<value>[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+))\s*(?P<percent>%)?",
        cleaned,
        re.IGNORECASE,
    )
    if efficiency_match:
        value = float(efficiency_match.group("value"))
        if efficiency_match.group("percent"):
            value /= 100.0
        if 0.0 < value <= 1.0:
            parsed.append(
                _condition("compressor_isentropic_efficiency", value, "dimensionless", cleaned)
            )
        else:
            notes.append("등엔트로피 효율은 0보다 크고 1 이하여야 합니다.")

    if re.search(r"(?i)(?<![A-Za-z])(?:bar\s*\(\s*g\s*\)|barg)(?![A-Za-z])", cleaned):
        raise ValueError(
            "게이지압 bar(g)/barg는 절대압으로 자동 변환하지 않습니다. "
            "근거가 있는 절대압 bar(a) 또는 bara로 입력해 주세요."
        )
    pressure_unit = (
        r"(?P<unit>bar\s*\(a\)|bara|bar(?!\s*\([^)]*\)|[A-Za-z])|"
        r"MPa(?![A-Za-z])|kPa(?![A-Za-z])|Pa(?![A-Za-z]))"
    )
    temperature_unit = r"(?P<unit>°?C|degC|K)"
    specifications = (
        (
            "evaporator_pressure",
            (
                rf"(?:증발\s*압력|저압(?:측)?(?:\s*압력)?)\s*[:=]?\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*{pressure_unit}",
            ),
        ),
        (
            "high_side_pressure",
            (
                rf"(?:고압(?:측)?(?:\s*압력)?|응축\s*압력|"
                rf"gas[ -]?cooler\s*pressure)\s*[:=]?\s*"
                rf"(?P<value>[0-9]+(?:\.[0-9]+)?)\s*{pressure_unit}",
            ),
        ),
        (
            "compressor_inlet_temperature",
            (
                rf"(?:압축기\s*)?(?:흡입|입구)\s*온도\s*[:=]?\s*(?P<value>-?[0-9]+(?:\.[0-9]+)?)\s*{temperature_unit}",
            ),
        ),
        (
            "heat_rejection_outlet_temperature",
            (
                rf"(?:응축기|gas[ -]?cooler|가스\s*쿨러)\s*출구\s*온도\s*"
                rf"[:=]?\s*(?P<value>-?[0-9]+(?:\.[0-9]+)?)\s*{temperature_unit}",
            ),
        ),
        (
            "refrigerant_mass_flow",
            (
                r"(?:냉매\s*)?(?:질량\s*)?유량\s*[:=]?\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>kg/s|kg/h)",
            ),
        ),
    )
    for name, patterns in specifications:
        match = _first_match(cleaned, patterns)
        if match is not None:
            parsed.append(_condition(name, match[0], match[1], cleaned))

    supplied = {condition.name for condition in parsed}
    missing.extend(name for name in _REQUIRED_SOLVER_INPUTS if name not in supplied)
    if refrigerant is not None:
        high_side = "gas cooler" if refrigerant == "R744" else "condenser"
        notes.append(f"기본 단일단 사이클의 고압 열교환기는 {high_side}로 구성합니다.")
    notes.append("명령에 없는 수치 조건은 생성하지 않았습니다.")
    return CommandPlan(
        raw_prompt=cleaned,
        refrigerant=refrigerant,
        compressor_model=compressor_model,
        conditions=tuple(parsed),
        pipe_insertions=pipe_insertions,
        missing=tuple(dict.fromkeys(missing)),
        notes=tuple(notes),
    )


def project_from_command(plan: CommandPlan) -> WorkbenchProject:
    """Create an editor graph even when solver inputs remain unresolved."""
    if plan.refrigerant is None:
        raise ValueError("캔버스를 구성하려면 냉매를 하나 지정해야 합니다.")
    high_side = ComponentKind.GAS_COOLER if plan.refrigerant == "R744" else ComponentKind.CONDENSER
    components = [
        CanvasComponent(
            component_id="compressor",
            kind=ComponentKind.COMPRESSOR,
            label=_LABELS[ComponentKind.COMPRESSOR],
            x=82,
            y=50,
            calculation_model=(
                plan.compressor_model or generic_calculation_model(ComponentKind.COMPRESSOR)
            ),
        ),
        CanvasComponent(
            component_id=high_side.value,
            kind=high_side,
            label=_LABELS[high_side],
            x=50,
            y=16,
            calculation_model=generic_calculation_model(high_side),
        ),
        CanvasComponent(
            component_id="expansion_valve",
            kind=ComponentKind.EXPANSION_VALVE,
            label=_LABELS[ComponentKind.EXPANSION_VALVE],
            x=18,
            y=50,
            calculation_model=generic_calculation_model(ComponentKind.EXPANSION_VALVE),
        ),
        CanvasComponent(
            component_id="evaporator",
            kind=ComponentKind.EVAPORATOR,
            label=_LABELS[ComponentKind.EVAPORATOR],
            x=50,
            y=84,
            calculation_model=generic_calculation_model(ComponentKind.EVAPORATOR),
        ),
    ]

    def connection(
        source_id: str,
        target_id: str,
        *,
        state_number: int | None = None,
    ) -> CanvasConnection:
        source = next(item for item in components if item.component_id == source_id)
        target = next(item for item in components if item.component_id == target_id)
        canonical_anchors = {
            ("compressor", high_side.value): (PortSide.TOP, PortSide.RIGHT),
            (high_side.value, "expansion_valve"): (PortSide.LEFT, PortSide.TOP),
            ("expansion_valve", "evaporator"): (PortSide.BOTTOM, PortSide.LEFT),
            ("evaporator", "compressor"): (PortSide.RIGHT, PortSide.BOTTOM),
        }
        anchor_sides = canonical_anchors.get((source_id, target_id))
        if anchor_sides is None:
            source_anchor, target_anchor = natural_connection_anchors(source, target)
        else:
            source_anchor = CanvasVisualAnchor(side=anchor_sides[0])
            target_anchor = CanvasVisualAnchor(side=anchor_sides[1])
        return CanvasConnection(
            source_id=source_id,
            target_id=target_id,
            state_number=state_number,
            source_anchor=source_anchor,
            target_anchor=target_anchor,
        )

    connections = [
        connection("compressor", high_side.value, state_number=2),
        connection(high_side.value, "expansion_valve", state_number=3),
        connection("expansion_valve", "evaporator", state_number=4),
        connection("evaporator", "compressor", state_number=1),
    ]
    for index, insertion in enumerate(plan.pipe_insertions, start=1):
        first = next((item for item in components if item.kind == insertion.first), None)
        second = next((item for item in components if item.kind == insertion.second), None)
        if first is None or second is None:
            raise ValueError("요청한 배관 양쪽 부품이 현재 냉매 사이클에 없습니다.")
        direct = next(
            (
                connection
                for connection in connections
                if {connection.source_id, connection.target_id}
                == {first.component_id, second.component_id}
            ),
            None,
        )
        if direct is None:
            raise ValueError("배관은 현재 직접 연결된 두 부품 사이에만 삽입할 수 있습니다.")
        pipe_id = f"pipe_{index}"
        components.append(
            CanvasComponent(
                component_id=pipe_id,
                kind=ComponentKind.PIPE,
                label=f"배관 {index}",
                x=(first.x + second.x) / 2,
                y=(first.y + second.y) / 2,
            )
        )
        position = connections.index(direct)
        connections[position : position + 1] = [
            connection(direct.source_id, pipe_id),
            connection(pipe_id, direct.target_id),
        ]
    return WorkbenchProject(
        title=f"{plan.refrigerant} 기본 증기압축 사이클",
        refrigerant=plan.refrigerant,
        components=tuple(components),
        connections=tuple(connections),
        conditions=plan.conditions,
        unresolved_inputs=plan.missing,
        source_prompt=plan.raw_prompt,
        layout_preset="refrigeration_cycle",
    )


def _canonical_conditions(project: WorkbenchProject) -> dict[str, WorkbenchCondition]:
    return {_ALIASES.get(item.name, item.name): item for item in project.conditions}


def missing_solver_inputs(project: WorkbenchProject) -> tuple[str, ...]:
    supplied = _canonical_conditions(project)
    return tuple(name for name in _REQUIRED_SOLVER_INPUTS if name not in supplied)


def _pressure_si(condition: WorkbenchCondition) -> Pressure:
    unit = condition.unit.replace(" ", "").lower()
    factors = {"pa": 1.0, "kpa": 1e3, "mpa": 1e6, "bar": 1e5, "bar(a)": 1e5, "bara": 1e5}
    if unit not in factors:
        raise ValueError(f"지원하지 않는 압력 단위: {condition.unit}")
    return Pressure(value=condition.value * factors[unit], unit="Pa")


def _temperature_si(condition: WorkbenchCondition) -> Temperature:
    unit = condition.unit.lower().replace("°", "")
    if unit in {"c", "degc"}:
        return Temperature(value=condition.value + 273.15, unit="K")
    if unit == "k":
        return Temperature(value=condition.value, unit="K")
    raise ValueError(f"지원하지 않는 온도 단위: {condition.unit}")


def _mass_flow_si(condition: WorkbenchCondition) -> MassFlow:
    unit = condition.unit.lower()
    if unit == "kg/s":
        return MassFlow(value=condition.value, unit="kg/s")
    if unit == "kg/h":
        return MassFlow(value=condition.value / 3600.0, unit="kg/s")
    raise ValueError(f"지원하지 않는 질량유량 단위: {condition.unit}")


def _efficiency_si(condition: WorkbenchCondition) -> Quantity:
    unit = condition.unit.strip().lower()
    if unit in {"dimensionless", "1"}:
        value = condition.value
    elif unit in {"%", "percent"}:
        value = condition.value / 100.0
    else:
        raise ValueError(f"지원하지 않는 등엔트로피 효율 단위: {condition.unit}")
    if not 0.0 < value <= 1.0:
        raise ValueError("등엔트로피 효율은 0보다 크고 1 이하여야 합니다.")
    return Quantity(value=value, unit="dimensionless")


def design_from_project(project: WorkbenchProject) -> DesignSpecification:
    """Adapt a complete editor project to the frozen baseline solver contract."""
    missing = missing_solver_inputs(project)
    if missing:
        raise ValueError("solver 필수 입력 누락: " + ", ".join(missing))
    model_issues = baseline_model_issues(project)
    if model_issues:
        raise ValueError("baseline 모델 구성 오류: " + " ".join(model_issues))
    values = _canonical_conditions(project)

    def provenance(condition: WorkbenchCondition) -> Provenance:
        source_type = (
            SourceType.USER if condition.source_type == "USER" else SourceType.DESIGN_GUIDELINE
        )
        return Provenance(source_type=source_type, source_ref=condition.source_ref)

    resolved: tuple[Parameter, ...] = (
        Parameter(
            name="evaporator_pressure",
            value=_pressure_si(values["evaporator_pressure"]),
            provenance=provenance(values["evaporator_pressure"]),
        ),
        Parameter(
            name="high_side_pressure",
            value=_pressure_si(values["high_side_pressure"]),
            provenance=provenance(values["high_side_pressure"]),
        ),
        Parameter(
            name="compressor_inlet_temperature",
            value=_temperature_si(values["compressor_inlet_temperature"]),
            provenance=provenance(values["compressor_inlet_temperature"]),
        ),
        Parameter(
            name="heat_rejection_outlet_temperature",
            value=_temperature_si(values["heat_rejection_outlet_temperature"]),
            provenance=provenance(values["heat_rejection_outlet_temperature"]),
        ),
        Parameter(
            name="refrigerant_mass_flow",
            value=_mass_flow_si(values["refrigerant_mass_flow"]),
            provenance=provenance(values["refrigerant_mass_flow"]),
        ),
        Parameter(
            name="compressor_isentropic_efficiency",
            value=_efficiency_si(values["compressor_isentropic_efficiency"]),
            provenance=provenance(values["compressor_isentropic_efficiency"]),
        ),
    )
    user_source = Provenance(
        source_type=SourceType.USER,
        source_ref=project.source_prompt or "workbench project",
    )
    topology_source = Provenance(
        source_type=SourceType.AGENT_ASSUMPTION,
        source_ref="workbench basic single-stage topology parser",
    )
    requirements = UserRequirements(
        raw_prompt=project.source_prompt or "structured workbench input",
        parameters=resolved,
        hitl_mode=HITLMode.REVIEW,
    )
    return DesignSpecification(
        design_id=f"WORKBENCH-{project.refrigerant}",
        requirements=requirements,
        refrigerant=Parameter(
            name="refrigerant", value=project.refrigerant, provenance=user_source
        ),
        topology=Parameter(
            name="topology",
            value="single-stage-baseline",
            provenance=topology_source,
        ),
        boundary_conditions=resolved,
        is_mock=False,
    )


def simulate_project(project: WorkbenchProject) -> SimulationResult:
    """Run the existing deterministic property/cycle service, never GUI math."""
    return BaselineCycleSolver(CoolPropBackend()).simulate(design_from_project(project))
