"""App-private project model for the schematic workbench.

The workbench project stores editor layout and user-entered conditions.  It is
not a solver input or a replacement for the frozen DesignSpecification contract.
"""

from __future__ import annotations

import html
import json
from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ComponentKind(StrEnum):
    COMPRESSOR = "compressor"
    GAS_COOLER = "gas_cooler"
    CONDENSER = "condenser"
    EXPANSION_VALVE = "expansion_valve"
    EVAPORATOR = "evaporator"
    PIPE = "pipe"
    RECEIVER = "receiver"
    ACCUMULATOR = "accumulator"
    INTERNAL_HEAT_EXCHANGER = "internal_heat_exchanger"
    FAN = "fan"
    PUMP = "pump"


class PortDirection(StrEnum):
    IN = "in"
    OUT = "out"


class PortType(StrEnum):
    REFRIGERANT = "refrigerant"
    AIR = "air"
    COOLANT = "coolant"


class PortSide(StrEnum):
    LEFT = "left"
    RIGHT = "right"
    TOP = "top"
    BOTTOM = "bottom"


class RoutingMode(StrEnum):
    AUTO = "auto"
    MANUAL = "manual"


class WorkbenchModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class CanvasComponent(WorkbenchModel):
    component_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    kind: ComponentKind
    label: str = Field(min_length=1)
    x: float = Field(ge=0.0, le=100.0)
    y: float = Field(ge=0.0, le=100.0)
    calculation_model: str | None = None
    model_reference: str | None = None
    inlet_side: PortSide | None = None
    outlet_side: PortSide | None = None


class CanvasPort(WorkbenchModel):
    port_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")
    component_id: str = Field(min_length=1)
    name: Literal["inlet", "outlet"]
    direction: PortDirection
    port_type: PortType
    side: PortSide


class CanvasRoutingPoint(WorkbenchModel):
    x: float = Field(ge=0.0, le=100.0)
    y: float = Field(ge=0.0, le=100.0)


class CanvasVisualAnchor(WorkbenchModel):
    """View-only attachment point on a component perimeter."""

    side: PortSide
    offset: float = Field(default=0.5, ge=0.0, le=1.0)


class CanvasEdgeRouting(WorkbenchModel):
    source_port_id: str = Field(min_length=1)
    target_port_id: str = Field(min_length=1)
    mode: RoutingMode = RoutingMode.MANUAL
    points: tuple[CanvasRoutingPoint, ...] = Field(min_length=1)


