"""Isolated synthetic analysis GUI; run with streamlit, never imported by the solver."""

import hashlib
import importlib
import json
from typing import Any

from agent_hvac.app.analysis_screen import (
    bundle_json,
    candidate_rows,
    result_rows,
    run_metadata,
)
from agent_hvac.properties.coolprop_backend import CoolPropBackend
from agent_hvac.solvers.system_cycle.analysis_input import CompactAnalysisInput, expand_analysis
from agent_hvac.solvers.system_cycle.analysis_manager import AnalysisReport, run_analysis
from agent_hvac.solvers.system_cycle.design_study import DesignPoint

# Optional UI dependency. The deterministic package can still be checked/used without GUI extras.
st = importlib.import_module("streamlit")

FIELDS: dict[str, tuple[str, float, str]] = {
    "suction_pressure": ("흡입압력", 1.0, "MPa"),
    "discharge_pressure": ("토출압력", 3.5, "MPa"),
    "indoor_air_flow": ("실내 공기유량", 1.5, "kg/s"),
    "outdoor_air_flow": ("실외 공기유량", 0.8, "kg/s"),
    "condenser_ua": ("응축기 UA", 800.0, "W/K"),
    "evaporator_ua": ("증발기 UA", 800.0, "W/K"),
}


def quantity(value: float, unit: str) -> dict[str, Any]:
    return {"value": value, "unit": unit}


def collect_input() -> dict[str, Any]:
    st.subheader("1. 고정 요구조건")
    refrigerant = st.text_input("냉매", value="R410A", key="fluid")
    mass = st.number_input(
        "연속 냉매 유량 [kg/s]", value=0.05, min_value=0.0, format="%.5f", key="mass"
    )
    room = st.number_input("목표 실내 경계온도 [°C]", value=21.0, key="room")
    st.caption("21°C는 실내 경계조건입니다. 방의 도달시간·동적 온도 유지 계산은 포함하지 않습니다.")
    st.subheader("2. 환경과 부하")
    outdoor = st.number_input("외기온도 [°C]", value=35.0, key="outdoor")
    load = st.number_input("현열부하 [W]", value=3000.0, min_value=0.0, key="load")
    source = st.selectbox(
        "환경·부하 출처 유형", ["AGENT_ASSUMPTION", "USER", "HUMAN_CONFIRMED"], key="source_type"
    )
    source_ref = st.text_input(
        "환경·부하 출처", value="명시적 합성 시험값; 실측값 아님", key="source_ref"
    )
    st.subheader("3. 기준 설계조건")
    baseline = {}
    for name, (label, value, unit) in FIELDS.items():
        baseline[name] = quantity(
            float(st.number_input(f"{label} [{unit}]", value=value, min_value=0.0, key=name)),
            unit,
        )
    st.subheader("4. 변경을 허용한 범위")
    st.caption("체크한 변수만 탐색합니다. 입력 범위를 늘리거나 고정조건을 자동 변경하지 않습니다.")
    axes = []
    for name, (label, value, unit) in FIELDS.items():
        enabled = st.checkbox(
            f"{label} 탐색", value=name == "discharge_pressure", key=f"enable_{name}"
        )
        if enabled:
            low = 2.8 if name == "discharge_pressure" else value
            minimum = st.number_input(
                f"{label} 최소 [{unit}]", value=low, min_value=0.0, key=f"min_{name}"
            )
            maximum = st.number_input(
                f"{label} 최대 [{unit}]", value=value, min_value=0.0, key=f"max_{name}"
            )
            samples = st.number_input(
                f"{label} 표본 수",
                value=2 if low != value else 1,
                min_value=1,
                max_value=100,
                step=1,
                key=f"n_{name}",
            )
            axes.append(
                {
                    "name": name,
                    "minimum": quantity(float(minimum), unit),
                    "maximum": quantity(float(maximum), unit),
                    "samples": int(samples),
                    "authorization_ref": "사용자가 실행 전 지정한 화면의 허용 축",
                }
            )
    budget = st.number_input(
        "최대 계산 후보 수", value=20, min_value=1, max_value=100, step=1, key="budget"
    )
    with st.expander("수치 탐색구간과 합성 모델 가정", expanded=False):
        st.write(
            "합성 preset v1: 단열·길이0 배관, eta_is=0.75, 건식 공기 cp=1006 J/(kg K), "
            "병류 constant-UA HX 80 cells. 제조사 제품·전기 입력동력·습도 모델이 아닙니다."
        )
        lower_h = st.number_input("흡입 h 하한 [J/kg]", value=423500.0, key="lower_h")
        upper_h = st.number_input("흡입 h 상한 [J/kg]", value=450000.0, key="upper_h")
        valve_low = st.number_input("밸브 출구압력 하한 [MPa(a)]", value=1.0, key="valve_low")
        valve_high = st.number_input("밸브 출구압력 상한 [MPa(a)]", value=1.1, key="valve_high")
    return {
        "raw_requirement": "사용자가 화면에서 지정한 구조화 조건. 연속 유량과 실내 경계 유지.",
        "authorization_ref": "사용자가 실행 버튼으로 확인한 현재 화면의 조건과 허용 범위",
        "preset": "synthetic-condenser-v1",
        "refrigerant": refrigerant,
        "refrigerant_mass_flow": quantity(float(mass), "kg/s"),
        "room_temperature": quantity(float(room), "degC"),
        "outdoor_temperature": quantity(float(outdoor), "degC"),
        "sensible_load": quantity(float(load), "W"),
        "boundary_source_type": source,
        "boundary_source_ref": source_ref,
        "baseline": baseline,
        "lower_enthalpy": quantity(float(lower_h), "J/kg"),
        "upper_enthalpy": quantity(float(upper_h), "J/kg"),
        "valve_pressure_lower": quantity(float(valve_low), "MPa"),
        "valve_pressure_upper": quantity(float(valve_high), "MPa"),
        "axes": axes,
        "max_cases": int(budget),
    }


