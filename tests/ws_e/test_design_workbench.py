import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_hvac.app.design_workbench import (
    CanvasComponent,
    CanvasRoutingPoint,
    CanvasVisualAnchor,
    ComponentKind,
    PortSide,
    PortType,
    RoutingMode,
    WorkbenchProject,
    add_component,
    add_connection,
    apply_canvas_action,
    baseline_model_issues,
    canvas_html,
    component_parameter_names,
    component_ports,
    condition_for_parameter,
    default_r744_project,
    load_project,
    natural_connection_anchors,
    project_json,
    remove_component,
    remove_connection,
    topology_issues,
    update_component,
    update_condition,
    update_edge_routing,
)
from agent_hvac.app.workbench_canvas_component import (
    WORKBENCH_CANVAS_CSS,
    WORKBENCH_CANVAS_HTML,
    WORKBENCH_CANVAS_JS,
)
from agent_hvac.app.workbench_command import (
    design_from_project,
    interpret_command,
    missing_solver_inputs,
    project_from_command,
    required_solver_input_names,
    simulate_project,
)
from agent_hvac.schemas.results import SolverStatus


def test_default_project_is_a_complete_editor_graph_and_round_trips() -> None:
    project = default_r744_project()

    assert project.refrigerant == "R744"
    assert project.schema_version == "ws-e-workbench-0.3"
    assert project.calculation_status == "not_run"
    assert topology_issues(project) == ()
    assert baseline_model_issues(project) == ()
    assert all(component.calculation_model is not None for component in project.components)
    assert all(connection.source_port_id.endswith(".outlet") for connection in project.connections)
    assert all(connection.target_port_id.endswith(".inlet") for connection in project.connections)
    assert project.layout_preset == "refrigeration_cycle"
    assert {
        component.component_id: (component.x, component.y) for component in project.components
    } == {
        "compressor": (82.0, 50.0),
        "gas_cooler": (50.0, 16.0),
        "expansion_valve": (18.0, 50.0),
        "evaporator": (50.0, 84.0),
    }
    assert {
        (connection.source_id, connection.target_id): (
            connection.source_anchor.side,
            connection.target_anchor.side,
        )
        for connection in project.connections
        if connection.source_anchor is not None and connection.target_anchor is not None
    } == {
        ("compressor", "gas_cooler"): (PortSide.TOP, PortSide.RIGHT),
        ("gas_cooler", "expansion_valve"): (PortSide.LEFT, PortSide.TOP),
        ("expansion_valve", "evaporator"): (PortSide.BOTTOM, PortSide.LEFT),
        ("evaporator", "compressor"): (PortSide.RIGHT, PortSide.BOTTOM),
    }
    assert {
        (connection.source_id, connection.target_id): connection.state_number
        for connection in project.connections
    } == {
        ("evaporator", "compressor"): 1,
        ("compressor", "gas_cooler"): 2,
        ("gas_cooler", "expansion_valve"): 3,
        ("expansion_valve", "evaporator"): 4,
    }
    assert load_project(project_json(project)) == project


def test_default_port_visual_sides_do_not_change_semantic_direction() -> None:
    project = default_r744_project()
    by_id = {component.component_id: component for component in project.components}

    assert [(port.direction, port.side) for port in component_ports(by_id["compressor"])] == [
        ("in", PortSide.BOTTOM),
        ("out", PortSide.TOP),
    ]
    assert [(port.direction, port.side) for port in component_ports(by_id["gas_cooler"])] == [
        ("in", PortSide.RIGHT),
        ("out", PortSide.LEFT),
    ]
    assert [(port.direction, port.side) for port in component_ports(by_id["expansion_valve"])] == [
        ("in", PortSide.TOP),
        ("out", PortSide.BOTTOM),
    ]
    assert [(port.direction, port.side) for port in component_ports(by_id["evaporator"])] == [
        ("in", PortSide.LEFT),
        ("out", PortSide.RIGHT),
    ]


def test_manual_edge_routing_round_trips_without_changing_topology() -> None:
    project = default_r744_project()
    topology = project.connections
    points = (
        CanvasRoutingPoint(x=73.0, y=27.0),
        CanvasRoutingPoint(x=73.0, y=16.0),
    )

    routed = update_edge_routing(
        project,
        "compressor.outlet",
        "gas_cooler.inlet",
        points,
    )

    assert routed.connections == topology
    assert len(routed.edge_routing) == 1
    assert routed.edge_routing[0].mode == RoutingMode.MANUAL
    assert routed.edge_routing[0].points == points
    assert load_project(project_json(routed)) == routed

    reset = apply_canvas_action(
        routed,
        {
            "type": "reset_route",
            "source_port_id": "compressor.outlet",
            "target_port_id": "gas_cooler.inlet",
        },
    )
    assert reset.connections == topology
    assert reset.edge_routing == ()


def test_dynamic_visual_anchors_are_separate_from_logical_ports_and_round_trip() -> None:
    project = default_r744_project()
    without = remove_connection(project, "compressor", "gas_cooler")
    connected = add_connection(
        without,
        "compressor",
        "gas_cooler",
        source_anchor=CanvasVisualAnchor(side=PortSide.LEFT, offset=0.35),
        target_anchor=CanvasVisualAnchor(side=PortSide.BOTTOM, offset=0.65),
    )
    edge = connected.connections[-1]

    assert edge.source_port_id == "compressor.outlet"
    assert edge.target_port_id == "gas_cooler.inlet"
    assert edge.source_anchor == CanvasVisualAnchor(side=PortSide.LEFT, offset=0.35)
    assert edge.target_anchor == CanvasVisualAnchor(side=PortSide.BOTTOM, offset=0.65)
    assert load_project(project_json(connected)) == connected

    action_connected = apply_canvas_action(
        without,
        {
            "type": "connect",
            "source_id": "compressor",
            "target_id": "gas_cooler",
            "source_port_id": "compressor.outlet",
            "target_port_id": "gas_cooler.inlet",
            "connection_type": "refrigerant",
            "source_anchor": {"side": "top", "offset": 0.4},
            "target_anchor": {"side": "bottom", "offset": 0.6},
        },
    )
    action_edge = action_connected.connections[-1]
    assert action_edge.source_anchor == CanvasVisualAnchor(side=PortSide.TOP, offset=0.4)
    assert action_edge.target_anchor == CanvasVisualAnchor(side=PortSide.BOTTOM, offset=0.6)

    with pytest.raises(ValidationError):
        CanvasVisualAnchor(side=PortSide.LEFT, offset=1.1)