class CanvasConnection(WorkbenchModel):
    source_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    source_port_id: str = Field(default="", min_length=1)
    target_port_id: str = Field(default="", min_length=1)
    connection_type: PortType = PortType.REFRIGERANT
    state_number: int | None = Field(default=None, ge=1)
    source_anchor: CanvasVisualAnchor | None = None
    target_anchor: CanvasVisualAnchor | None = None

    @model_validator(mode="before")
    @classmethod
    def populate_legacy_port_ids(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        data = dict(value)
        source_id = data.get("source_id")
        target_id = data.get("target_id")
        if isinstance(source_id, str):
            data.setdefault("source_port_id", f"{source_id}.outlet")
        if isinstance(target_id, str):
            data.setdefault("target_port_id", f"{target_id}.inlet")
        data.setdefault("connection_type", PortType.REFRIGERANT)
        return data


class WorkbenchCondition(WorkbenchModel):
    name: str = Field(min_length=1)
    value: float
    unit: str = Field(min_length=1)
    source_type: Literal["USER", "VALIDATION_BASELINE"]
    source_ref: str = Field(min_length=1)


class WorkbenchProject(WorkbenchModel):
    schema_version: Literal[
        "ws-e-workbench-0.1",
        "ws-e-workbench-0.2",
        "ws-e-workbench-0.3",
    ] = "ws-e-workbench-0.3"
    title: str = Field(min_length=1)
    refrigerant: Literal["R744", "R134a", "R410A"] = "R744"
    components: tuple[CanvasComponent, ...]
    connections: tuple[CanvasConnection, ...]
    edge_routing: tuple[CanvasEdgeRouting, ...] = ()
    layout_preset: Literal["refrigeration_cycle"] | None = None
    conditions: tuple[WorkbenchCondition, ...]
    unresolved_inputs: tuple[str, ...] = ()
    source_prompt: str | None = None
    calculation_status: Literal["not_run"] = "not_run"

    @model_validator(mode="after")
    def validate_editor_graph(self) -> Self:
        ids = [component.component_id for component in self.components]
        if len(ids) != len(set(ids)):
            raise ValueError("Component IDs must be unique")
        known = set(ids)
        ports = {
            port.port_id: port
            for component in self.components
            for port in component_ports(component)
        }
        pairs: set[tuple[str, str]] = set()
        used_source_ports: set[str] = set()
        used_target_ports: set[str] = set()
        for connection in self.connections:
            pair = (connection.source_port_id, connection.target_port_id)
            if connection.source_id not in known or connection.target_id not in known:
                raise ValueError("Connection references an unknown component")
            if connection.source_id == connection.target_id:
                raise ValueError("A component cannot connect to itself")
            source_port = ports.get(connection.source_port_id)
            target_port = ports.get(connection.target_port_id)
            if source_port is None or target_port is None:
                raise ValueError("Connection references an unknown port")
            if (
                source_port.component_id != connection.source_id
                or target_port.component_id != connection.target_id
            ):
                raise ValueError("Connection port does not belong to its component")
            if (
                source_port.direction != PortDirection.OUT
                or target_port.direction != PortDirection.IN
            ):
                raise ValueError("Connections must run from OUT to IN")
            if source_port.port_type != target_port.port_type:
                raise ValueError("Connection port types must match")
            if connection.connection_type != source_port.port_type:
                raise ValueError("Connection type must match its ports")
            if pair in pairs:
                raise ValueError("Connections must be unique")
            if connection.source_port_id in used_source_ports:
                raise ValueError("Output ports can have only one connection")
            if connection.target_port_id in used_target_ports:
                raise ValueError("Input ports can have only one connection")
            pairs.add(pair)
            used_source_ports.add(connection.source_port_id)
            used_target_ports.add(connection.target_port_id)
        known_edges = {
            (connection.source_port_id, connection.target_port_id)
            for connection in self.connections
        }
        route_keys: set[tuple[str, str]] = set()
        for route in self.edge_routing:
            key = (route.source_port_id, route.target_port_id)
            if key not in known_edges:
                raise ValueError("Edge routing references an unknown connection")
            if key in route_keys:
                raise ValueError("Edge routing records must be unique")
            if route.mode != RoutingMode.MANUAL:
                raise ValueError("Stored edge routing must use manual mode")
            route_keys.add(key)
        condition_names = [condition.name for condition in self.conditions]
        if len(condition_names) != len(set(condition_names)):
            raise ValueError("Condition names must be unique")
        return self


def _mutable_project_data(project: WorkbenchProject) -> dict[str, Any]:
    """Return mutation data upgraded to the latest app-private editor schema."""
    raw = project.model_dump(mode="json")
    raw["schema_version"] = "ws-e-workbench-0.3"
    by_id = {component.component_id: component for component in project.components}
    for connection in raw["connections"]:
        if (
            connection.get("source_anchor") is not None
            and connection.get("target_anchor") is not None
        ):
            continue
        source = by_id[connection["source_id"]]
        target = by_id[connection["target_id"]]
        source_anchor, target_anchor = natural_connection_anchors(source, target)
        connection["source_anchor"] = source_anchor.model_dump(mode="json")
        connection["target_anchor"] = target_anchor.model_dump(mode="json")
    return raw


def default_port_sides(kind: ComponentKind) -> tuple[PortSide, PortSide]:
    """Return inlet/outlet visual sides without changing their semantics."""
    if kind == ComponentKind.COMPRESSOR:
        return PortSide.BOTTOM, PortSide.TOP
    if kind in {ComponentKind.GAS_COOLER, ComponentKind.CONDENSER}:
        return PortSide.RIGHT, PortSide.LEFT
    if kind == ComponentKind.EXPANSION_VALVE:
        return PortSide.TOP, PortSide.BOTTOM
    if kind == ComponentKind.EVAPORATOR:
        return PortSide.LEFT, PortSide.RIGHT
    return PortSide.LEFT, PortSide.RIGHT


def component_ports(component: CanvasComponent) -> tuple[CanvasPort, CanvasPort]:
    if component.kind == ComponentKind.FAN:
        port_type = PortType.AIR
    elif component.kind == ComponentKind.PUMP:
        port_type = PortType.COOLANT
    else:
        port_type = PortType.REFRIGERANT
    default_inlet_side, default_outlet_side = default_port_sides(component.kind)
    return (
        CanvasPort(
            port_id=f"{component.component_id}.inlet",
            component_id=component.component_id,
            name="inlet",
            direction=PortDirection.IN,
            port_type=port_type,
            side=component.inlet_side or default_inlet_side,
        ),
        CanvasPort(
            port_id=f"{component.component_id}.outlet",
            component_id=component.component_id,
            name="outlet",
            direction=PortDirection.OUT,
            port_type=port_type,
            side=component.outlet_side or default_outlet_side,
        ),
    )


def natural_connection_anchors(
    source: CanvasComponent,
    target: CanvasComponent,
) -> tuple[CanvasVisualAnchor, CanvasVisualAnchor]:
    """Choose facing four-side anchors without changing logical port semantics."""
    dx = target.x - source.x
    dy = target.y - source.y
    if abs(dx) >= abs(dy):
        source_side = PortSide.RIGHT if dx >= 0 else PortSide.LEFT
        target_side = PortSide.LEFT if dx >= 0 else PortSide.RIGHT
    else:
        source_side = PortSide.BOTTOM if dy >= 0 else PortSide.TOP
        target_side = PortSide.TOP if dy >= 0 else PortSide.BOTTOM
    return (
        CanvasVisualAnchor(side=source_side),
        CanvasVisualAnchor(side=target_side),
    )


_GENERIC_MODELS: dict[ComponentKind, str] = {
    ComponentKind.COMPRESSOR: "constant-isentropic-efficiency",
    ComponentKind.GAS_COOLER: "prescribed-outlet-state",
    ComponentKind.CONDENSER: "prescribed-outlet-state",
    ComponentKind.EXPANSION_VALVE: "isenthalpic",
    ComponentKind.EVAPORATOR: "prescribed-pressure-and-outlet-state",
}

_COMPONENT_PARAMETERS: dict[ComponentKind, tuple[str, ...]] = {
    ComponentKind.COMPRESSOR: (
        "compressor_inlet_temperature",
        "high_side_pressure",
        "compressor_isentropic_efficiency",
        "refrigerant_mass_flow",
    ),
    ComponentKind.GAS_COOLER: (
        "high_side_pressure",
        "heat_rejection_outlet_temperature",
        "refrigerant_mass_flow",
    ),
    ComponentKind.CONDENSER: (
        "high_side_pressure",
        "heat_rejection_outlet_temperature",
        "refrigerant_mass_flow",
    ),
    ComponentKind.EXPANSION_VALVE: (
        "high_side_pressure",
        "evaporator_pressure",
        "refrigerant_mass_flow",
    ),
    ComponentKind.EVAPORATOR: (
        "evaporator_pressure",
        "compressor_inlet_temperature",
        "refrigerant_mass_flow",
    ),
}

_CONDITION_ALIASES = {
    "low_side_pressure": "evaporator_pressure",
    "suction_temperature": "compressor_inlet_temperature",
    "gas_cooler_outlet_temperature": "heat_rejection_outlet_temperature",
}


def generic_calculation_model(kind: ComponentKind) -> str | None:
    """Return the product-independent model supported by the baseline cycle."""
    return _GENERIC_MODELS.get(kind)


def component_parameter_names(kind: ComponentKind) -> tuple[str, ...]:
    """Return baseline inputs relevant to a selected component."""
    return _COMPONENT_PARAMETERS.get(kind, ())


def condition_for_parameter(project: WorkbenchProject, name: str) -> WorkbenchCondition | None:
    """Find a canonical baseline parameter while accepting legacy editor aliases."""
    return next(
        (
            condition
            for condition in project.conditions
            if _CONDITION_ALIASES.get(condition.name, condition.name) == name
        ),
        None,
    )


def default_r744_project() -> WorkbenchProject:
    """Return the documented editable P02/P03 comparison-point example."""
    return WorkbenchProject(
        title="R744 기본 증기압축 사이클",
        components=(
            CanvasComponent(
                component_id="compressor",
                kind=ComponentKind.COMPRESSOR,
                label="압축기",
                x=82,
                y=50,
                calculation_model=_GENERIC_MODELS[ComponentKind.COMPRESSOR],
            ),
            CanvasComponent(
                component_id="gas_cooler",
                kind=ComponentKind.GAS_COOLER,
                label="Gas cooler",
                x=50,
                y=16,
                calculation_model=_GENERIC_MODELS[ComponentKind.GAS_COOLER],
            ),
            CanvasComponent(
                component_id="expansion_valve",
                kind=ComponentKind.EXPANSION_VALVE,
                label="팽창밸브",
                x=18,
                y=50,
                calculation_model=_GENERIC_MODELS[ComponentKind.EXPANSION_VALVE],
            ),
            CanvasComponent(
                component_id="evaporator",
                kind=ComponentKind.EVAPORATOR,
                label="증발기",
                x=50,
                y=84,
                calculation_model=_GENERIC_MODELS[ComponentKind.EVAPORATOR],
            ),
        ),
        connections=(
            CanvasConnection(
                source_id="compressor",
                target_id="gas_cooler",
                state_number=2,
                source_anchor=CanvasVisualAnchor(side=PortSide.TOP),
                target_anchor=CanvasVisualAnchor(side=PortSide.RIGHT),
            ),
            CanvasConnection(
                source_id="gas_cooler",
                target_id="expansion_valve",
                state_number=3,
                source_anchor=CanvasVisualAnchor(side=PortSide.LEFT),
                target_anchor=CanvasVisualAnchor(side=PortSide.TOP),
            ),
            CanvasConnection(
                source_id="expansion_valve",
                target_id="evaporator",
                state_number=4,
                source_anchor=CanvasVisualAnchor(side=PortSide.BOTTOM),
                target_anchor=CanvasVisualAnchor(side=PortSide.LEFT),
            ),
            CanvasConnection(
                source_id="evaporator",
                target_id="compressor",
                state_number=1,
                source_anchor=CanvasVisualAnchor(side=PortSide.RIGHT),
                target_anchor=CanvasVisualAnchor(side=PortSide.BOTTOM),
            ),
        ),
        layout_preset="refrigeration_cycle",
        conditions=(
            WorkbenchCondition(
                name="low_side_pressure",
                value=30.0,
                unit="bar(a)",
                source_type="VALIDATION_BASELINE",
                source_ref="P02/P03 cross-check point",
            ),
            WorkbenchCondition(
                name="high_side_pressure",
                value=90.0,
                unit="bar(a)",
                source_type="VALIDATION_BASELINE",
                source_ref="P02/P03 cross-check point",
            ),
            WorkbenchCondition(
                name="suction_temperature",
                value=6.85,
                unit="degC",
                source_type="VALIDATION_BASELINE",
                source_ref="P02/P03 cross-check point",
            ),
            WorkbenchCondition(
                name="gas_cooler_outlet_temperature",
                value=36.85,
                unit="degC",
                source_type="VALIDATION_BASELINE",
                source_ref="P02/P03 cross-check point",
            ),
            WorkbenchCondition(
                name="specified_pipe_length",
                value=0.5,
                unit="meter",
                source_type="USER",
                source_ref="Master Plan section 22 example",
            ),
        ),
    )


def topology_issues(project: WorkbenchProject) -> tuple[str, ...]:
    """Return editor-level completeness issues without making a physics judgment."""
    issues: list[str] = []
    kinds = {component.kind for component in project.components}
    high_side = (
        ComponentKind.GAS_COOLER if project.refrigerant == "R744" else ComponentKind.CONDENSER
    )
    required_kinds = (
        ComponentKind.COMPRESSOR,
        high_side,
        ComponentKind.EXPANSION_VALVE,
        ComponentKind.EVAPORATOR,
    )
    missing = [kind.value for kind in required_kinds if kind not in kinds]
    if missing:
        issues.append("필수 부품 누락: " + ", ".join(missing))
    connected_ports = {
        port_id
        for connection in project.connections
        for port_id in (connection.source_port_id, connection.target_port_id)
    }
    unconnected = [
        component.component_id
        for component in project.components
        if any(port.port_id not in connected_ports for port in component_ports(component))
    ]
    if unconnected:
        issues.append("연결되지 않은 부품: " + ", ".join(unconnected))
    if not project.connections:
        issues.append("연결이 없습니다.")
    return tuple(issues)


def baseline_model_issues(project: WorkbenchProject) -> tuple[str, ...]:
    """Report canvas elements the four-component baseline solver cannot consume."""
    high_side = (
        ComponentKind.GAS_COOLER if project.refrigerant == "R744" else ComponentKind.CONDENSER
    )
    supported = {
        ComponentKind.COMPRESSOR,
        high_side,
        ComponentKind.EXPANSION_VALVE,
        ComponentKind.EVAPORATOR,
    }
    issues: list[str] = []
    for kind in supported:
        matches = [component for component in project.components if component.kind == kind]
        if len(matches) != 1:
            issues.append(f"baseline은 {kind.value} 1개가 필요합니다 (현재 {len(matches)}개).")
            continue
        expected = generic_calculation_model(kind)
        calculation_model = getattr(matches[0], "calculation_model", None) or expected
        if calculation_model != expected:
            issues.append(f"{matches[0].component_id}: 지원 계산 모델은 {expected}입니다.")
    connected_ids = {
        component_id
        for connection in project.connections
        for component_id in (connection.source_id, connection.target_id)
    }
    for component in project.components:
        if component.kind not in supported and component.component_id in connected_ids:
            issues.append(
                f"{component.component_id}: baseline solver에 연결되지 않은 부품 모델입니다."
            )
    by_kind = {component.kind: component.component_id for component in project.components}
    if all(kind in by_kind for kind in supported):
        expected_connections = (
            (by_kind[ComponentKind.COMPRESSOR], by_kind[high_side]),
            (by_kind[high_side], by_kind[ComponentKind.EXPANSION_VALVE]),
            (by_kind[ComponentKind.EXPANSION_VALVE], by_kind[ComponentKind.EVAPORATOR]),
            (by_kind[ComponentKind.EVAPORATOR], by_kind[ComponentKind.COMPRESSOR]),
        )
        actual_connections = {
            (connection.source_id, connection.target_id) for connection in project.connections
        }
        missing_connections = [
            f"{source} → {target}"
            for source, target in expected_connections
            if (source, target) not in actual_connections
        ]
        if missing_connections:
            issues.append("baseline 사이클 연결 누락: " + ", ".join(missing_connections))
    return tuple(issues)


def project_json(project: WorkbenchProject) -> str:
    """Revalidate mutable nested state before exporting a project."""
    validated = WorkbenchProject.model_validate_json(project.model_dump_json())
    return json.dumps(validated.model_dump(mode="json"), ensure_ascii=False, indent=2)


def load_project(data: str | bytes) -> WorkbenchProject:
    return WorkbenchProject.model_validate_json(data)


def add_connection(
    project: WorkbenchProject,
    source_id: str,
    target_id: str,
    *,
    source_port_id: str | None = None,
    target_port_id: str | None = None,
    connection_type: PortType | str = PortType.REFRIGERANT,
    state_number: int | None = None,
    source_anchor: CanvasVisualAnchor | Mapping[str, Any] | None = None,
    target_anchor: CanvasVisualAnchor | Mapping[str, Any] | None = None,
) -> WorkbenchProject:
    if state_number is None:
        state_number = _infer_state_number(project, source_id, target_id)
    if source_anchor is None or target_anchor is None:
        by_id = {component.component_id: component for component in project.components}
        source = by_id.get(source_id)
        target = by_id.get(target_id)
        if source is not None and target is not None:
            inferred_source, inferred_target = natural_connection_anchors(source, target)
            source_anchor = source_anchor or inferred_source
            target_anchor = target_anchor or inferred_target
    raw = _mutable_project_data(project)
    raw["connections"].append(
        {
            "source_id": source_id,
            "target_id": target_id,
            "source_port_id": source_port_id or f"{source_id}.outlet",
            "target_port_id": target_port_id or f"{target_id}.inlet",
            "connection_type": connection_type,
            "state_number": state_number,
            "source_anchor": source_anchor,
            "target_anchor": target_anchor,
        }
    )
    return WorkbenchProject.model_validate(raw)


def _infer_state_number(project: WorkbenchProject, source_id: str, target_id: str) -> int | None:
    by_id = {component.component_id: component.kind for component in project.components}
    source_kind = by_id.get(source_id)
    target_kind = by_id.get(target_id)
    if source_kind is None or target_kind is None:
        return None
    pair = (source_kind, target_kind)
    high_side = (
        ComponentKind.GAS_COOLER if project.refrigerant == "R744" else ComponentKind.CONDENSER
    )
    return {
        (ComponentKind.EVAPORATOR, ComponentKind.COMPRESSOR): 1,
        (ComponentKind.COMPRESSOR, high_side): 2,
        (high_side, ComponentKind.EXPANSION_VALVE): 3,
        (ComponentKind.EXPANSION_VALVE, ComponentKind.EVAPORATOR): 4,
    }.get(pair)


def update_edge_routing(
    project: WorkbenchProject,
    source_port_id: str,
    target_port_id: str,
    points: tuple[CanvasRoutingPoint, ...],
) -> WorkbenchProject:
    """Persist visual waypoints without changing the topology connection."""
    raw = _mutable_project_data(project)
    raw["edge_routing"] = [
        route
        for route in raw["edge_routing"]
        if (route["source_port_id"], route["target_port_id"]) != (source_port_id, target_port_id)
    ]
    if points:
        raw["edge_routing"].append(
            CanvasEdgeRouting(
                source_port_id=source_port_id,
                target_port_id=target_port_id,
                points=points,
            ).model_dump(mode="json")
        )
    return WorkbenchProject.model_validate(raw)


def add_component(
    project: WorkbenchProject,
    kind: ComponentKind,
    *,
    x: float = 50.0,
    y: float = 50.0,
) -> WorkbenchProject:
    """Add an editor component at a validated canvas position."""
    sequence = sum(component.kind == kind for component in project.components) + 1
    component = CanvasComponent(
        component_id=f"{kind.value}_{sequence}",
        kind=kind,
        label=kind.value.replace("_", " ").title(),
        x=x,
        y=y,
        calculation_model=generic_calculation_model(kind),
    )
    raw = _mutable_project_data(project)
    raw["components"].append(component.model_dump(mode="json"))
    return WorkbenchProject.model_validate(raw)


def apply_canvas_action(project: WorkbenchProject, action: Mapping[str, Any]) -> WorkbenchProject:
    """Apply a trusted, revalidated event emitted by the app-private canvas."""
    action_type = action.get("type")
    if action_type == "move":
        component_id = action.get("component_id")
        x = action.get("x")
        y = action.get("y")
        if (
            not isinstance(component_id, str)
            or not isinstance(x, (int, float))
            or not isinstance(y, (int, float))
        ):
            raise ValueError("Invalid move action")
        selected = next(
            (
                component
                for component in project.components
                if component.component_id == component_id
            ),
            None,
        )
        if selected is None:
            raise ValueError(f"Unknown component: {component_id}")
        return update_component(
            project,
            component_id,
            label=selected.label,
            x=float(x),
            y=float(y),
            model_reference=selected.model_reference,
        )
    if action_type == "add":
        raw_kind = action.get("kind")
        x = action.get("x")
        y = action.get("y")
        if (
            not isinstance(raw_kind, str)
            or not isinstance(x, (int, float))
            or not isinstance(y, (int, float))
        ):
            raise ValueError("Invalid add action")
        return add_component(project, ComponentKind(raw_kind), x=float(x), y=float(y))
    if action_type == "remove_component":
        component_id = action.get("component_id")
        if not isinstance(component_id, str):
            raise ValueError("Invalid remove_component action")
        if not any(component.component_id == component_id for component in project.components):
            raise ValueError(f"Unknown component: {component_id}")
        return remove_component(project, component_id)
    if action_type in {"connect", "disconnect"}:
        source_id = action.get("source_id")
        target_id = action.get("target_id")
        source_port_id = action.get("source_port_id")
        target_port_id = action.get("target_port_id")
        connection_type = action.get("connection_type", PortType.REFRIGERANT)
        raw_source_anchor = action.get("source_anchor")
        raw_target_anchor = action.get("target_anchor")
        if (
            not isinstance(source_id, str)
            or not isinstance(target_id, str)
            or (source_port_id is not None and not isinstance(source_port_id, str))
            or (target_port_id is not None and not isinstance(target_port_id, str))
            or not isinstance(connection_type, str)
        ):
            raise ValueError(f"Invalid {action_type} action")
        if action_type == "connect":
            return add_connection(
                project,
                source_id,
                target_id,
                source_port_id=source_port_id,
                target_port_id=target_port_id,
                connection_type=connection_type,
                source_anchor=(
                    CanvasVisualAnchor.model_validate(raw_source_anchor)
                    if raw_source_anchor is not None
                    else None
                ),
                target_anchor=(
                    CanvasVisualAnchor.model_validate(raw_target_anchor)
                    if raw_target_anchor is not None
                    else None
                ),
            )
        return remove_connection(
            project,
            source_id,
            target_id,
            source_port_id=source_port_id,
            target_port_id=target_port_id,
        )
    if action_type in {"route", "reset_route"}:
        source_port_id = action.get("source_port_id")
        target_port_id = action.get("target_port_id")
        if not isinstance(source_port_id, str) or not isinstance(target_port_id, str):
            raise ValueError(f"Invalid {action_type} action")
        if action_type == "reset_route":
            return update_edge_routing(project, source_port_id, target_port_id, ())
        raw_points = action.get("points")
        if not isinstance(raw_points, list):
            raise ValueError("Invalid route action")
        points = tuple(CanvasRoutingPoint.model_validate(point) for point in raw_points)
        return update_edge_routing(project, source_port_id, target_port_id, points)
    raise ValueError("Unknown canvas action")


def remove_connection(
    project: WorkbenchProject,
    source_id: str,
    target_id: str,
    *,
    source_port_id: str | None = None,
    target_port_id: str | None = None,
) -> WorkbenchProject:
    raw = _mutable_project_data(project)
    source_port_id = source_port_id or f"{source_id}.outlet"
    target_port_id = target_port_id or f"{target_id}.inlet"
    raw["connections"] = [
        connection
        for connection in raw["connections"]
        if (connection["source_port_id"], connection["target_port_id"])
        != (source_port_id, target_port_id)
    ]
    raw["edge_routing"] = [
        route
        for route in raw["edge_routing"]
        if (route["source_port_id"], route["target_port_id"]) != (source_port_id, target_port_id)
    ]
    return WorkbenchProject.model_validate(raw)


def update_component(
    project: WorkbenchProject,
    component_id: str,
    *,
    label: str,
    x: float,
    y: float,
    model_reference: str | None,
    calculation_model: str | None = None,
    inlet_side: PortSide | None = None,
    outlet_side: PortSide | None = None,
) -> WorkbenchProject:
    raw = _mutable_project_data(project)
    found = False
    moved = False
    for component in raw["components"]:
        if component["component_id"] == component_id:
            moved = component["x"] != x or component["y"] != y
            component.update(
                label=label,
                x=x,
                y=y,
                model_reference=model_reference or None,
                calculation_model=calculation_model or component.get("calculation_model"),
                inlet_side=inlet_side or component.get("inlet_side"),
                outlet_side=outlet_side or component.get("outlet_side"),
            )
            found = True
    if not found:
        raise ValueError(f"Unknown component: {component_id}")
    if moved:
        changed = WorkbenchProject.model_validate(raw)
        by_id = {component.component_id: component for component in changed.components}
        for connection in raw["connections"]:
            if component_id not in (connection["source_id"], connection["target_id"]):
                continue
            source_anchor, target_anchor = natural_connection_anchors(
                by_id[connection["source_id"]],
                by_id[connection["target_id"]],
            )
            connection["source_anchor"] = source_anchor.model_dump(mode="json")
            connection["target_anchor"] = target_anchor.model_dump(mode="json")
    return WorkbenchProject.model_validate(raw)


def update_condition(
    project: WorkbenchProject,
    name: str,
    *,
    value: float,
    unit: str,
    source_ref: str = "component parameter editor",
) -> WorkbenchProject:
    """Create or replace one explicit user input without supplying other defaults."""
    raw = _mutable_project_data(project)
    replacement = WorkbenchCondition(
        name=name,
        value=value,
        unit=unit,
        source_type="USER",
        source_ref=source_ref,
    ).model_dump(mode="json")
    for index, condition in enumerate(raw["conditions"]):
        canonical = _CONDITION_ALIASES.get(condition["name"], condition["name"])
        if canonical == name:
            raw["conditions"][index] = replacement
            break
    else:
        raw["conditions"].append(replacement)
    raw["unresolved_inputs"] = [item for item in raw["unresolved_inputs"] if item != name]
    return WorkbenchProject.model_validate(raw)


def remove_component(project: WorkbenchProject, component_id: str) -> WorkbenchProject:
    raw = _mutable_project_data(project)
    before = len(raw["components"])
    raw["components"] = [
        component for component in raw["components"] if component["component_id"] != component_id
    ]
    if len(raw["components"]) == before:
        raise ValueError(f"Unknown component: {component_id}")
    raw["connections"] = [
        connection
        for connection in raw["connections"]
        if component_id not in (connection["source_id"], connection["target_id"])
    ]
    live_edges = {
        (connection["source_port_id"], connection["target_port_id"])
        for connection in raw["connections"]
    }
    raw["edge_routing"] = [
        route
        for route in raw["edge_routing"]
        if (route["source_port_id"], route["target_port_id"]) in live_edges
    ]
    return WorkbenchProject.model_validate(raw)


def canvas_html(project: WorkbenchProject) -> str:
    """Build a dependency-free schematic preview; labels are HTML-escaped."""
    by_id = {component.component_id: component for component in project.components}
    lines = []
    for connection in project.connections:
        source = by_id[connection.source_id]
        target = by_id[connection.target_id]
        lines.append(
            f'<line x1="{source.x + 7}" y1="{source.y + 6}" '
            f'x2="{target.x + 7}" y2="{target.y + 6}" />'
        )
    nodes = []
    for component in project.components:
        nodes.append(
            '<div class="node" '
            f'style="left:{component.x}%;top:{component.y}%;">'
            f"<span>{html.escape(component.label)}</span>"
            f"<small>{html.escape(component.kind.value)}</small></div>"
        )
    return (
        """<style>
    .canvas{position:relative;height:510px;border:1px solid #344054;border-radius:14px;
      background:radial-gradient(circle at 20% 20%,#172033,#0b1220 62%);overflow:hidden}
    .canvas svg{position:absolute;inset:0;width:100%;height:100%}
    .canvas line{stroke:#52d3a9;stroke-width:0.7;marker-end:url(#arrow)}
    .node{position:absolute;transform:translate(-50%,-50%);width:132px;padding:13px 10px;
      border:1px solid #68e0bd;border-radius:12px;background:#13243a;color:#f8fafc;
      text-align:center;box-shadow:0 8px 24px #0008;font:600 14px sans-serif}
    .node small{display:block;color:#9fb3c8;font:11px monospace;margin-top:5px}
    .legend{position:absolute;left:16px;bottom:12px;color:#9fb3c8;font:12px sans-serif}
    </style><div class="canvas"><svg viewBox="0 0 100 100" preserveAspectRatio="none">
    <defs><marker id="arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5"
      orient="auto"><path d="M0,0 L7,3.5 L0,7 z" fill="#52d3a9"/></marker></defs>"""
        + "".join(lines)
        + "</svg>"
        + "".join(nodes)
        + ('<div class="legend">Schematic editor preview · 계산 결과가 아닙니다.</div></div>')
    )
