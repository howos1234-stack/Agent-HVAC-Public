"""Deterministic JSON and HTML reports from the frozen final-package contract."""

# ruff: noqa: E501 -- Standalone HTML/CSS stays readable as its rendered source.

import argparse
import hashlib
import html
import json
import os
import re
import tempfile
from collections.abc import Iterable, Sequence
from pathlib import Path

from agent_hvac.reporting.generator import ReportArtifact
from agent_hvac.schemas.design import DecisionVariable, Objective
from agent_hvac.schemas.provenance import Parameter
from agent_hvac.schemas.results import FinalDesignPackage
from agent_hvac.utils.units import Quantity


def _validated(package: FinalDesignPackage) -> FinalDesignPackage:
    """Revalidate mutable nested containers before creating an artifact."""
    return FinalDesignPackage.model_validate_json(package.model_dump_json())


def _safe_run_id(run_id: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", run_id).strip("._-")
    digest = hashlib.sha256(run_id.encode("utf-8")).hexdigest()
    return f"{slug[:48] or 'report'}-{digest}"


def _artifact_path(output_dir: Path, run_id: str, suffix: str) -> Path:
    return (output_dir / f"agent-hvac-{_safe_run_id(run_id)}.{suffix}").resolve()


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
        ) as stream:
            stream.write(content)
            temporary = Path(stream.name)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _text(value: object) -> str:
    return html.escape(str(value), quote=True)


def _quantity(value: Quantity | None) -> str:
    return "미제공" if value is None else f"{value.value:g} {value.unit}"


def _table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    body = list(rows)
    if not body:
        return '<p class="empty">제공된 항목이 없습니다.</p>'
    headings = "".join(f"<th>{_text(header)}</th>" for header in headers)
    rendered_rows = "".join(
        "<tr>" + "".join(f"<td>{_text(cell)}</td>" for cell in row) + "</tr>" for row in body
    )
    return (
        f'<div class="table-wrap"><table><thead><tr>{headings}</tr></thead>'
        f"<tbody>{rendered_rows}</tbody></table></div>"
    )


def _parameter_rows(parameters: Iterable[Parameter]) -> list[tuple[object, ...]]:
    return [
        (
            parameter.name,
            _quantity(parameter.value)
            if isinstance(parameter.value, Quantity)
            else parameter.value,
            parameter.provenance.source_type,
            parameter.provenance.source_ref,
        )
        for parameter in parameters
    ]


def _decision_rows(variables: Iterable[DecisionVariable]) -> list[tuple[object, ...]]:
    return [
        (
            variable.name,
            _quantity(variable.lower),
            _quantity(variable.upper),
            variable.provenance.source_ref,
        )
        for variable in variables
    ]


def _objective_rows(objectives: Iterable[Objective]) -> list[tuple[object, ...]]:
    return [
        (objective.metric, objective.direction, objective.provenance.source_ref)
        for objective in objectives
    ]