def test_component_move_recomputes_facing_anchors_but_preserves_manual_waypoints() -> None:
    project = update_edge_routing(
        default_r744_project(),
        "compressor.outlet",
        "gas_cooler.inlet",
        (CanvasRoutingPoint(x=75.0, y=30.0),),
    )
    compressor = next(item for item in project.components if item.component_id == "compressor")
    moved = update_component(
        project,
        "compressor",
        label=compressor.label,
        x=25.0,
        y=16.0,
        model_reference=compressor.model_reference,
    )
    edge = next(item for item in moved.connections if item.source_id == "compressor")

    assert (edge.source_anchor.side, edge.target_anchor.side) == (
        PortSide.RIGHT,
        PortSide.LEFT,
    )
    assert moved.edge_routing == project.edge_routing
    source = next(item for item in moved.components if item.component_id == "compressor")
    target = next(item for item in moved.components if item.component_id == "gas_cooler")
    assert natural_connection_anchors(source, target) == (
        edge.source_anchor,
        edge.target_anchor,
    )


def test_route_actions_reject_unknown_edges_and_cleanup_deleted_edges() -> None:
    project = default_r744_project()
    action = {
        "type": "route",
        "source_port_id": "compressor.outlet",
        "target_port_id": "gas_cooler.inlet",
        "points": [{"x": 71.0, "y": 25.0}],
    }
    routed = apply_canvas_action(project, action)

    disconnected = remove_connection(
        routed,
        "compressor",
        "gas_cooler",
        source_port_id="compressor.outlet",
        target_port_id="gas_cooler.inlet",
    )
    assert disconnected.edge_routing == ()

    with pytest.raises(ValidationError, match="unknown connection"):
        apply_canvas_action(disconnected, action)
    with pytest.raises(ValidationError):
        apply_canvas_action(
            project,
            {
                **action,
                "points": [{"x": 101.0, "y": 25.0}],
            },
        )


def test_unknown_connection_and_duplicate_condition_are_rejected() -> None:
    raw = default_r744_project().model_dump(mode="json")
    raw["connections"][0]["target_id"] = "missing"
    with pytest.raises(ValidationError, match="unknown component"):
        WorkbenchProject.model_validate(raw)

    raw = default_r744_project().model_dump(mode="json")
    raw["conditions"].append(raw["conditions"][0])
    with pytest.raises(ValidationError, match="Condition names must be unique"):
        WorkbenchProject.model_validate(raw)


def test_each_canvas_port_accepts_only_one_connection() -> None:
    project = add_component(default_r744_project(), ComponentKind.ACCUMULATOR, x=50, y=50)

    with pytest.raises(ValidationError, match="Output ports can have only one connection"):
        add_connection(project, "compressor", "accumulator_1")

    with pytest.raises(ValidationError, match="Input ports can have only one connection"):
        add_connection(project, "accumulator_1", "gas_cooler")


def test_missing_and_unconnected_components_are_reported_without_physics_claim() -> None:
    raw = default_r744_project().model_dump(mode="json")
    raw["components"] = [
        component for component in raw["components"] if component["kind"] != "evaporator"
    ]
    raw["connections"] = [
        connection for connection in raw["connections"] if "evaporator" not in connection.values()
    ]
    project = WorkbenchProject.model_validate(raw)

    assert any("evaporator" in issue for issue in topology_issues(project))


def test_canvas_escapes_user_visible_labels() -> None:
    project = default_r744_project()
    raw = project.model_dump(mode="json")
    raw["components"][0]["label"] = '<img src=x onerror="alert(1)">'
    changed = WorkbenchProject.model_validate(raw)

    output = canvas_html(changed)

    assert '<img src=x onerror="alert(1)">' not in output
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in output


def test_component_identifier_and_extra_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        CanvasComponent(
            component_id="../escape",
            kind=ComponentKind.PIPE,
            label="pipe",
            x=10,
            y=10,
        )
    raw = json.loads(project_json(default_r744_project()))
    raw["unexpected"] = True
    with pytest.raises(ValidationError):
        load_project(json.dumps(raw))


def test_component_layout_and_connection_edits_round_trip() -> None:
    project = default_r744_project()
    changed = update_component(
        project,
        "compressor",
        label="Synthetic compressor",
        x=20,
        y=30,
        model_reference="CD 360M",
    )
    compressor = next(
        component for component in changed.components if component.component_id == "compressor"
    )
    assert (compressor.label, compressor.x, compressor.y, compressor.model_reference) == (
        "Synthetic compressor",
        20,
        30,
        "CD 360M",
    )

    without = remove_connection(changed, "compressor", "gas_cooler")
    restored = add_connection(without, "compressor", "gas_cooler")
    assert len(restored.connections) == len(changed.connections)
    with pytest.raises(ValidationError, match="Connections must be unique"):
        add_connection(restored, "compressor", "gas_cooler")

    removed = remove_component(restored, "gas_cooler")
    assert all(component.component_id != "gas_cooler" for component in removed.components)
    assert all(
        "gas_cooler" not in connection.model_dump().values() for connection in removed.connections
    )


def test_editing_a_legacy_project_upgrades_the_app_private_schema() -> None:
    raw = default_r744_project().model_dump(mode="json")
    raw["schema_version"] = "ws-e-workbench-0.1"
    raw["connections"] = [
        {
            key: value
            for key, value in connection.items()
            if key not in {"source_anchor", "target_anchor"}
        }
        for connection in raw["connections"]
    ]
    legacy = WorkbenchProject.model_validate(raw)
    compressor = next(item for item in legacy.components if item.component_id == "compressor")

    edited = update_component(
        legacy,
        "compressor",
        label=compressor.label,
        x=80.0,
        y=50.0,
        model_reference=None,
    )

    assert edited.schema_version == "ws-e-workbench-0.3"
    assert all(edge.source_anchor is not None for edge in edited.connections)
    assert all(edge.target_anchor is not None for edge in edited.connections)


def test_canvas_actions_add_and_move_components_with_strict_revalidation() -> None:
    project = default_r744_project()
    added = apply_canvas_action(
        project,
        {"type": "add", "kind": "receiver", "x": 55.25, "y": 64.5},
    )
    receiver = next(component for component in added.components if component.kind == "receiver")
    assert (receiver.component_id, receiver.x, receiver.y) == ("receiver_1", 55.25, 64.5)

    moved = apply_canvas_action(
        added,
        {"type": "move", "component_id": receiver.component_id, "x": 61.0, "y": 70.0},
    )
    moved_receiver = next(
        component
        for component in moved.components
        if component.component_id == receiver.component_id
    )
    assert (moved_receiver.x, moved_receiver.y) == (61.0, 70.0)
    with pytest.raises(ValidationError):
        apply_canvas_action(
            moved,
            {"type": "move", "component_id": receiver.component_id, "x": 101.0, "y": 20.0},
        )
    removed = apply_canvas_action(
        moved,
        {"type": "remove_component", "component_id": receiver.component_id},
    )
    assert all(component.component_id != receiver.component_id for component in removed.components)
    with pytest.raises(ValueError, match="Unknown canvas action"):
        apply_canvas_action(moved, {"type": "delete"})

    disconnected = apply_canvas_action(
        moved,
        {"type": "disconnect", "source_id": "compressor", "target_id": "gas_cooler"},
    )
    reconnected = apply_canvas_action(
        disconnected,
        {"type": "connect", "source_id": "compressor", "target_id": "gas_cooler"},
    )
    assert len(reconnected.connections) == len(moved.connections)


