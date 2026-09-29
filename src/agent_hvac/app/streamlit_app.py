"""P12 mock-first results viewer. Run with Streamlit; never imported by core."""

from pathlib import Path

import streamlit as st
from pydantic import ValidationError

from agent_hvac.app.result_view import (
    Artifact,
    ArtifactKind,
    export_artifact,
    optimization_rows,
    parse_artifact,
    quantity_text,
    state_rows,
)
from agent_hvac.schemas.results import (
    FinalDesignPackage,
    OptimizationResult,
    RankedDesign,
    SolverStatus,
)


def _parameter_rows(candidate: RankedDesign) -> list[dict[str, str]]:
    design = candidate.design
    return [
        {
            "is_mock": str(design.is_mock).lower(),
            "항목": parameter.name,
            "값": quantity_text(parameter.value)
            if not isinstance(parameter.value, str)
            else parameter.value,
            "출처 유형": parameter.provenance.source_type.value,
            "출처": parameter.provenance.source_ref,
        }
        for parameter in design.fixed + design.boundary_conditions
    ]


def render_optimization_result(result: OptimizationResult) -> None:
    if not result.is_mock:
        st.error(
            "입력 거부 · 이 P09→P12 화면은 mock OptimizationResult 전용입니다. "
            "non-mock 결과를 표시하거나 내보내지 않습니다."
        )
        return
    st.subheader(f"P09 최적화 결과 · {result.status}")
    st.warning("MOCK · synthetic 탐색 결과입니다. 실제 HVAC 최적화·제품 검증 결과가 아닙니다.")
    st.text(f"Optimization status: {result.status}")
    for message in result.messages:
        st.text(message)
    if result.status != "completed":
        st.error("유효한 최적해가 없습니다. 실패 결과를 정상 후보나 성능 카드로 표시하지 않습니다.")
        st.info("후보 순위: 제공되지 않음")
    else:
        st.subheader("후보 순위")
        st.dataframe(optimization_rows(result), hide_index=True)
        selected = result.ranked_designs[0]
        st.metric(
            "1위 목적함수 · MOCK",
            quantity_text(selected.objective_value),
        )
        st.subheader("1위 후보 고정값·경계조건과 출처")
        st.dataframe(_parameter_rows(selected), hide_index=True)
        st.subheader("1위 후보 제품 출처")
        if not selected.design.selected_products:
            st.info("선택된 제품이 없습니다.")
        for product in selected.design.selected_products:
            st.text(f"{product.manufacturer} / {product.model} · {product.status}")
            st.json(product.source.model_dump(mode="json"))
    st.subheader("재현 정보")
    st.caption("seed·search version·평가/탈락 수는 P09가 제공한 메시지를 그대로 표시합니다.")
    st.info(
        "OptimizationResult에는 RunMetadata·승인·release 정보가 없습니다. "
        "GUI는 해당 값을 생성하거나 FinalDesignPackage로 변환하지 않습니다."
    )
    data = export_artifact(result)
    st.download_button(
        "MOCK OptimizationResult JSON 다운로드",
        data=data,
        file_name="MOCK-p09-optimization-result.json",
        mime="application/json",
    )
    with st.expander("JSON 미리보기"):
        st.code(data, language="json")