def render_report(report: AnalysisReport) -> None:
    st.subheader("해석 결과")
    if report.target_found:
        st.success("유한 후보에서 정상상태 목표부하 일치점을 찾았습니다.")
    else:
        st.warning(
            "지정한 후보에서 목표부하 일치점을 찾지 못했습니다. 전역 불가능 판정은 아닙니다."
        )
    st.dataframe(result_rows(report), hide_index=True)
    if report.closest_eligible_case_id:
        st.info(
            f"부하에 가장 가까운 유효 후보: {report.closest_eligible_case_id} "
            "(목표 달성 여부는 표의 별도 항목을 확인하세요.)"
        )
    for assessment in report.assessments:
        with st.expander(f"{assessment.case_id} · {assessment.outcome}"):
            st.write(assessment.next_action)
            st.write("기준 대비 변경:", list(assessment.changed_paths))
            for evidence in assessment.evidence:
                st.text(evidence)
    st.write("다음 검토 제안")
    for proposal in report.proposals:
        st.write(proposal)


def main() -> None:
    st.set_page_config(page_title="합성 HVAC 해석", layout="wide")
    st.title("합성 HVAC 조건 탐색")
    st.warning(
        "SYNTHETIC · DB 없는 정상상태 해석입니다. 제품 검증·Gate 승인·실내 동특성 완료가 아닙니다."
    )
    raw = collect_input()
    signature = hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()
    previous = st.session_state.get("analysis_signature")
    if previous != signature:
        had_result = "analysis_bundle" in st.session_state
        st.session_state.pop("analysis_bundle", None)
        st.session_state.pop("analysis_preview", None)
        st.session_state["analysis_signature"] = signature
        if had_result:
            st.info("입력이 변경되어 이전 결과를 숨겼습니다. 새 조건으로 다시 계산하세요.")
    try:
        compact = CompactAnalysisInput.model_validate(raw)
        expanded = expand_analysis(compact)
    except ValueError as exc:
        st.error(f"입력 확인이 필요합니다: {exc}")
        return
    st.caption(f"생성 후보 {compact.candidate_count}개 / 예산 {compact.max_cases}개")
    if st.button("후보 미리보기", key="preview"):
        st.session_state["analysis_preview"] = True
    if st.session_state.get("analysis_preview"):
        st.dataframe(candidate_rows(expanded), hide_index=True)
        st.download_button(
            "확장 입력 JSON",
            expanded.model_dump_json(indent=2),
            file_name="synthetic-expanded-input.json",
        )
    if st.button("해석 실행", key="run"):
        points: list[dict[str, Any]] = []
        # Replace the previous run before preparation can fail or Streamlit can stop.
        bundle: dict[str, Any] = {
            "status": "RUNNING",
            "input": compact.model_dump(mode="json"),
            "metadata": None,
            "completed_points": points,
        }
        st.session_state["analysis_bundle"] = bundle
        progress = st.empty()

        def record(point: DesignPoint) -> None:
            points.append(point.model_dump(mode="json"))
            progress.text(
                f"계산 중: {len(points)}/{compact.candidate_count} · {point.case.case_id}"
            )

        try:
            bundle["metadata"] = run_metadata(compact, expanded)
            report = run_analysis(CoolPropBackend(), expanded, on_point=record)
            bundle["report"] = report.model_dump(mode="json")
            bundle["status"] = "COMPLETE"
        except Exception as exc:
            bundle["status"] = "ERROR"
            bundle["error"] = {"type": type(exc).__name__, "message": str(exc)}
        progress.empty()
    bundle = st.session_state.get("analysis_bundle")
    if bundle:
        # A rerun can resume the UI after a Stop/Rerun interrupted the script.
        # Older sessions may also contain the pre-status partial bundle.
        if bundle.get("status") in (None, "RUNNING"):
            bundle["status"] = "ERROR"
            bundle["error"] = {
                "type": "InterruptedRun",
                "message": "이전 실행이 완료되기 전에 중단됐습니다. 다시 실행하세요.",
            }
        if bundle["status"] == "ERROR":
            st.error(f"계산 오류: {bundle['error']['type']}: {bundle['error']['message']}")
            st.info("성공으로 처리하지 않았습니다. 완료된 후보와 오류 기록을 내려받을 수 있습니다.")
        else:
            render_report(AnalysisReport.model_validate(bundle["report"]))
        st.download_button(
            "전체 실행 기록 JSON",
            bundle_json(bundle),
            file_name="synthetic-analysis-run.json",
            mime="application/json",
        )


if __name__ == "__main__":
    main()