def test_new_component_ports_connect_to_persisted_port_topology() -> None:
    project = add_component(default_r744_project(), ComponentKind.ACCUMULATOR, x=60, y=70)
    accumulator = project.components[-1]
    ports = component_ports(accumulator)

    assert [port.port_id for port in ports] == [
        "accumulator_1.inlet",
        "accumulator_1.outlet",
    ]
    assert all(port.port_type == PortType.REFRIGERANT for port in ports)

    disconnected = remove_connection(
        project,
        "evaporator",
        "compressor",
        source_port_id="evaporator.outlet",
        target_port_id="compressor.inlet",
    )
    connected = apply_canvas_action(
        disconnected,
        {
            "type": "connect",
            "source_id": "evaporator",
            "target_id": "accumulator_1",
            "source_port_id": "evaporator.outlet",
            "target_port_id": "accumulator_1.inlet",
            "connection_type": "refrigerant",
        },
    )
    edge = connected.connections[-1]
    assert edge.source_port_id == "evaporator.outlet"
    assert edge.target_port_id == "accumulator_1.inlet"
    assert edge.connection_type == PortType.REFRIGERANT
    assert "accumulator_1" in " ".join(topology_issues(connected))

    complete = add_connection(connected, "accumulator_1", "compressor")
    assert "accumulator_1" not in " ".join(topology_issues(complete))


@pytest.mark.parametrize(
    ("source_port_id", "target_port_id", "message"),
    [
        ("compressor.inlet", "gas_cooler.inlet", "OUT to IN"),
        ("compressor.outlet", "gas_cooler.outlet", "OUT to IN"),
        ("compressor.outlet", "fan_1.inlet", "port types must match"),
    ],
)
def test_port_direction_and_type_validation_rejects_invalid_edges(
    source_port_id: str,
    target_port_id: str,
    message: str,
) -> None:
    project = add_component(default_r744_project(), ComponentKind.FAN, x=80, y=80)
    source_id = source_port_id.split(".", maxsplit=1)[0]
    target_id = target_port_id.split(".", maxsplit=1)[0]

    with pytest.raises(ValidationError, match=message):
        add_connection(
            project,
            source_id,
            target_id,
            source_port_id=source_port_id,
            target_port_id=target_port_id,
        )


def test_component_addition_uses_deterministic_ids_and_canvas_assets_show_connections() -> None:
    app_source = (
        Path(__file__).parents[2] / "src/agent_hvac/app/design_workbench_app.py"
    ).read_text(encoding="utf-8")
    project = add_component(default_r744_project(), ComponentKind.PIPE, x=25, y=30)
    project = add_component(project, ComponentKind.PIPE, x=35, y=40)

    assert [component.component_id for component in project.components[-2:]] == ["pipe_1", "pipe_2"]
    assert "setTriggerValue('action'" in WORKBENCH_CANVAS_JS
    assert "marker-end:url(#wb-arrow)" in WORKBENCH_CANVAS_CSS
    assert "application/x-agent-hvac-kind" in WORKBENCH_CANVAS_JS
    assert "event.ctrlKey||event.metaKey" in WORKBENCH_CANVAS_JS
    assert "emit({type:event.shiftKey?'redo':'undo'})" in WORKBENCH_CANVAS_JS
    assert "emit({type:'redo'})" in WORKBENCH_CANVAS_JS
    assert "type:'connect'" in WORKBENCH_CANVAS_JS
    assert "type:'disconnect'" in WORKBENCH_CANVAS_JS
    assert "orthogonalVertices" in WORKBENCH_CANVAS_JS
    assert "pathFromVertices" in WORKBENCH_CANVAS_JS
    assert "reserveLane" in WORKBENCH_CANVAS_JS
    assert "const usedLanes=[]" in WORKBENCH_CANVAS_JS
    assert "Math.abs(lane-candidate)>=gap-.01" in WORKBENCH_CANVAS_JS
    assert "polylineMidpoint" in WORKBENCH_CANVAS_JS
    assert "wb-waypoint" in WORKBENCH_CANVAS_HTML
    assert 'aria-label="HVAC connections"' in WORKBENCH_CANVAS_HTML
    assert "Routing waypoint" in WORKBENCH_CANVAS_JS
    assert "ArrowLeft:[-1,0]" in WORKBENCH_CANVAS_JS
    assert "Select connection ${edge.source_id} to ${edge.target_id}" in WORKBENCH_CANVAS_JS
    assert "type:'route'" in WORKBENCH_CANVAS_JS
    assert "type:'reset_route'" in WORKBENCH_CANVAS_JS
    assert "['left','right','top','bottom'].map" in WORKBENCH_CANVAS_JS
    assert "visual.dataset.side=side" in WORKBENCH_CANVAS_JS
    assert "marker-end','url(#wb-arrow)'" in WORKBENCH_CANVAS_JS
    assert 'markerUnits="userSpaceOnUse"' in WORKBENCH_CANVAS_HTML
    assert "content:attr(data-label)" not in WORKBENCH_CANVAS_CSS
    assert "is-highlighted" in WORKBENCH_CANVAS_CSS
    assert "wb-preview-wire" in WORKBENCH_CANVAS_JS
    assert ".wb-port.is-available" in WORKBENCH_CANVAS_CSS
    assert ".wb-port-dual" in WORKBENCH_CANVAS_CSS
    assert "--canvas-bg:#f8fafc" in WORKBENCH_CANVAS_CSS
    assert "radial-gradient(circle,#cbd5e1 1px,transparent 1.2px)" in WORKBENCH_CANVAS_CSS
    assert ".wb-node.is-selected" in WORKBENCH_CANVAS_CSS
    assert ".wb-node-icon svg" in WORKBENCH_CANVAS_CSS
    assert "item.component_id===data.selected_component_id" in WORKBENCH_CANVAS_JS
    assert "icon.innerHTML=icons[item.kind]" in WORKBENCH_CANVAS_JS
    assert "BUILD HVAC SYSTEM" in WORKBENCH_CANVAS_HTML
    assert "path.setAttribute('stroke','#64748b')" in WORKBENCH_CANVAS_JS
    assert "document.elementFromPoint" in WORKBENCH_CANVAS_JS
    assert "root.elementFromPoint?." in WORKBENCH_CANVAS_JS
    assert "visual.setPointerCapture" in WORKBENCH_CANVAS_JS
    assert "inputPortFor(target.dataset.componentId)" in WORKBENCH_CANVAS_JS
    assert "connectedPortIds.has(targetPort.port_id)" in WORKBENCH_CANVAS_JS
    assert "connectedPortIds.has(outputPort.port_id)" in WORKBENCH_CANVAS_JS
    assert "source_port_id:connectionSource.port_id" in WORKBENCH_CANVAS_JS
    assert "source_anchor:connectionSource.visual_anchor" in WORKBENCH_CANVAS_JS
    assert "target_anchor:{side:target.dataset.side,offset:.5}" in WORKBENCH_CANVAS_JS
    assert "['Delete','Backspace']" in WORKBENCH_CANVAS_JS
    assert "setZoom" in WORKBENCH_CANVAS_JS
    assert "panSession" in WORKBENCH_CANVAS_JS
    assert "RIGHT_DRAG_THRESHOLD=6" in WORKBENCH_CANVAS_JS
    assert "MAGNETIC_RADIUS=44" in WORKBENCH_CANVAS_JS
    assert "DOUBLE_CLICK_WINDOW=500" in WORKBENCH_CANVAS_JS
    assert "now-nodeClickState.at<=DOUBLE_CLICK_WINDOW" in WORKBENCH_CANVAS_JS
    assert (
        "nodeClickState=null;emit({type:'select',component_id:item.component_id,open_properties:true})"
        in WORKBENCH_CANVAS_JS
    )
    assert "return dedupe([{x:laneX,y:source.y},{x:laneX,y:target.y}])" in WORKBENCH_CANVAS_JS
    assert "return dedupe([{x:source.x,y:laneY},{x:target.x,y:laneY}])" in WORKBENCH_CANVAS_JS
    assert "limitedManualControlPoints" in WORKBENCH_CANVAS_JS
    assert "points.slice(0,2)" in WORKBENCH_CANVAS_JS
    assert "emitRoute(edge,[pointerPoint(event)])" in WORKBENCH_CANVAS_JS
    assert "sourceStub" not in WORKBENCH_CANVAS_JS
    assert "targetStub" not in WORKBENCH_CANVAS_JS
    assert "nearestMagneticTarget" in WORKBENCH_CANVAS_JS
    assert "event.button===2" in WORKBENCH_CANVAS_JS
    assert "source_anchor:rightConnect.sourceAnchor" in WORKBENCH_CANVAS_JS
    assert "nearestNodeSide(candidate.node,event)" in WORKBENCH_CANVAS_JS
    assert "type:'select'" in WORKBENCH_CANVAS_JS
    assert "open_properties:true" in WORKBENCH_CANVAS_JS
    assert "event.key==='Escape'" in WORKBENCH_CANVAS_JS
    assert 'default={"action": None}' not in app_source
    assert "on_action_change=lambda: None" in app_source
    assert "workbench-interactive-canvas-body-connect-v8" in app_source
    assert "type:'remove_component'" in WORKBENCH_CANVAS_JS
    assert "입구 포트 화면 위치" not in app_source
    assert "출구 포트 화면 위치" not in app_source