def render_artifact(artifact: Artifact) -> None:
    if isinstance(artifact, OptimizationResult):
        render_optimization_result(artifact)
        return
    package = artifact if isinstance(artifact, FinalDesignPackage) else None
    result = package.selected.simulation if package else artifact
    # Narrow explicitly for static checking without introducing a second schema.
    if isinstance(result, FinalDesignPackage):
        raise TypeError("Expected simulation")
    st.subheader(f"결과 · {result.design_id}")
    if result.is_mock:
        st.warning("MOCK · 합성 데이터입니다. 실제 물리 수렴·성능·제품 검증 결과가 아닙니다.")
    else:
        st.info("서비스 제공 결과 · 이 화면은 물리 정확성이나 배포 승인을 검증하지 않습니다.")
    st.text(f"Solver status: {result.status.value}")
    for message in result.messages:
        st.text(message)
    if result.status == SolverStatus.CONVERGED:
        columns = st.columns(3)
        columns[0].metric("COP [dimensionless]" + (" · MOCK" if result.is_mock else ""), result.cop)
        columns[1].metric("증발기 용량", quantity_text(result.evaporator_capacity))
        columns[2].metric("압축기 동력", quantity_text(result.compressor_power))
        st.text(f"열 방출량: {quantity_text(result.heat_rejection)}")
        st.text(f"질량유량: {quantity_text(result.mass_flow)}")
    else:
        st.error("실패 결과 · 성능 카드를 표시하지 않습니다. 아래 상태값은 진단용입니다.")
    st.text(f"에너지 잔차 [dimensionless]: {result.energy_balance_error}")
    st.text(f"질량 잔차 [dimensionless]: {result.mass_balance_error}")
    st.caption("서비스가 제공한 잔차이며, GUI는 허용오차나 합격 여부를 판정하지 않습니다.")

    states, constraints, sources, archive = st.tabs(
        ["상태점", "제약", "설계·출처", "JSON 내보내기"]
    )
    with states:
        rows = state_rows(result)
        if rows:
            st.dataframe(rows, hide_index=True)
            st.subheader("P-h 상태점")
            st.vega_lite_chart(
                [
                    {"h": state.enthalpy.value, "p": state.pressure.value}
                    for state in result.state_points.values()
                ],
                {
                    "title": "MOCK · P-h states" if result.is_mock else "P-h states",
                    "mark": "point",
                    "encoding": {
                        "x": {"field": "h", "type": "quantitative", "title": "h [J/kg]"},
                        "y": {"field": "p", "type": "quantitative", "title": "p [Pa, absolute]"},
                    },
                },
            )
            st.caption("제공된 점만 표시합니다. 사이클 경로·포화선은 추정하지 않습니다.")
        else:
            st.info("제공된 상태점이 없습니다.")
        st.info("T-s 그래프 대기 · 엔트로피 데이터가 제공되지 않았습니다.")
        st.json(
            {
                "pressure_drops": {k: v.model_dump() for k, v in result.pressure_drops.items()},
                "heat_exchanger_duties": {
                    k: v.model_dump() for k, v in result.heat_exchanger_duties.items()
                },
            }
        )
    with constraints:
        if package:
            report = package.selected.constraints
            st.text(f"서비스 feasibility: {report.feasible}")
            st.dataframe(
                [
                    {
                        "is_mock": str(report.is_mock).lower(),
                        "규칙": c.rule_id,
                        "passed": c.passed,
                        "hard": c.hard,
                        "메시지": c.message,
                        "margin": quantity_text(c.margin),
                    }
                    for c in report.checks
                ],
                hide_index=True,
            )
        else:
            st.info("SimulationResult 단독 입력에는 ConstraintReport가 포함되지 않습니다.")
        st.json(
            {
                "active_constraints": result.active_constraints,
                "envelope_margins": {k: v.model_dump() for k, v in result.envelope_margins.items()},
            }
        )
    with sources:
        if package:
            design = package.selected.design
            st.text(f"냉매: {design.refrigerant.value} · 토폴로지: {design.topology.value}")
            st.text(design.requirements.raw_prompt)
            st.subheader("입력값과 출처")
            st.dataframe(
                [
                    {
                        "is_mock": str(design.is_mock).lower(),
                        "항목": p.name,
                        "값": quantity_text(p.value)
                        if not isinstance(p.value, (str, bool))
                        else str(p.value),
                        "출처": p.provenance.source_ref,
                    }
                    for p in (design.refrigerant, design.topology)
                    + design.fixed
                    + design.boundary_conditions
                ],
                hide_index=True,
            )
            with st.expander("설계 원본 · 누락값과 변수 범위"):
                st.json(design.model_dump(mode="json"))
            st.subheader("선택 제품 출처")
            if not design.selected_products:
                st.info("선택된 제품이 없습니다.")
            for product in design.selected_products:
                st.text(f"{product.manufacturer} / {product.model} · {product.status}")
                st.json(product.source.model_dump(mode="json"))
            st.subheader("실행 메타데이터")
            st.json(package.metadata.model_dump(mode="json"))
            for warning in package.warnings:
                st.warning(warning)
            st.text(
                f"승인 상태: {package.approval_status} · release_ready: {package.release_ready}"
            )
        else:
            st.info("설계·제품·실행 출처는 FinalDesignPackage 입력에서 확인할 수 있습니다.")
        st.info("승인 기능 준비 중 · 현재 화면에서는 승인 상태를 변경할 수 없습니다.")
    with archive:
        st.caption("입력 결과와 MOCK 표시를 보존합니다. 보고서 생성 기능은 준비 중입니다.")
        data = export_artifact(artifact)
        st.download_button(
            "MOCK JSON 다운로드" if result.is_mock else "결과 JSON 다운로드",
            data=data,
            file_name="MOCK-result.json" if result.is_mock else "result.json",
            mime="application/json",
        )
        with st.expander("JSON 미리보기"):
            st.code(data, language="json")


def render_json(data: str | bytes, kind: ArtifactKind) -> None:
    try:
        artifact = parse_artifact(data, kind)
    except (ValidationError, ValueError) as error:
        st.error("입력 JSON 검증 실패 · 결과를 표시하거나 내보내지 않습니다.")
        st.text(str(error))
        return
    render_artifact(artifact)


def main() -> None:
    st.set_page_config(page_title="Agent-HVAC · 결과", layout="wide")
    st.title("Agent-HVAC")
    st.caption("WS-E / P12 · 서비스 결과 뷰어")
    kind: ArtifactKind = st.sidebar.selectbox(
        "입력 계약", ["FinalDesignPackage", "SimulationResult", "OptimizationResult"]
    )
    uploaded = st.sidebar.file_uploader("결과 JSON 열기", type=["json"])
    if uploaded is not None:
        render_json(uploaded.getvalue(), kind)
        return
    names = {
        "FinalDesignPackage": "final_design_package.json",
        "SimulationResult": "simulation_result_r744.json",
        "OptimizationResult": "optimization_result_p09.json",
    }
    name = names[kind]
    fixture = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / name
    st.sidebar.caption("파일을 열기 전에는 저장소의 P00 MOCK 예제를 표시합니다.")
    try:
        data = fixture.read_bytes()
    except OSError as error:
        st.error("예제 파일을 읽을 수 없습니다. 결과 JSON을 열어주세요.")
        st.text(str(error))
        return
    render_json(data, kind)


if __name__ == "__main__":
    main()