def _render_html(package: FinalDesignPackage) -> str:
    selected = package.selected
    design = selected.design
    result = selected.simulation
    constraints = selected.constraints
    requirements = design.requirements
    banner = (
        "MOCK REPORT — 실제 HVAC 설계 또는 제품 성능 검증 자료가 아닙니다."
        if package.metadata.is_mock
        else "SERVICE RESULT REPORT — 보고서는 제공된 서비스 결과를 재계산하지 않습니다."
    )
    parameter_rows = _parameter_rows(
        (design.refrigerant, design.topology) + design.fixed + design.boundary_conditions
    )
    missing_rows = [(item.name, item.classification, item.reason) for item in requirements.missing]
    state_rows = [
        (
            name,
            state.fluid,
            _quantity(state.pressure),
            _quantity(state.temperature),
            _quantity(state.enthalpy),
            _quantity(state.density),
            state.phase,
            "미제공" if state.vapor_quality is None else f"{state.vapor_quality:g}",
        )
        for name, state in result.state_points.items()
    ]
    constraint_rows = [
        (
            check.rule_id,
            check.passed,
            check.hard,
            check.message,
            _quantity(check.margin),
        )
        for check in constraints.checks
    ]
    product_rows = [
        (
            product.component_type,
            product.manufacturer,
            product.model,
            product.status,
            ", ".join(product.supported_refrigerants),
            product.source.excel_file,
            product.source.sheet,
            product.source.row,
            product.source.document_ref,
            product.source.file_sha256,
        )
        for product in design.selected_products
    ]
    alternative_rows = [
        (
            alternative.design.design_id,
            _quantity(alternative.objective_value),
            alternative.simulation.status,
            alternative.constraints.feasible,
        )
        for alternative in package.alternatives
    ]
    design_constraint_rows = [
        (
            definition.rule_id,
            definition.parameter,
            definition.operator,
            _quantity(definition.limit),
            definition.hard,
            definition.provenance.source_ref,
        )
        for definition in design.constraints
    ]
    pressure_drop_rows = [(name, _quantity(value)) for name, value in result.pressure_drops.items()]
    duty_rows = [(name, _quantity(value)) for name, value in result.heat_exchanger_duties.items()]
    envelope_rows = [(name, _quantity(value)) for name, value in result.envelope_margins.items()]
    warning_items = "".join(f"<li>{_text(warning)}</li>" for warning in package.warnings)
    message_items = "".join(f"<li>{_text(message)}</li>" for message in result.messages)
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent-HVAC Report · {_text(package.metadata.run_id)}</title>
  <style>
    :root {{ color-scheme: light; --ink:#172033; --muted:#5c667a; --line:#dbe1ea;
      --paper:#fff; --panel:#f6f8fb; --accent:#176b87; --warn:#8a4b00; --warn-bg:#fff3d6; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:#edf1f5; color:var(--ink); font:15px/1.55 Arial, sans-serif; }}
    main {{ max-width:1100px; margin:32px auto; padding:36px; background:var(--paper);
      box-shadow:0 8px 28px #17203318; }}
    h1 {{ margin:0 0 4px; font-size:32px; }} h2 {{ margin-top:34px; border-bottom:2px solid var(--line); padding-bottom:7px; }}
    h3 {{ margin-top:24px; }} .subtitle,.empty,footer {{ color:var(--muted); }}
    .banner {{ margin:24px 0; padding:16px 18px; border:2px solid #df9c2f;
      background:var(--warn-bg); color:var(--warn); font-weight:700; }}
    .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; }}
    .card {{ padding:14px; background:var(--panel); border:1px solid var(--line); }}
    .card b {{ display:block; margin-top:4px; font-size:19px; }} blockquote {{ margin:0; padding:14px 18px;
      border-left:4px solid var(--accent); background:var(--panel); }}
    .table-wrap {{ overflow-x:auto; }} table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th,td {{ padding:9px 10px; border:1px solid var(--line); text-align:left; vertical-align:top; }}
    th {{ background:#eaf0f5; }} td {{ overflow-wrap:anywhere; }} code {{ font-size:12px; }}
    footer {{ margin-top:36px; padding-top:16px; border-top:1px solid var(--line); }}
    @media print {{ body {{ background:#fff; }} main {{ margin:0; box-shadow:none; max-width:none; }}
      h2,h3,.card,table {{ break-inside:avoid; }} }}
  </style>
</head>
<body><main>
  <header><h1>Agent-HVAC Engineering Report</h1>
    <div class="subtitle">Run {_text(package.metadata.run_id)} · Design {
        _text(design.design_id)
    }</div></header>
  <div class="banner">{_text(banner)}</div>
  <section><h2>1. 결과 요약</h2><div class="cards">
    <div class="card">냉매<b>{_text(design.refrigerant.value)}</b></div>
    <div class="card">토폴로지<b>{_text(design.topology.value)}</b></div>
    <div class="card">Solver 상태<b>{_text(result.status)}</b></div>
    <div class="card">COP [dimensionless]<b>{_text(result.cop)}</b></div>
    <div class="card">제약 feasible<b>{_text(constraints.feasible)}</b></div>
    <div class="card">승인 / release<b>{_text(package.approval_status)} / {
        _text(package.release_ready)
    }</b></div>
  </div></section>
  <section><h2>2. 사용자 요청과 요구사항</h2><blockquote>{
        _text(requirements.raw_prompt)
    }</blockquote>
    <h3>입력·설계값과 출처</h3>{_table(("항목", "값", "출처 유형", "출처"), parameter_rows)}
    <h3>미해결 입력</h3>{_table(("항목", "분류", "이유"), missing_rows)}</section>
  <section><h2>3. 설계 및 최적화 정의</h2>
    <h3>Decision variables</h3>{
        _table(("항목", "하한", "상한", "출처"), _decision_rows(design.decision_variables))
    }
    <h3>Objectives</h3>{_table(("지표", "방향", "출처"), _objective_rows(design.objectives))}
    <h3>설계 제약 정의</h3>{
        _table(
            ("규칙", "항목", "연산", "한계", "Hard", "출처"),
            design_constraint_rows,
        )
    }</section>
  <section><h2>4. 시스템 성능 및 잔차</h2>{
        _table(
            ("항목", "값"),
            (
                ("목적함수 값", _quantity(selected.objective_value)),
                ("COP [dimensionless]", result.cop),
                ("EER [dimensionless]", result.eer),
                ("질량유량", _quantity(result.mass_flow)),
                ("압축기 동력", _quantity(result.compressor_power)),
                ("증발기 용량", _quantity(result.evaporator_capacity)),
                ("열 방출량", _quantity(result.heat_rejection)),
                ("에너지 잔차 [dimensionless]", result.energy_balance_error),
                ("질량 잔차 [dimensionless]", result.mass_balance_error),
            ),
        )
    }
    <h3>압력손실</h3>{_table(("구간", "값"), pressure_drop_rows)}
    <h3>열교환기 duty</h3>{_table(("열교환기", "값"), duty_rows)}
    <h3>장비 운전범위 margin</h3>{_table(("항목", "값"), envelope_rows)}
    <h3>Active constraints</h3><p>{
        _text(", ".join(result.active_constraints) or "제공된 항목이 없습니다.")
    }</p>
    <h3>Solver 메시지</h3><ul>{message_items or '<li class="empty">메시지 없음</li>'}</ul></section>
  <section><h2>5. 상태점</h2>{
        _table(("상태점", "냉매", "p", "T", "h", "밀도", "상", "건도"), state_rows)
    }</section>
  <section><h2>6. 제약조건</h2>{
        _table(("규칙", "통과", "Hard", "메시지", "Margin"), constraint_rows)
    }</section>
  <section><h2>7. 선택 제품과 출처</h2>{
        _table(
            ("종류", "제조사", "모델", "상태", "냉매", "Excel", "Sheet", "Row", "문서", "SHA-256"),
            product_rows,
        )
    }</section>
  <section><h2>8. 대안 후보</h2>{
        _table(("설계 ID", "목적값", "Solver", "Feasible"), alternative_rows)
    }</section>
  <section><h2>9. 경고</h2><ul>{warning_items or '<li class="empty">경고 없음</li>'}</ul></section>
  <section><h2>10. 재현 메타데이터</h2>{
        _table(
            ("항목", "값"),
            (
                ("created_at", package.metadata.created_at.isoformat()),
                ("code_version", package.metadata.code_version),
                ("dependency_lock_sha256", package.metadata.dependency_lock_sha256),
                ("database_version", package.metadata.database_version),
                ("guideline_version", package.metadata.guideline_version),
                ("random_seed", package.metadata.random_seed),
                (
                    "solver_settings",
                    json.dumps(
                        package.metadata.solver_settings, ensure_ascii=False, sort_keys=True
                    ),
                ),
                ("is_mock", package.metadata.is_mock),
            ),
        )
    }</section>
  <footer>이 문서는 저장된 FinalDesignPackage를 표시합니다. 보고서 생성기는 물리 계산,
  제약 판정 또는 승인 상태 변경을 수행하지 않습니다.</footer>
</main></body></html>
"""


class JsonReportGenerator:
    """Persist the validated final package as a reproducible JSON archive."""

    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)

    def generate(self, package: FinalDesignPackage) -> ReportArtifact:
        validated = _validated(package)
        path = _artifact_path(self.output_dir, validated.metadata.run_id, "json")
        _atomic_write(path, validated.model_dump_json(indent=2))
        return ReportArtifact(
            path=str(path), media_type="application/json", is_mock=validated.metadata.is_mock
        )


class HtmlReportGenerator:
    """Create a standalone, escaped and print-friendly HTML report."""

    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)

    def generate(self, package: FinalDesignPackage) -> ReportArtifact:
        validated = _validated(package)
        path = _artifact_path(self.output_dir, validated.metadata.run_id, "html")
        _atomic_write(path, _render_html(validated))
        return ReportArtifact(
            path=str(path),
            media_type="text/html; charset=utf-8",
            is_mock=validated.metadata.is_mock,
        )


def generate_report_bundle(
    package: FinalDesignPackage, output_dir: str | Path
) -> tuple[ReportArtifact, ReportArtifact]:
    """Create JSON and HTML artifacts without changing the frozen service contract."""
    validated = _validated(package)
    return (
        JsonReportGenerator(output_dir).generate(validated),
        HtmlReportGenerator(output_dir).generate(validated),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Agent-HVAC JSON and HTML reports")
    parser.add_argument("input", type=Path, help="FinalDesignPackage JSON")
    parser.add_argument("output_dir", type=Path, help="Artifact output directory")
    args = parser.parse_args(argv)
    package = FinalDesignPackage.model_validate_json(args.input.read_bytes())
    for artifact in generate_report_bundle(package, args.output_dir):
        print(f"{artifact.media_type}: {artifact.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