def test_natural_language_command_builds_graph_and_preserves_missing_values() -> None:
    plan = interpret_command("R134a 냉동사이클을 구성하고 압축기에 등엔트로피 효율 모델을 적용해줘")

    assert plan.refrigerant == "R134a"
    assert plan.compressor_model == "constant-isentropic-efficiency"
    assert "compressor_isentropic_efficiency" in plan.missing
    project = project_from_command(plan)
    assert project.refrigerant == "R134a"
    assert {component.kind for component in project.components} == {
        ComponentKind.COMPRESSOR,
        ComponentKind.CONDENSER,
        ComponentKind.EXPANSION_VALVE,
        ComponentKind.EVAPORATOR,
    }
    compressor = next(
        component for component in project.components if component.kind == ComponentKind.COMPRESSOR
    )
    assert compressor.calculation_model == "constant-isentropic-efficiency"
    assert compressor.model_reference is None
    assert "compressor_isentropic_efficiency" in missing_solver_inputs(project)
    with pytest.raises(ValueError, match="필수 입력 누락"):
        design_from_project(project)


def test_command_help_uses_exact_baseline_solver_requirements() -> None:
    assert required_solver_input_names() == (
        "evaporator_pressure",
        "high_side_pressure",
        "compressor_inlet_temperature",
        "heat_rejection_outlet_temperature",
        "refrigerant_mass_flow",
        "compressor_isentropic_efficiency",
    )


def test_natural_language_inserts_pipe_between_named_adjacent_components() -> None:
    plan = interpret_command(
        "R134a 기본 냉동사이클을 구성해줘. 응축기랑 팽창밸브 사이에 배관 넣어줘"
    )

    assert len(plan.pipe_insertions) == 1
    assert plan.pipe_insertions[0].first == ComponentKind.CONDENSER
    assert plan.pipe_insertions[0].second == ComponentKind.EXPANSION_VALVE
    project = project_from_command(plan)
    pipe = next(
        component for component in project.components if component.kind == ComponentKind.PIPE
    )
    assert (pipe.component_id, pipe.label, pipe.x, pipe.y) == ("pipe_1", "배관 1", 34.0, 33.0)
    pairs = {(item.source_id, item.target_id) for item in project.connections}
    assert ("condenser", "expansion_valve") not in pairs
    assert ("condenser", "pipe_1") in pairs
    assert ("pipe_1", "expansion_valve") in pairs
    assert any("배관을 삽입" in note for note in plan.notes)
    assert any("pipe_1" in issue for issue in baseline_model_issues(project))


def test_natural_language_accepts_compact_valve_and_insert_wording() -> None:
    plan = interpret_command(
        "R134a 기본 냉동사이클을 구성하고 압축기에 등엔트로피 효율 0.75 모델을 적용해줘. "
        "증발압력 3 bar(a), 고압 12 bar(a), 흡입온도 10°C, 응축기 출구온도 35°C, "
        "냉매 질량유량 0.05 kg/s. 응축기랑 밸브사이에 배관삽입해줘"
    )

    project = project_from_command(plan)

    assert plan.missing == ()
    assert len(plan.pipe_insertions) == 1
    assert {item.component_id for item in project.components} >= {"condenser", "pipe_1"}
    assert ("condenser", "pipe_1") in {
        (item.source_id, item.target_id) for item in project.connections
    }


