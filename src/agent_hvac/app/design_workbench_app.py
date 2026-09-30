"""Streamlit entry point for the R744 schematic workbench MVP."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal, cast

import streamlit as st
from pydantic import ValidationError
from streamlit.components.v2 import component

from agent_hvac.app.design_workbench import (
    ComponentKind,
    WorkbenchProject,
    add_component,
    add_connection,
    apply_canvas_action,
    baseline_model_issues,
    component_parameter_names,
    component_ports,
    condition_for_parameter,
    default_r744_project,
    generic_calculation_model,
    load_project,
    project_json,
    remove_component,
    remove_connection,
    topology_issues,
    update_component,
    update_condition,
)
from agent_hvac.app.streamlit_app import render_artifact, render_optimization_result
from agent_hvac.app.synthetic_flow import SyntheticScenario, run_synthetic_scenario
from agent_hvac.app.workbench_canvas_component import (
    WORKBENCH_CANVAS_CSS,
    WORKBENCH_CANVAS_HTML,
    WORKBENCH_CANVAS_JS,
)
from agent_hvac.app.workbench_command import (
    CommandPlan,
    interpret_command,
    missing_solver_inputs,
    project_from_command,
    required_solver_input_names,
    simulate_project,
)
from agent_hvac.schemas.design import DesignProblem
from agent_hvac.schemas.results import SimulationResult, SolverStatus

ROOT = Path(__file__).resolve().parents[3]

PALETTE_LABELS = {
    ComponentKind.COMPRESSOR: "압축기",
    ComponentKind.GAS_COOLER: "Gas cooler",
    ComponentKind.CONDENSER: "응축기",
    ComponentKind.EXPANSION_VALVE: "팽창밸브",
    ComponentKind.EVAPORATOR: "증발기",
    ComponentKind.PIPE: "배관",
    ComponentKind.RECEIVER: "Receiver",
    ComponentKind.ACCUMULATOR: "Accumulator",
    ComponentKind.INTERNAL_HEAT_EXCHANGER: "내부 열교환기",
    ComponentKind.FAN: "Fan",
    ComponentKind.PUMP: "Pump",
}

PARAMETER_PRESENTATION = {
    "compressor_inlet_temperature": ("흡입 온도", "degC"),
    "high_side_pressure": ("토출·고압측 압력", "bar(a)"),
    "compressor_isentropic_efficiency": ("등엔트로피 효율", "dimensionless"),
    "refrigerant_mass_flow": ("냉매 질량유량", "kg/s"),
    "heat_rejection_outlet_temperature": ("고압 열교환기 출구 온도", "degC"),
    "evaporator_pressure": ("증발·저압측 압력", "bar(a)"),
}

PARAMETER_EXAMPLES = {
    "evaporator_pressure": "3 bar(a)",
    "high_side_pressure": "12 bar(a)",
    "compressor_inlet_temperature": "10 °C",
    "heat_rejection_outlet_temperature": "35 °C",
    "refrigerant_mass_flow": "0.05 kg/s",
    "compressor_isentropic_efficiency": "0.75",
}

APP_THEME_CSS = """
<style>
:root {
  --hvac-app-bg: #f1f5f9;
  --hvac-panel: #ffffff;
  --hvac-border: #e2e8f0;
  --hvac-text: #1e293b;
  --hvac-muted: #64748b;
  --hvac-accent: #2563eb;
}
[data-testid="stAppViewContainer"] { background: var(--hvac-app-bg); color: var(--hvac-text); }
[data-testid="stHeader"] { background: rgba(241, 245, 249, 0.92); }
[data-testid="stSidebar"] {
  background: var(--hvac-panel); border-right: 1px solid var(--hvac-border);
}
[data-testid="stSidebar"] > div:first-child { padding-top: 1.4rem; }
.block-container { max-width: 1760px; padding-top: 1.25rem; padding-bottom: 2rem; }
h1, h2, h3, h4 { color: var(--hvac-text); letter-spacing: -0.018em; }
h1 { font-size: 2rem !important; font-weight: 720 !important; }
h3 { font-size: 1rem !important; font-weight: 680 !important; }
[data-testid="stCaptionContainer"], .stCaption { color: var(--hvac-muted) !important; }
[data-testid="stExpander"] {
  border: 1px solid var(--hvac-border); border-radius: 8px; background: var(--hvac-panel);
}
[data-testid="stMetric"] {
  padding: .65rem .75rem; border: 1px solid var(--hvac-border); border-radius: 7px;
  background: #fff;
}
[data-testid="stMetricLabel"] { color: var(--hvac-muted); }
div[data-testid="stButton"] button, div[data-testid="stDownloadButton"] button {
  min-height: 2.25rem; border: 1px solid #cbd5e1; border-radius: 6px;
  background: #fff; color: #334155;
  box-shadow: 0 1px 1px rgba(15, 23, 42, .03); font-weight: 600;
}
div[data-testid="stButton"] button:hover, div[data-testid="stDownloadButton"] button:hover {
  border-color: #93c5fd; background: #f8fbff; color: #1d4ed8;
}
div[data-testid="stButton"] button[kind="primary"] {
  border-color: var(--hvac-accent); background: var(--hvac-accent); color: #fff;
}
[data-baseweb="input"] > div, [data-baseweb="textarea"] > div, [data-baseweb="select"] > div {
  border-color: #d8dee8 !important; background: #fff !important;
}
[data-testid="stAlert"] { border-radius: 7px; border-width: 1px; box-shadow: none; }
[data-testid="stHorizontalBlock"] { align-items: flex-start; }
hr { border-color: var(--hvac-border) !important; }
</style>
"""

_workbench_canvas = component(
    "agent_hvac_workbench_canvas",
    html=WORKBENCH_CANVAS_HTML,
    css=WORKBENCH_CANVAS_CSS,
    js=WORKBENCH_CANVAS_JS,
)

_HISTORY_CURRENT_KEY = "project_history_current"
_HISTORY_UNDO_KEY = "project_history_undo"
_HISTORY_REDO_KEY = "project_history_redo"
_HISTORY_LIMIT = 50
_IMPORTED_UPLOAD_KEY = "workbench_imported_upload"


def _project_fingerprint(project: WorkbenchProject) -> str:
    return hashlib.sha256(project_json(project).encode("utf-8")).hexdigest()


def _invalidate_workbench_result() -> None:
    st.session_state.pop("workbench_result", None)
    st.session_state.pop("workbench_result_project_fingerprint", None)


def _sync_project_history(project: WorkbenchProject) -> None:
    """Record project changes that occurred during the previous Streamlit run."""

    current = project_json(project)
    tracked = st.session_state.get(_HISTORY_CURRENT_KEY)
    if not isinstance(tracked, str):
        st.session_state[_HISTORY_CURRENT_KEY] = current
        st.session_state[_HISTORY_UNDO_KEY] = []
        st.session_state[_HISTORY_REDO_KEY] = []
        return
    if tracked == current:
        return
    undo = list(st.session_state.get(_HISTORY_UNDO_KEY, []))
    undo.append(tracked)
    st.session_state[_HISTORY_UNDO_KEY] = undo[-_HISTORY_LIMIT:]
    st.session_state[_HISTORY_REDO_KEY] = []
    st.session_state[_HISTORY_CURRENT_KEY] = current


def _restore_project_history(direction: Literal["undo", "redo"]) -> None:
    source_key = _HISTORY_UNDO_KEY if direction == "undo" else _HISTORY_REDO_KEY
    target_key = _HISTORY_REDO_KEY if direction == "undo" else _HISTORY_UNDO_KEY
    source = list(st.session_state.get(source_key, []))
    current = st.session_state.get(_HISTORY_CURRENT_KEY)
    if not source or not isinstance(current, str):
        return
    restored_json = source.pop()
    target = list(st.session_state.get(target_key, []))
    target.append(current)
    restored = load_project(restored_json.encode("utf-8"))
    st.session_state[source_key] = source
    st.session_state[target_key] = target[-_HISTORY_LIMIT:]
    st.session_state[_HISTORY_CURRENT_KEY] = restored_json
    st.session_state.workbench_project = restored
    _clear_project_widget_state()
    _invalidate_workbench_result()
    st.rerun()


def _render_project_history_controls() -> None:
    undo = st.session_state.get(_HISTORY_UNDO_KEY, [])
    redo = st.session_state.get(_HISTORY_REDO_KEY, [])
    left, right = st.sidebar.columns(2)
    with left:
        if st.button("↶ 실행 취소", disabled=not undo, use_container_width=True):
            _restore_project_history("undo")
    with right:
        if st.button("↷ 다시 실행", disabled=not redo, use_container_width=True):
            _restore_project_history("redo")
    st.sidebar.caption(f"편집 기록 {len(undo)}단계 · 최대 {_HISTORY_LIMIT}단계")


def _project_widget_suffix(project: WorkbenchProject) -> str:
    source = project.source_prompt or "default"
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:10]
    return f"{project.refrigerant}-{digest}"


def _clear_project_widget_state() -> None:
    for key in tuple(st.session_state):
        if isinstance(key, str) and (
            key.startswith("workbench-")
            or key.startswith("condition-")
            or key.startswith("connection-")
        ):
            del st.session_state[key]


def _empty_project(refrigerant: Literal["R744", "R134a", "R410A"]) -> WorkbenchProject:
    return WorkbenchProject(
        title=f"{refrigerant} 사용자 구성 사이클",
        refrigerant=refrigerant,
        components=(),
        connections=(),
        conditions=(),
        source_prompt=None,
        layout_preset="refrigeration_cycle",
    )


def _basic_project(refrigerant: Literal["R744", "R134a", "R410A"]) -> WorkbenchProject:
    if refrigerant == "R744":
        return default_r744_project()
    return project_from_command(interpret_command(f"{refrigerant} 기본 냉동사이클을 구성해줘"))


def _render_command_builder() -> None:
    st.subheader("자연어 사이클 구성")
    st.caption("지원 냉매: R134a, R410A, R744 · 명령에 없는 공학 수치는 자동으로 만들지 않습니다.")
    default_prompt = (
        "R134a 기본 냉동사이클을 구성하고 압축기에 등엔트로피 효율 0.75 모델을 적용해줘. "
        "증발압력 3 bar(a), 고압 12 bar(a), 흡입온도 10°C, 응축기 출구온도 35°C, "
        "냉매 질량유량 0.05 kg/s."
    )
    command_key = "natural-language-command"
    if command_key not in st.session_state:
        st.session_state[command_key] = default_prompt
    with st.expander("입력 가능한 항목과 단위", expanded=False):
        st.caption("현재 BaselineCycleSolver adapter가 실제로 요구하는 입력만 표시합니다.")
        st.markdown("**필수 냉매:** R134a · R410A · R744 중 하나")
        st.dataframe(
            [
                {
                    "필수 입력": PARAMETER_PRESENTATION[name][0],
                    "단위": PARAMETER_PRESENTATION[name][1],
                    "예": PARAMETER_EXAMPLES[name],
                }
                for name in required_solver_input_names()
            ],
            hide_index=True,
        )
    with st.expander("예시 명령", expanded=False):
        st.code(default_prompt, language=None)
        st.caption(
            "지원 topology 예: ‘R134a 기본 냉동사이클을 구성해줘. "
            "응축기랑 팽창밸브 사이에 배관 넣어줘.’"
        )
        if st.button("예시 사용", key="use-natural-language-example"):
            st.session_state[command_key] = default_prompt
            st.session_state.pop("command_plan", None)
            st.rerun()
    prompt = st.text_area(
        "설계 명령",
        height=95,
        key=command_key,
    )
    analyze, apply = st.columns(2)
    with analyze:
        if st.button("명령 해석", use_container_width=True):
            try:
                st.session_state.command_plan = interpret_command(prompt)
            except ValueError as error:
                st.error(str(error))
    plan = st.session_state.get("command_plan")
    with apply:
        if st.button(
            "캔버스에 구성",
            use_container_width=True,
            disabled=not isinstance(plan, CommandPlan) or plan.refrigerant is None,
        ):
            assert isinstance(plan, CommandPlan)
            try:
                project = project_from_command(plan)
            except ValueError as error:
                st.error(str(error))
            else:
                _clear_project_widget_state()
                st.session_state.workbench_project = project
                _invalidate_workbench_result()
                st.rerun()

    if isinstance(plan, CommandPlan):
        refrigerant = plan.refrigerant or "확인 필요"
        model = plan.compressor_model or "미지정"
        first, second, third = st.columns(3)
        first.metric("감지 냉매", refrigerant)
        second.metric("압축기 모델", model)
        third.metric("감지 조건", len(plan.conditions))
        if plan.conditions:
            st.dataframe(
                [
                    {"조건": item.name, "값": item.value, "원문 단위": item.unit}
                    for item in plan.conditions
                ],
                hide_index=True,
            )
        if plan.missing:
            st.warning("계산 전 추가 입력 필요: " + ", ".join(plan.missing))
        else:
            st.success("baseline 계산에 필요한 입력을 모두 인식했습니다.")
        for note in plan.notes:
            st.caption(note)


def _render_condition_editor(project: WorkbenchProject) -> WorkbenchProject:
    suffix = _project_widget_suffix(project)
    required = required_solver_input_names()
    supplied = {name: condition_for_parameter(project, name) for name in required}
    completed = sum(condition is not None for condition in supplied.values())
    missing = missing_solver_inputs(project)
    st.caption(f"계산 입력 {completed}/{len(required)} · 자연어 없이 직접 입력 가능")
    with st.expander("설계조건 입력·수정", expanded=bool(missing)):
        entered: dict[str, tuple[str, str]] = {}
        with st.form(f"workbench-condition-form-{suffix}"):
            for name in required:
                label, default_unit = PARAMETER_PRESENTATION[name]
                condition = supplied[name]
                unit = condition.unit if condition is not None else default_unit
                source = (
                    "미입력"
                    if condition is None
                    else f"{condition.source_type} · {condition.source_ref}"
                )
                entered[name] = (
                    st.text_input(
                        f"전체 · {label} [{unit}]",
                        value="" if condition is None else f"{condition.value:g}",
                        placeholder=PARAMETER_EXAMPLES[name],
                        help=f"현재 출처: {source}",
                        key=(
                            f"condition-{suffix}-{name}-"
                            f"{'missing' if condition is None else format(condition.value, '.12g')}"
                        ),
                    ),
                    unit,
                )
            submitted = st.form_submit_button("설계조건 적용", use_container_width=True)
        if submitted:
            changed = project
            try:
                for name, (raw_value, unit) in entered.items():
                    if raw_value.strip():
                        changed = update_condition(
                            changed,
                            name,
                            value=float(raw_value),
                            unit=unit,
                            source_ref="workbench design condition editor",
                        )
            except (ValueError, ValidationError) as error:
                st.error(f"설계조건 입력 거부: {error}")
            else:
                st.session_state.workbench_project = changed
                _invalidate_workbench_result()
                st.rerun()
    if missing:
        st.warning("미입력: " + ", ".join(PARAMETER_PRESENTATION[name][0] for name in missing))
    return project


def _render_palette(project: WorkbenchProject) -> tuple[WorkbenchProject, str]:
    st.subheader("부품 라이브러리")
    st.caption("캔버스 상단에서 끌어 놓거나 목록에서 추가하세요.")
    palette_kinds = list(PALETTE_LABELS)
    selected_kind = st.selectbox(
        "추가할 부품",
        palette_kinds,
        format_func=lambda kind: PALETTE_LABELS[kind],
        key="workbench-add-component-kind",
    )
    if st.button("캔버스에 추가", key="add-selected-component", use_container_width=True):
        project = add_component(
            project,
            selected_kind,
            x=50,
            y=min(88, 18 + len(project.components) * 9),
        )
        st.session_state.workbench_project = project
        _invalidate_workbench_result()
        st.rerun()
    st.subheader("부품 선택")
    suffix = _project_widget_suffix(project)
    component_ids = [component.component_id for component in project.components]
    if not component_ids:
        st.caption("빈 캔버스입니다. 라이브러리에서 부품을 추가하세요.")
        return project, ""
    selector_key = f"workbench-component-select-{suffix}"
    pending_selection = st.session_state.pop("workbench-pending-component-selection", None)
    if pending_selection in component_ids:
        st.session_state[selector_key] = pending_selection
    selected_id = st.selectbox(
        "선택 부품",
        component_ids,
        key=selector_key,
    )
    selected = next(
        component for component in project.components if component.component_id == selected_id
    )
    st.caption("컴포넌트를 왼쪽 버튼으로 두 번 클릭하면 왼쪽 속성 패널이 열립니다.")
    if st.button("속성 열기", use_container_width=True):
        st.session_state["workbench-property-focus"] = selected_id
        st.rerun()
    if st.session_state.get("workbench-property-focus") == selected_id:
        st.info(f"{selected.label} 속성 패널이 열려 있습니다.")
    return project, selected_id


def _render_sidebar_component_editor(project: WorkbenchProject) -> WorkbenchProject:
    selected_id = st.session_state.get("workbench-property-focus")
    if not isinstance(selected_id, str):
        st.session_state.pop("workbench-property-focus", None)
        return project
    selected = next(
        (component for component in project.components if component.component_id == selected_id),
        None,
    )
    if selected is None:
        st.session_state.pop("workbench-property-focus", None)
        return project

    suffix = _project_widget_suffix(project)
    with st.sidebar:
        st.divider()
        st.subheader("컴포넌트 파라미터")
        st.caption(f"{selected.label} · {selected.kind.value} · {selected.component_id}")
        if st.button("속성 패널 닫기", use_container_width=True):
            st.session_state.pop("workbench-property-focus", None)
            st.rerun()

        label = st.text_input(
            "표시 이름",
            value=selected.label,
            key=f"workbench-sidebar-label-{suffix}-{selected_id}",
        )
        model_reference = st.text_input(
            "제품 모델 참조 (선택)",
            value=selected.model_reference or "",
            placeholder="미지정",
            key=f"workbench-sidebar-model-{suffix}-{selected_id}",
        )
        supported_model = generic_calculation_model(selected.kind)
        if supported_model is None:
            calculation_model = selected.calculation_model
            st.warning("이 부품은 현재 캔버스 편집용이며 baseline solver에 연결되지 않습니다.")
        else:
            calculation_model = st.selectbox(
                "일반 계산 모델",
                [supported_model],
                index=0,
                key=f"workbench-sidebar-calculation-model-{suffix}-{selected_id}",
            )
            st.success("제품 DB 없이 사용할 수 있는 일반 물리 모델입니다.")

        with st.expander("캔버스 위치"):
            x = st.slider(
                "캔버스 X",
                0.0,
                100.0,
                selected.x,
                1.0,
                key=f"workbench-sidebar-x-{suffix}-{selected_id}-{selected.x:.6g}",
            )
            y = st.slider(
                "캔버스 Y",
                0.0,
                100.0,
                selected.y,
                1.0,
                key=f"workbench-sidebar-y-{suffix}-{selected_id}-{selected.y:.6g}",
            )
        st.caption("상·하·좌·우 연결점은 시작 시 Outlet, 도착 시 Inlet으로 동작합니다.")
        if st.button("부품 위치·속성 적용", use_container_width=True):
            changed = update_component(
                project,
                selected_id,
                label=label,
                x=x,
                y=y,
                model_reference=model_reference,
                calculation_model=calculation_model,
            )
            st.session_state.workbench_project = changed
            _invalidate_workbench_result()
            st.rerun()

        st.markdown("#### 계산 파라미터")
        parameter_names = component_parameter_names(selected.kind)
        entered: dict[str, tuple[str, str]] = {}
        if not parameter_names:
            st.caption("현재 baseline 계산에 전달되는 파라미터가 없습니다.")
        for name in parameter_names:
            label_text, default_unit = PARAMETER_PRESENTATION[name]
            condition = condition_for_parameter(project, name)
            unit = condition.unit if condition is not None else default_unit
            entered[name] = (
                st.text_input(
                    f"{label_text} [{unit}]",
                    value="" if condition is None else f"{condition.value:g}",
                    placeholder="값을 직접 입력",
                    key=(
                        f"workbench-sidebar-parameter-{suffix}-{name}-"
                        f"{'missing' if condition is None else format(condition.value, '.12g')}"
                    ),
                ),
                unit,
            )
        if parameter_names and st.button("부품 파라미터 적용", use_container_width=True):
            changed = project
            try:
                for name, (raw_value, unit) in entered.items():
                    if raw_value.strip():
                        changed = update_condition(
                            changed,
                            name,
                            value=float(raw_value),
                            unit=unit,
                        )
            except (ValueError, ValidationError) as error:
                st.error(f"파라미터 입력 거부: {error}")
            else:
                st.session_state.workbench_project = changed
                _invalidate_workbench_result()
                st.rerun()

        if st.button("선택 부품 제거", use_container_width=True):
            changed = remove_component(project, selected_id)
            st.session_state.workbench_project = changed
            st.session_state.pop("workbench-property-focus", None)
            _invalidate_workbench_result()
            st.rerun()
    return project


def _render_interactive_canvas(
    project: WorkbenchProject,
    selected_component_id: str,
) -> WorkbenchProject:
    result = _workbench_canvas(
        key=(f"workbench-interactive-canvas-body-connect-v8-{_project_widget_suffix(project)}"),
        data={
            "components": [
                {
                    **component.model_dump(mode="json"),
                    "ports": [port.model_dump(mode="json") for port in component_ports(component)],
                }
                for component in project.components
            ],
            "connections": [
                connection.model_dump(mode="json") for connection in project.connections
            ],
            "edge_routing": [routing.model_dump(mode="json") for routing in project.edge_routing],
            "palette": [
                {"kind": kind.value, "label": label} for kind, label in PALETTE_LABELS.items()
            ],
            "selected_component_id": selected_component_id,
        },
        height=620,
        on_action_change=lambda: None,
    )
    action = getattr(result, "action", None)
    if not isinstance(action, dict):
        return project
    nonce = str(action.get("nonce", ""))
    if not nonce or st.session_state.get("workbench-last-canvas-action") == nonce:
        return project
    action_type = action.get("type")
    if action_type in {"undo", "redo"}:
        st.session_state["workbench-last-canvas-action"] = nonce
        _restore_project_history(cast(Literal["undo", "redo"], action_type))
    if action.get("type") == "select":
        component_id = action.get("component_id")
        known_ids = {component.component_id for component in project.components}
        if not isinstance(component_id, str) or component_id not in known_ids:
            st.error("캔버스 선택 이벤트가 알 수 없는 부품을 참조합니다.")
            st.session_state["workbench-last-canvas-action"] = nonce
            return project
        st.session_state["workbench-last-canvas-action"] = nonce
        st.session_state["workbench-pending-component-selection"] = component_id
        if bool(action.get("open_properties")):
            st.session_state["workbench-property-focus"] = component_id
        st.rerun()
    try:
        changed = apply_canvas_action(project, action)
    except (ValueError, ValidationError) as error:
        st.error(f"캔버스 변경 거부: {error}")
        st.session_state["workbench-last-canvas-action"] = nonce
        return project
    st.session_state["workbench-last-canvas-action"] = nonce
    st.session_state.workbench_project = changed
    if action.get("type") == "remove_component":
        st.session_state.pop("workbench-property-focus", None)
        st.session_state.pop("workbench-pending-component-selection", None)
    _invalidate_workbench_result()
    st.rerun()
    return changed


def _render_connection_editor(project: WorkbenchProject) -> None:
    st.subheader("포트 연결 편집")
    suffix = _project_widget_suffix(project)
    ids = [component.component_id for component in project.components]
    if len(ids) < 2:
        st.caption("부품을 두 개 이상 추가하면 목록에서도 연결할 수 있습니다.")
        return
    source = st.selectbox("출발 부품", ids, key=f"connection-source-{suffix}")
    target = st.selectbox(
        "도착 부품",
        ids,
        index=min(1, len(ids) - 1),
        key=f"connection-target-{suffix}",
    )
    connection_exists = any(
        connection.source_id == source and connection.target_id == target
        for connection in project.connections
    )
    self_connection = source == target
    if connection_exists:
        st.info(f"{source} → {target} 연결은 이미 존재합니다.")
    elif self_connection:
        st.info("출발 부품과 다른 도착 부품을 선택해 주세요.")
    add_column, remove_column = st.columns(2)
    with add_column:
        if st.button(
            "연결 추가",
            use_container_width=True,
            disabled=connection_exists or self_connection,
        ):
            try:
                changed = add_connection(project, source, target)
            except ValidationError as error:
                st.error(f"연결 추가 거부: {error.errors()[0]['msg']}")
            else:
                st.session_state.workbench_project = changed
                _invalidate_workbench_result()
                st.rerun()
    with remove_column:
        if st.button("연결 삭제", use_container_width=True, disabled=not connection_exists):
            changed = remove_connection(project, source, target)
            st.session_state.workbench_project = changed
            _invalidate_workbench_result()
            st.rerun()


_STATE_POINT_BY_NUMBER = {
    1: "compressor_inlet",
    2: "compressor_outlet",
    3: "heat_rejection_outlet",
    4: "expansion_valve_outlet",
}


def _component_state_rows(
    project: WorkbenchProject,
    result: SimulationResult,
) -> list[dict[str, str | float]]:
    rows: list[dict[str, str | float]] = []
    for canvas_component in project.components:
        incoming = next(
            (
                item
                for item in project.connections
                if item.target_id == canvas_component.component_id
            ),
            None,
        )
        outgoing = next(
            (
                item
                for item in project.connections
                if item.source_id == canvas_component.component_id
            ),
            None,
        )
        if incoming is None or outgoing is None:
            continue
        inlet_name = _STATE_POINT_BY_NUMBER.get(incoming.state_number or -1)
        outlet_name = _STATE_POINT_BY_NUMBER.get(outgoing.state_number or -1)
        inlet = result.state_points.get(inlet_name or "")
        outlet = result.state_points.get(outlet_name or "")
        if inlet is None or outlet is None:
            continue
        rows.append(
            {
                "컴포넌트": canvas_component.label,
                "ID": canvas_component.component_id,
                "입구 상태점": inlet_name or "",
                "입구 T [°C]": inlet.temperature.value - 273.15,
                "입구 p [bar(a)]": inlet.pressure.value / 100_000.0,
                "출구 상태점": outlet_name or "",
                "출구 T [°C]": outlet.temperature.value - 273.15,
                "출구 p [bar(a)]": outlet.pressure.value / 100_000.0,
            }
        )
    return rows


def _render_workbench_result(project: WorkbenchProject, result: SimulationResult) -> None:
    if result.status == SolverStatus.CONVERGED:
        rows = _component_state_rows(project, result)
        if rows:
            st.subheader("컴포넌트 입·출구 상태")
            st.dataframe(rows, hide_index=True, use_container_width=True)
            st.caption("solver가 반환한 상태점을 캔버스 연결의 상태번호 1–4에 대응했습니다.")
    elif any("evaporator capacity must be positive" in message for message in result.messages):
        st.warning(
            "입력 조건에서 팽창밸브 출구 엔탈피가 압축기 흡입 엔탈피보다 낮아지지 않아 "
            "증발기 냉동능력을 양수로 계산할 수 없습니다. 냉매에 맞는 고압측 압력, "
            "고압 열교환기 출구온도와 저압측 흡입상태를 다시 확인하세요. "
            "값은 자동 변경하지 않습니다."
        )
    render_artifact(result)


def _render_services(project: WorkbenchProject) -> None:
    st.subheader("서비스 연결")
    missing = missing_solver_inputs(project)
    model_issues = baseline_model_issues(project)
    editor_issues = topology_issues(project)
    st.info(
        "제품 모델이 없어도 선택한 일반 부품 모델과 직접 입력한 파라미터로 "
        "CoolProp 물성·P02 단일단 solver를 실행합니다. 제조사 제품 성능이나 "
        "자동선정 결과는 포함하지 않습니다."
    )
    if missing:
        st.warning("Baseline 실행 불가 · 필수 입력 누락: " + ", ".join(missing))
    for issue in model_issues:
        st.warning("Baseline 실행 불가 · " + issue)
    if not missing and not editor_issues and not model_issues:
        st.success("현재 캔버스 연결과 직접 입력한 설계조건으로 계산할 준비가 됐습니다.")
    if st.button(
        "캔버스 구성으로 baseline 계산 실행",
        type="primary",
        disabled=bool(missing or editor_issues or model_issues),
    ):
        try:
            st.session_state.workbench_result = simulate_project(project)
            st.session_state.workbench_result_project_fingerprint = _project_fingerprint(project)
        except (ValidationError, ValueError) as error:
            st.error(f"Baseline 입력 변환 실패: {error}")
    result = st.session_state.get("workbench_result")
    result_fingerprint = st.session_state.get("workbench_result_project_fingerprint")
    if isinstance(result, SimulationResult) and result_fingerprint != _project_fingerprint(project):
        _invalidate_workbench_result()
        result = None
    if isinstance(result, SimulationResult):
        _render_workbench_result(project, result)

    st.divider()
    st.subheader("MOCK 회귀 도구")
    st.warning(
        "P09 연결 점검은 committed synthetic fixture를 실행합니다. "
        "캔버스 입력을 실제 HVAC 계산에 전달하지 않습니다."
    )
    if st.button("P09 결정론적 MOCK 연결 점검 실행", type="primary"):
        fixture = ROOT / "tests" / "fixtures" / "design_problem_p09.json"
        problem = DesignProblem.model_validate_json(fixture.read_bytes())
        optimization_result = run_synthetic_scenario(problem, SyntheticScenario.NORMAL)
        render_optimization_result(optimization_result)
    if st.button("MOCK P-h / T-s 표시 규칙 확인"):
        fixture = ROOT / "tests" / "fixtures" / "simulation_result_r744.json"
        simulation_result = SimulationResult.model_validate_json(fixture.read_bytes())
        render_artifact(simulation_result)
    st.button("제품 DB 자동선정 · 준비 중", disabled=True)


def main() -> None:
    st.set_page_config(page_title="Agent-HVAC · 1D 설계", layout="wide")
    st.markdown(APP_THEME_CSS, unsafe_allow_html=True)
    st.title("Agent-HVAC 1D 설계 워크벤치")
    st.caption("WS-E · 자연어 지원 schematic editor")
    st.warning(
        "캔버스는 편집기입니다. Baseline 실행은 일반 물성·등엔트로피 효율 모델 결과이며, "
        "제조사 제품 선정·성능 검증·승인 결과가 아닙니다."
    )

    if "workbench_project" not in st.session_state:
        st.session_state.workbench_project = default_r744_project()
    stored_project = st.session_state.workbench_project
    if hasattr(stored_project, "model_dump"):
        project = WorkbenchProject.model_validate(stored_project.model_dump(mode="json"))
    else:
        project = WorkbenchProject.model_validate(stored_project)
    st.session_state.workbench_project = project
    _sync_project_history(project)

    with st.expander("자연어로 빠르게 구성 (선택)", expanded=False):
        _render_command_builder()
    project = st.session_state.workbench_project

    uploaded = st.sidebar.file_uploader("워크벤치 JSON 열기", type=["json"])
    if uploaded is not None:
        upload_bytes = uploaded.getvalue()
        upload_id = hashlib.sha256(upload_bytes).hexdigest()
        if st.session_state.get(_IMPORTED_UPLOAD_KEY) != upload_id:
            try:
                uploaded_project = load_project(upload_bytes)
                if _project_fingerprint(uploaded_project) != _project_fingerprint(project):
                    _invalidate_workbench_result()
                project = uploaded_project
                st.session_state.workbench_project = uploaded_project
                st.session_state[_IMPORTED_UPLOAD_KEY] = upload_id
                _sync_project_history(uploaded_project)
            except (ValidationError, ValueError) as error:
                st.sidebar.error("워크벤치 JSON 검증 실패")
                st.sidebar.text(str(error))
    else:
        st.session_state.pop(_IMPORTED_UPLOAD_KEY, None)
    _render_project_history_controls()
    if st.sidebar.button("기본 사이클로 초기화"):
        project = _basic_project(project.refrigerant)
        _clear_project_widget_state()
        _invalidate_workbench_result()
        st.session_state.workbench_project = project
        st.rerun()
    with st.sidebar.expander("새 빈 캔버스"):
        blank_refrigerant = st.selectbox(
            "냉매",
            ["R744", "R134a", "R410A"],
            key="workbench-blank-refrigerant",
        )
        if st.button("빈 캔버스 시작", use_container_width=True):
            project = _empty_project(cast(Literal["R744", "R134a", "R410A"], blank_refrigerant))
            _clear_project_widget_state()
            _invalidate_workbench_result()
            st.session_state.workbench_project = project
            st.rerun()

    project = _render_sidebar_component_editor(project)

    palette, canvas, properties = st.columns([1.5, 6.25, 2.25])
    with palette:
        project, selected_component_id = _render_palette(project)
        st.subheader("프로젝트")
        st.caption(
            f"냉매 {project.refrigerant} · 부품 {len(project.components)}개 · "
            f"연결 {len(project.connections)}개"
        )
    with canvas:
        st.subheader(project.title)
        project = _render_interactive_canvas(project, selected_component_id)
        issues = topology_issues(project)
        if issues:
            for issue in issues:
                st.error(issue)
        else:
            st.success("편집기 수준의 필수 부품·연결 검사를 통과했습니다.")
        st.caption("이 검사는 물리 feasibility, 용량 또는 제품 운전영역을 판정하지 않습니다.")
        with st.expander("부품과 연결 목록"):
            st.dataframe(
                [
                    {
                        "ID": component.component_id,
                        "종류": component.kind.value,
                        "이름": component.label,
                        "제품 모델": component.model_reference or "미지정",
                        "일반 계산 모델": (
                            getattr(component, "calculation_model", None)
                            or generic_calculation_model(component.kind)
                        )
                        or "편집 전용",
                    }
                    for component in project.components
                ],
                hide_index=True,
            )
            st.dataframe(
                [connection.model_dump() for connection in project.connections], hide_index=True
            )
        _render_connection_editor(project)
    with properties:
        st.subheader("설계조건")
        project = _render_condition_editor(project)
        st.session_state.workbench_project = project
        data = project_json(project)
        st.download_button(
            "워크벤치 JSON 저장",
            data=data,
            file_name=f"agent-hvac-{project.refrigerant.lower()}-workbench.json",
            mime="application/json",
            use_container_width=True,
        )
        st.caption("이 JSON은 편집 프로젝트이며 DesignSpecification 또는 solver 입력이 아닙니다.")

    st.divider()
    _render_services(project)


if __name__ == "__main__":
    main()
