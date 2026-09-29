"""WS-E JSON/HTML presentation for the frozen P09 OptimizationResult contract."""

# ruff: noqa: E501 -- Standalone HTML/CSS stays readable as its rendered source.

from __future__ import annotations

import hashlib
import html
import os
import re
import tempfile
from collections.abc import Iterable, Sequence
from pathlib import Path

from agent_hvac.reporting.generator import ReportArtifact
from agent_hvac.schemas.provenance import Parameter
from agent_hvac.schemas.results import OptimizationResult
from agent_hvac.utils.units import Quantity


def _validated(result: OptimizationResult) -> OptimizationResult:
    return OptimizationResult.model_validate_json(result.model_dump_json())


def _safe_name(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._-")
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]
    return f"{slug[:48] or 'result'}-{digest}"


def _artifact_path(output_dir: Path, name: str, suffix: str) -> Path:
    return (output_dir / f"agent-hvac-p09-{_safe_name(name)}.{suffix}").resolve()


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _text(value: object) -> str:
    return html.escape(str(value), quote=True)


def _quantity(value: Quantity) -> str:
    return f"{value.value:g} {value.unit}"


def _parameter_value(parameter: Parameter) -> str:
    return _quantity(parameter.value) if isinstance(parameter.value, Quantity) else parameter.value


def _table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    body = list(rows)
    if not body:
        return '<p class="empty">제공된 항목이 없습니다.</p>'
    headings = "".join(f"<th>{_text(header)}</th>" for header in headers)
    rendered = "".join(
        "<tr>" + "".join(f"<td>{_text(cell)}</td>" for cell in row) + "</tr>" for row in body
    )
    return f"<table><thead><tr>{headings}</tr></thead><tbody>{rendered}</tbody></table>"


def _render_html(result: OptimizationResult) -> str:
    rank_rows = [
        (
            rank,
            candidate.design.design_id,
            _quantity(candidate.objective_value),
            candidate.simulation.status.value,
            candidate.constraints.feasible,
        )
        for rank, candidate in enumerate(result.ranked_designs, start=1)
    ]
    parameter_rows = [
        (
            rank,
            parameter.name,
            _parameter_value(parameter),
            parameter.provenance.source_type.value,
            parameter.provenance.source_ref,
        )
        for rank, candidate in enumerate(result.ranked_designs, start=1)
        for parameter in candidate.design.fixed + candidate.design.boundary_conditions
    ]
    product_rows = [
        (
            rank,
            product.component_type,
            product.manufacturer,
            product.model,
            product.source.document_ref,
            product.source.file_sha256,
        )
        for rank, candidate in enumerate(result.ranked_designs, start=1)
        for product in candidate.design.selected_products
    ]
    messages = "".join(f"<li>{_text(message)}</li>" for message in result.messages)
    outcome = (
        "RANKED MOCK CANDIDATES — 실제 HVAC 최적해 또는 제품 선정 결과가 아닙니다."
        if result.status == "completed"
        else "NO VALID OPTIMUM — 실패 결과를 정상 최적해로 표시하지 않습니다."
    )
    raw_json = result.model_dump_json(indent=2)
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Agent-HVAC P09 synthetic result</title>
<style>
body{{margin:0;background:#edf1f5;color:#172033;font:15px/1.5 Arial,sans-serif}}
main{{max-width:1100px;margin:28px auto;padding:32px;background:#fff}}
.banner{{padding:16px;border:2px solid #d98c00;background:#fff4d8;font-weight:700}}
.status{{font-size:24px;font-weight:700}} .empty,.note{{color:#5c667a}}
table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{border:1px solid #dbe1ea;padding:8px;text-align:left}}
th{{background:#eaf0f5}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f8fb;padding:16px}}
</style></head><body><main>
<h1>Agent-HVAC P09 Synthetic Optimization Result</h1>
<div class="banner">MOCK ONLY · {_text(outcome)}</div>
<p class="status">status: {_text(result.status)}</p><p>is_mock: {_text(result.is_mock)}</p>
<h2>후보 순위</h2>{_table(("rank", "design_id", "objective", "solver", "feasible"), rank_rows)}
<h2>실패·재현 메시지</h2><ul>{messages or '<li class="empty">제공된 메시지가 없습니다.</li>'}</ul>
<h2>고정값·경계조건과 출처</h2>{_table(("rank", "name", "value", "source_type", "source_ref"), parameter_rows)}
<h2>제품 출처</h2>{_table(("rank", "type", "manufacturer", "model", "document", "sha256"), product_rows)}
<h2>제공되지 않은 보고서 정보</h2><p class="note">OptimizationResult에는 RunMetadata,
승인 상태와 release 상태가 없습니다. 이 보고서는 해당 값을 생성하거나 FinalDesignPackage로
변환하지 않습니다.</p>
<details><summary>검증된 원문 JSON</summary><pre>{_text(raw_json)}</pre></details>
</main></body></html>"""


def generate_optimization_report_bundle(
    result: OptimizationResult, output_dir: str | Path, artifact_name: str
) -> tuple[ReportArtifact, ReportArtifact]:
    """Persist a validated P09 result without inventing final-package metadata."""
    if not artifact_name.strip():
        raise ValueError("artifact_name must be non-empty")
    validated = _validated(result)
    if not validated.is_mock:
        raise ValueError("P09 synthetic report requires a mock OptimizationResult")
    directory = Path(output_dir)
    json_path = _artifact_path(directory, artifact_name, "json")
    html_path = _artifact_path(directory, artifact_name, "html")
    _atomic_write(json_path, validated.model_dump_json(indent=2))
    _atomic_write(html_path, _render_html(validated))
    return (
        ReportArtifact(path=str(json_path), media_type="application/json", is_mock=True),
        ReportArtifact(path=str(html_path), media_type="text/html; charset=utf-8", is_mock=True),
    )