def test_natural_language_rejects_pipe_between_nonadjacent_components() -> None:
    plan = interpret_command("R134a 냉동사이클을 구성하고 압축기와 팽창밸브 사이에 배관을 추가해줘")

    with pytest.raises(ValueError, match="직접 연결된 두 부품"):
        project_from_command(plan)


def test_component_parameters_complete_a_product_free_cycle() -> None:
    project = project_from_command(
        interpret_command("R134a 냉동사이클을 구성하고 일반 부품 모델을 사용해줘")
    )
    values = (
        ("evaporator_pressure", 3.0, "bar(a)"),
        ("high_side_pressure", 12.0, "bar(a)"),
        ("compressor_inlet_temperature", 10.0, "degC"),
        ("heat_rejection_outlet_temperature", 35.0, "degC"),
        ("refrigerant_mass_flow", 0.05, "kg/s"),
        ("compressor_isentropic_efficiency", 0.75, "dimensionless"),
    )
    for name, value, unit in values:
        project = update_condition(project, name, value=value, unit=unit)

    result = simulate_project(project)

    assert missing_solver_inputs(project) == ()
    assert baseline_model_issues(project) == ()
    assert all(component.model_reference is None for component in project.components)
    assert result.status == SolverStatus.CONVERGED
    assert result.cop == pytest.approx(3.9147244816576934)
    compressor_parameters = component_parameter_names(ComponentKind.COMPRESSOR)
    assert "compressor_isentropic_efficiency" in compressor_parameters


def _manually_connected_r134a_project() -> WorkbenchProject:
    project = WorkbenchProject(
        title="마우스로 구성한 R134a 사이클",
        refrigerant="R134a",
        components=(),
        connections=(),
        conditions=(),
        source_prompt=None,
        layout_preset="refrigeration_cycle",
    )
    for kind in (
        ComponentKind.COMPRESSOR,
        ComponentKind.CONDENSER,
        ComponentKind.EXPANSION_VALVE,
        ComponentKind.EVAPORATOR,
    ):
        project = add_component(project, kind)
    for source, target in (
        ("compressor_1", "condenser_1"),
        ("condenser_1", "expansion_valve_1"),
        ("expansion_valve_1", "evaporator_1"),
        ("evaporator_1", "compressor_1"),
    ):
        project = add_connection(project, source, target)
    return project


def test_manually_connected_canvas_with_generated_ids_runs_baseline() -> None:
    project = _manually_connected_r134a_project()
    for name, value, unit in (
        ("evaporator_pressure", 3.0, "bar(a)"),
        ("high_side_pressure", 12.0, "bar(a)"),
        ("compressor_inlet_temperature", 10.0, "degC"),
        ("heat_rejection_outlet_temperature", 35.0, "degC"),
        ("refrigerant_mass_flow", 0.05, "kg/s"),
        ("compressor_isentropic_efficiency", 0.75, "dimensionless"),
    ):
        project = update_condition(project, name, value=value, unit=unit)

    result = simulate_project(project)

    assert topology_issues(project) == ()
    assert baseline_model_issues(project) == ()
    assert [connection.state_number for connection in project.connections] == [2, 3, 4, 1]
    assert result.status == SolverStatus.CONVERGED


def test_baseline_requires_the_canvas_cycle_connections() -> None:
    project = remove_connection(default_r744_project(), "compressor", "gas_cooler")
    project = update_condition(project, "refrigerant_mass_flow", value=0.1, unit="kg/s")
    project = update_condition(
        project,
        "compressor_isentropic_efficiency",
        value=0.8,
        unit="dimensionless",
    )

    issues = baseline_model_issues(project)

    assert any("compressor → gas_cooler" in issue for issue in issues)
    with pytest.raises(ValueError, match="baseline 사이클 연결 누락"):
        design_from_project(project)


def test_component_efficiency_edit_is_used_by_the_existing_solver() -> None:
    project = project_from_command(
        interpret_command(
            "R134a 기본 냉동사이클을 구성하고 압축기에 등엔트로피 효율 0.75 모델을 "
            "적용해줘. 증발압력 3 bar(a), 고압 12 bar(a), 흡입온도 10°C, "
            "응축기 출구온도 35°C, 냉매 질량유량 0.05 kg/s."
        )
    )
    before = simulate_project(project)
    edited = update_condition(
        project,
        "compressor_isentropic_efficiency",
        value=0.80,
        unit="dimensionless",
    )
    after = simulate_project(edited)

    efficiency = condition_for_parameter(edited, "compressor_isentropic_efficiency")
    assert efficiency is not None
    assert efficiency.value == 0.80
    assert after.compressor_power.value < before.compressor_power.value
    assert after.cop > before.cop


def test_parameter_update_replaces_legacy_alias_and_connected_unknown_model_is_rejected() -> None:
    project = update_condition(
        default_r744_project(),
        "evaporator_pressure",
        value=28.0,
        unit="bar(a)",
    )
    pressure = condition_for_parameter(project, "evaporator_pressure")
    assert pressure is not None
    assert pressure.name == "evaporator_pressure"
    assert pressure.value == 28.0
    assert all(condition.name != "low_side_pressure" for condition in project.conditions)

    project = add_component(project, ComponentKind.PIPE, x=25, y=30)
    project = remove_connection(
        project,
        "compressor",
        "gas_cooler",
        source_port_id="compressor.outlet",
        target_port_id="gas_cooler.inlet",
    )
    project = add_connection(project, "compressor", "pipe_1")
    project = update_condition(project, "refrigerant_mass_flow", value=0.1, unit="kg/s")
    project = update_condition(
        project,
        "compressor_isentropic_efficiency",
        value=0.8,
        unit="dimensionless",
    )
    assert any("pipe_1" in issue for issue in baseline_model_issues(project))
    with pytest.raises(ValueError, match="baseline 모델 구성 오류"):
        design_from_project(project)


def test_complete_r134a_command_runs_existing_baseline_solver_with_entropy() -> None:
    plan = interpret_command(
        "R134a 기본 냉동사이클을 구성하고 압축기에 등엔트로피 효율 0.75 모델을 "
        "적용해줘. 증발압력 3 bar(a), 고압 12 bar(a), 흡입온도 10°C, "
        "응축기 출구온도 35°C, 냉매 질량유량 0.05 kg/s."
    )
    project = project_from_command(plan)

    result = simulate_project(project)

    assert plan.missing == ()
    assert missing_solver_inputs(project) == ()
    assert result.status == SolverStatus.CONVERGED
    assert result.is_mock is False
    assert result.cop == pytest.approx(3.9147244816576934)
    assert tuple(result.state_points) == (
        "compressor_inlet",
        "compressor_outlet",
        "heat_rejection_outlet",
        "expansion_valve_outlet",
    )
    assert all(state.entropy is not None for state in result.state_points.values())


def test_natural_language_parser_rejects_ambiguous_fluid_and_invalid_efficiency() -> None:
    plan = interpret_command(
        "R134a와 R410A 중 하나로 구성하고 등엔트로피 효율 120% 모델을 적용해줘"
    )

    assert plan.refrigerant is None
    assert "refrigerant" in plan.missing
    assert "compressor_isentropic_efficiency" in plan.missing
    assert any("0보다 크고 1 이하" in note for note in plan.notes)
    with pytest.raises(ValueError, match="냉매를 하나"):
        project_from_command(plan)


@pytest.mark.parametrize("raw_efficiency", ["-0.7", "-70%"])
def test_natural_language_parser_preserves_negative_efficiency_for_rejection(
    raw_efficiency: str,
) -> None:
    plan = interpret_command(f"R744 등엔트로피 효율 {raw_efficiency}")

    assert "compressor_isentropic_efficiency" in plan.missing
    assert not any(item.name == "compressor_isentropic_efficiency" for item in plan.conditions)
    assert any("0보다 크고 1 이하" in note for note in plan.notes)


@pytest.mark.parametrize("raw_efficiency", ["0.7", "70%"])
def test_natural_language_parser_accepts_valid_efficiency_forms(raw_efficiency: str) -> None:
    plan = interpret_command(f"R744 등엔트로피 효율 {raw_efficiency}")
    efficiency = next(
        item for item in plan.conditions if item.name == "compressor_isentropic_efficiency"
    )

    assert efficiency.value == pytest.approx(0.7)
    assert efficiency.unit == "dimensionless"


@pytest.mark.parametrize("gauge_unit", ["bar(g)", "barg"])
def test_natural_language_parser_rejects_gauge_pressure(gauge_unit: str) -> None:
    with pytest.raises(ValueError, match="게이지압"):
        interpret_command(f"R744 저압 30 {gauge_unit}")


@pytest.mark.parametrize("absolute_unit", ["bar(a)", "bara"])
def test_natural_language_parser_accepts_explicit_absolute_pressure(
    absolute_unit: str,
) -> None:
    plan = interpret_command(f"R744 저압 30 {absolute_unit}")
    pressure = next(item for item in plan.conditions if item.name == "evaporator_pressure")

    assert pressure.value == pytest.approx(30.0)
    assert pressure.unit.replace(" ", "").lower() == absolute_unit


def test_efficiency_adapter_validates_dimension_and_percent_policy() -> None:
    prompt = (
        "R134a 기본 냉동사이클을 구성하고 압축기에 등엔트로피 효율 0.75 모델을 "
        "적용해줘. 증발압력 3 bar(a), 고압 12 bar(a), 흡입온도 10°C, "
        "응축기 출구온도 35°C, 냉매 질량유량 0.05 kg/s."
    )
    project = project_from_command(interpret_command(prompt))
    wrong_dimension = update_condition(
        project,
        "compressor_isentropic_efficiency",
        value=0.75,
        unit="kg/s",
    )
    with pytest.raises(ValueError, match="효율 단위"):
        design_from_project(wrong_dimension)

    percent = update_condition(
        project,
        "compressor_isentropic_efficiency",
        value=75.0,
        unit="%",
    )
    design = design_from_project(percent)
    efficiency = next(
        item
        for item in design.requirements.parameters
        if item.name == "compressor_isentropic_efficiency"
    )
    assert efficiency.value.value == pytest.approx(0.75)
    assert efficiency.value.unit == "dimensionless"


@pytest.mark.parametrize(
    ("fluid", "expected_high_side"),
    [("R744", ComponentKind.GAS_COOLER), ("R410A", ComponentKind.CONDENSER)],
)
def test_natural_language_builder_selects_fluid_appropriate_high_side(
    fluid: str,
    expected_high_side: ComponentKind,
) -> None:
    project = project_from_command(interpret_command(f"{fluid} 기본 냉동사이클을 구성해줘"))

    assert any(component.kind == expected_high_side for component in project.components)
    high_side_id = expected_high_side.value
    assert {
        (connection.source_id, connection.target_id): (
            connection.source_anchor.side,
            connection.target_anchor.side,
        )
        for connection in project.connections
        if connection.source_anchor is not None and connection.target_anchor is not None
    } == {
        ("compressor", high_side_id): (PortSide.TOP, PortSide.RIGHT),
        (high_side_id, "expansion_valve"): (PortSide.LEFT, PortSide.TOP),
        ("expansion_valve", "evaporator"): (PortSide.BOTTOM, PortSide.LEFT),
        ("evaporator", "compressor"): (PortSide.RIGHT, PortSide.BOTTOM),
    }
    assert missing_solver_inputs(project) == (
        "evaporator_pressure",
        "high_side_pressure",
        "compressor_inlet_temperature",
        "heat_rejection_outlet_temperature",
        "refrigerant_mass_flow",
        "compressor_isentropic_efficiency",
    )


def test_streamlit_workbench_smoke() -> None:
    streamlit = pytest.importorskip("streamlit")
    assert streamlit
    from streamlit.testing.v1 import AppTest

    root = Path(__file__).resolve().parents[2]
    app = AppTest.from_file(str(root / "src/agent_hvac/app/design_workbench_app.py")).run(
        timeout=20
    )

    assert not app.exception
    assert any("캔버스는 편집기" in warning.value for warning in app.warning)
    assert any("필수 부품·연결 검사" in success.value for success in app.success)
    assert any(item.label == "전체 · 증발·저압측 압력 [bar(a)]" for item in app.text_input)
    open_editor = next(button for button in app.button if button.label == "속성 열기")
    app = open_editor.click().run(timeout=20)

    assert any(item.value == "컴포넌트 파라미터" for item in app.subheader)
    assert any(item.label == "일반 계산 모델" for item in app.selectbox)
    assert any(item.label.startswith("등엔트로피 효율") for item in app.text_input)
    assert any(item.label == "입력 가능한 항목과 단위" for item in app.expander)
    assert any(item.label == "예시 명령" for item in app.expander)
    assert any(button.label == "예시 사용" for button in app.button)
    assert any(button.label == "기본 사이클로 초기화" for button in app.button)
    assert not any("R744 기본 사이클로 초기화" == button.label for button in app.button)
    assert len(app.get("download_button")) == 1
    assert any(button.disabled for button in app.button)


def test_streamlit_palette_and_mock_connection_are_explicit() -> None:
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    root = Path(__file__).resolve().parents[2]
    app = AppTest.from_file(str(root / "src/agent_hvac/app/design_workbench_app.py")).run(
        timeout=20
    )
    component_kind = next(item for item in app.selectbox if item.label == "추가할 부품")
    app = component_kind.select(ComponentKind.PIPE).run(timeout=20)
    add_component_button = next(button for button in app.button if button.label == "캔버스에 추가")
    app = add_component_button.click().run(timeout=20)

    assert any("부품 5개" in text.value for text in app.caption)
    assert any("연결되지 않은 부품: pipe_1" in error.value for error in app.error)

    undo = next(button for button in app.button if button.label == "↶ 실행 취소")
    assert not undo.disabled
    app = undo.click().run(timeout=20)
    assert any("부품 4개" in text.value for text in app.caption)
    redo = next(button for button in app.button if button.label == "↷ 다시 실행")
    assert not redo.disabled
    app = redo.click().run(timeout=20)
    assert any("부품 5개" in text.value for text in app.caption)

    run_mock = next(
        button for button in app.button if button.label == "P09 결정론적 MOCK 연결 점검 실행"
    )
    app = run_mock.click().run(timeout=20)

    assert any(
        "캔버스 입력을 실제 HVAC 계산에 전달하지 않습니다" in item.value for item in app.warning
    )
    assert any("P09 최적화 결과 · completed" in heading.value for heading in app.subheader)
    assert len(app.metric) == 1

    diagram_preview = next(
        button for button in app.button if button.label == "MOCK P-h / T-s 표시 규칙 확인"
    )
    app = diagram_preview.click().run(timeout=20)
    assert len(app.get("vega_lite_chart")) == 1
    assert any("엔트로피 데이터가 없습니다" in item.value for item in app.info)


def test_streamlit_existing_connection_is_explained_without_raw_validation_error() -> None:
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    root = Path(__file__).resolve().parents[2]
    app = AppTest.from_file(str(root / "src/agent_hvac/app/design_workbench_app.py")).run(
        timeout=20
    )

    add = next(button for button in app.button if button.label == "연결 추가")
    remove = next(button for button in app.button if button.label == "연결 삭제")
    assert add.disabled
    assert not remove.disabled
    assert any("compressor → gas_cooler 연결은 이미 존재합니다" in item.value for item in app.info)
    assert not any("Connections must be unique" in item.value for item in app.error)


def test_streamlit_component_selection_updates_matching_editor_fields() -> None:
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    root = Path(__file__).resolve().parents[2]
    app = AppTest.from_file(str(root / "src/agent_hvac/app/design_workbench_app.py")).run(
        timeout=20
    )
    selector = next(item for item in app.selectbox if item.label == "선택 부품")
    app = selector.select("expansion_valve").run(timeout=20)
    open_editor = next(button for button in app.button if button.label == "속성 열기")
    app = open_editor.click().run(timeout=20)

    label = next(item for item in app.text_input if item.label == "표시 이름")
    assert label.value == "팽창밸브"
    assert app.slider[0].value == 18.0
    assert app.slider[1].value == 50.0


def test_streamlit_natural_language_builder_runs_real_baseline_result() -> None:
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    root = Path(__file__).resolve().parents[2]
    app = AppTest.from_file(str(root / "src/agent_hvac/app/design_workbench_app.py")).run(
        timeout=20
    )
    prompt = (
        "R134a 기본 냉동사이클을 구성하고 압축기에 등엔트로피 효율 0.75 모델을 "
        "적용해줘. 증발압력 3 bar(a), 고압 12 bar(a), 흡입온도 10°C, "
        "응축기 출구온도 35°C, 냉매 질량유량 0.05 kg/s."
    )
    app = app.text_area[0].set_value(prompt).run(timeout=20)
    analyze = next(button for button in app.button if button.label == "명령 해석")
    app = analyze.click().run(timeout=20)

    assert any("필요한 입력을 모두 인식" in item.value for item in app.success)
    apply = next(button for button in app.button if button.label == "캔버스에 구성")
    assert not apply.disabled
    app = apply.click().run(timeout=20)
    assert any("냉매 R134a" in item.value for item in app.caption)
    component_selector = next(item for item in app.selectbox if item.label == "선택 부품")
    assert "condenser" in component_selector.options
    high_pressure = next(
        item for item in app.text_input if item.label == "전체 · 토출·고압측 압력 [bar(a)]"
    )
    target_selector = next(item for item in app.selectbox if item.label == "도착 부품")
    assert float(high_pressure.value) == 12.0
    assert target_selector.value == "condenser"

    run = next(
        button for button in app.button if button.label == "캔버스 구성으로 baseline 계산 실행"
    )
    assert not run.disabled
    app = run.click().run(timeout=20)

    assert any("결과 · WORKBENCH-R134a" in item.value for item in app.subheader)
    assert any("Solver status: converged" in item.value for item in app.text)
    assert len(app.get("vega_lite_chart")) == 2


def test_streamlit_direct_conditions_run_canvas_without_natural_language() -> None:
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    root = Path(__file__).resolve().parents[2]
    app = AppTest.from_file(str(root / "src/agent_hvac/app/design_workbench_app.py")).run(
        timeout=20
    )
    mass_flow = next(item for item in app.text_input if item.label == "전체 · 냉매 질량유량 [kg/s]")
    efficiency = next(
        item for item in app.text_input if item.label == "전체 · 등엔트로피 효율 [dimensionless]"
    )
    mass_flow.set_value("0.1")
    efficiency.set_value("0.8")
    apply_conditions = next(button for button in app.button if button.label == "설계조건 적용")
    app = apply_conditions.click().run(timeout=20)

    run = next(
        button for button in app.button if button.label == "캔버스 구성으로 baseline 계산 실행"
    )
    assert not run.disabled
    app = run.click().run(timeout=20)

    assert any(item.value == "컴포넌트 입·출구 상태" for item in app.subheader)
    component_table = next(table for table in app.dataframe if "입구 T [°C]" in table.value.columns)
    assert list(component_table.value["ID"]) == [
        "compressor",
        "gas_cooler",
        "expansion_valve",
        "evaporator",
    ]
    assert any("Solver status: converged" in item.value for item in app.text)


def test_streamlit_manually_connected_canvas_runs_after_direct_input() -> None:
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    root = Path(__file__).resolve().parents[2]
    app = AppTest.from_file(str(root / "src/agent_hvac/app/design_workbench_app.py"))
    app.session_state["workbench_project"] = _manually_connected_r134a_project()
    app = app.run(timeout=20)

    values = {
        "전체 · 증발·저압측 압력 [bar(a)]": "3",
        "전체 · 토출·고압측 압력 [bar(a)]": "12",
        "전체 · 흡입 온도 [degC]": "10",
        "전체 · 고압 열교환기 출구 온도 [degC]": "35",
        "전체 · 냉매 질량유량 [kg/s]": "0.05",
        "전체 · 등엔트로피 효율 [dimensionless]": "0.75",
    }
    for field in app.text_input:
        if field.label in values:
            field.set_value(values[field.label])
    apply_conditions = next(button for button in app.button if button.label == "설계조건 적용")
    app = apply_conditions.click().run(timeout=20)

    assert any("현재 캔버스 연결" in item.value for item in app.success)
    run = next(
        button for button in app.button if button.label == "캔버스 구성으로 baseline 계산 실행"
    )
    assert not run.disabled
    app = run.click().run(timeout=20)

    assert any("Solver status: converged" in item.value for item in app.text)
    component_table = next(table for table in app.dataframe if "입구 T [°C]" in table.value.columns)
    assert list(component_table.value["ID"]) == [
        "compressor_1",
        "condenser_1",
        "expansion_valve_1",
        "evaporator_1",
    ]


def test_streamlit_component_parameter_edit_reaches_the_real_solver() -> None:
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    root = Path(__file__).resolve().parents[2]
    app = AppTest.from_file(str(root / "src/agent_hvac/app/design_workbench_app.py")).run(
        timeout=20
    )
    analyze = next(button for button in app.button if button.label == "명령 해석")
    app = analyze.click().run(timeout=20)
    apply = next(button for button in app.button if button.label == "캔버스에 구성")
    app = apply.click().run(timeout=20)
    open_editor = next(button for button in app.button if button.label == "속성 열기")
    app = open_editor.click().run(timeout=20)
    efficiency = next(
        item for item in app.text_input if item.label == "등엔트로피 효율 [dimensionless]"
    )
    app = efficiency.set_value("0.80").run(timeout=20)
    apply_parameter = next(button for button in app.button if button.label == "부품 파라미터 적용")
    app = apply_parameter.click().run(timeout=20)

    efficiency = next(
        item for item in app.text_input if item.label == "등엔트로피 효율 [dimensionless]"
    )
    assert float(efficiency.value) == pytest.approx(0.80)
    run = next(
        button for button in app.button if button.label == "캔버스 구성으로 baseline 계산 실행"
    )
    app = run.click().run(timeout=20)
    cop = next(metric for metric in app.metric if metric.label == "COP [dimensionless]")
    assert float(cop.value) == pytest.approx(4.175706113768209)


def _converged_default_workbench_app():
    from streamlit.testing.v1 import AppTest

    root = Path(__file__).resolve().parents[2]
    app = AppTest.from_file(str(root / "src/agent_hvac/app/design_workbench_app.py")).run(
        timeout=20
    )
    mass_flow = next(item for item in app.text_input if "냉매 질량유량" in item.label)
    efficiency = next(item for item in app.text_input if "등엔트로피 효율" in item.label)
    mass_flow.set_value("0.1")
    efficiency.set_value("0.8")
    apply_conditions = next(button for button in app.button if button.label == "설계조건 적용")
    app = apply_conditions.click().run(timeout=20)
    run = next(
        button for button in app.button if button.label == "캔버스 구성으로 baseline 계산 실행"
    )
    app = run.click().run(timeout=20)
    assert "workbench_result" in app.session_state.filtered_state
    assert "workbench_result_project_fingerprint" in app.session_state.filtered_state
    assert any("Solver status: converged" in item.value for item in app.text)
    return app


def _assert_workbench_result_invalidated(app) -> None:
    assert "workbench_result" not in app.session_state.filtered_state
    assert "workbench_result_project_fingerprint" not in app.session_state.filtered_state
    assert not any("Solver status: converged" in item.value for item in app.text)


def test_streamlit_component_delete_invalidates_previous_result() -> None:
    pytest.importorskip("streamlit")
    app = _converged_default_workbench_app()
    open_editor = next(button for button in app.button if button.label == "속성 열기")
    app = open_editor.click().run(timeout=20)
    remove = next(button for button in app.button if button.label == "선택 부품 제거")

    app = remove.click().run(timeout=20)

    _assert_workbench_result_invalidated(app)
    assert any("부품 3개" in item.value for item in app.caption)

    undo = next(button for button in app.button if button.label == "↶ 실행 취소")
    app = undo.click().run(timeout=20)
    _assert_workbench_result_invalidated(app)
    assert any("부품 4개" in item.value for item in app.caption)


def test_missing_conditions_expand_editor_and_history_starts_disabled() -> None:
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    root = Path(__file__).resolve().parents[2]
    app = AppTest.from_file(str(root / "src/agent_hvac/app/design_workbench_app.py")).run(
        timeout=20
    )

    editor = next(item for item in app.expander if item.label == "설계조건 입력·수정")
    assert editor.proto.expanded
    undo = next(button for button in app.button if button.label == "↶ 실행 취소")
    redo = next(button for button in app.button if button.label == "↷ 다시 실행")
    assert undo.disabled
    assert redo.disabled


def test_streamlit_connection_change_invalidates_previous_result() -> None:
    pytest.importorskip("streamlit")
    app = _converged_default_workbench_app()
    remove = next(button for button in app.button if button.label == "연결 삭제")

    app = remove.click().run(timeout=20)

    _assert_workbench_result_invalidated(app)


def test_streamlit_parameter_change_invalidates_previous_result() -> None:
    pytest.importorskip("streamlit")
    app = _converged_default_workbench_app()
    mass_flow = next(item for item in app.text_input if "냉매 질량유량" in item.label)
    mass_flow.set_value("0.11")
    apply_conditions = next(button for button in app.button if button.label == "설계조건 적용")

    app = apply_conditions.click().run(timeout=20)

    _assert_workbench_result_invalidated(app)


def test_streamlit_json_upload_invalidates_previous_result() -> None:
    pytest.importorskip("streamlit")
    app = _converged_default_workbench_app()
    uploaded_project = project_from_command(interpret_command("R134a 기본 냉동사이클을 구성해줘"))
    uploader = app.get("file_uploader")[0]

    app = uploader.upload(
        "r134a-workbench.json",
        project_json(uploaded_project).encode("utf-8"),
        "application/json",
    ).run(timeout=20)

    _assert_workbench_result_invalidated(app)
    assert any("냉매 R134a" in item.value for item in app.caption)
