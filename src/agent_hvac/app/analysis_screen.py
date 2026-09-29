"""Display/archival helpers for the isolated synthetic analysis screen (no GUI imports)."""

import hashlib
import json
import platform
from importlib.metadata import version
from pathlib import Path
from typing import Any

from agent_hvac.solvers.system_cycle.analysis_input import CompactAnalysisInput
from agent_hvac.solvers.system_cycle.analysis_manager import AnalysisReport, AnalysisRequest


def candidate_rows(request: AnalysisRequest) -> list[dict[str, Any]]:
    return [
        {
            "후보": c.case_id,
            "흡입압력 Pa(a)": c.cycle_request.scenario.suction_pressure.value,
            "토출압력 Pa(a)": c.cycle_request.scenario.discharge_pressure.value,
            "실내풍량 kg/s": c.cycle_request.scenario.evaporator.secondary_mass_flow.value,
            "실외풍량 kg/s": c.cycle_request.scenario.high_side_hx.secondary_mass_flow.value,
            "증발 UA W/K": c.cycle_request.scenario.evaporator.total_thermal_conductance.value,
            "응축 UA W/K": c.cycle_request.scenario.high_side_hx.total_thermal_conductance.value,
        }
        for c in request.study.cases
    ]


def result_rows(report: AnalysisReport) -> list[dict[str, Any]]:
    report = AnalysisReport.model_validate_json(report.model_dump_json())
    return [
        {
            "후보": p.case.case_id,
            "판정": a.outcome,
            "회로 수렴": p.cycle.cycle_converged,
            "냉방 설계 적합": p.cooling_design_eligible,
            "목표부하 일치": p.load_balance_satisfied,
            "냉방 W": p.cooling.value if p.cooling else None,
            "부하 차이 W": p.load_residual.value if p.load_residual else None,
            "COP": p.cycle.performance.cooling_cop if p.cycle.performance else None,
            "원인": p.cycle.reason,
        }
        for p, a in zip(report.study_result.points, report.assessments, strict=True)
    ]


def run_metadata(compact: CompactAnalysisInput, expanded: AnalysisRequest) -> dict[str, Any]:
    """Archive actual installed package bytes; usable outside a Git checkout."""
    package = Path(__file__).resolve().parents[1]
    paths = sorted(package.rglob("*.py")) + sorted(
        (package / "solvers/system_cycle/presets").glob("*.json")
    )
    return {
        "is_mock": True,
        "db": None,
        "python": platform.python_version(),
        "coolprop": version("CoolProp"),
        "package_version": version("agent-hvac"),
        "compact_input": compact.model_dump(mode="json"),
        "expanded_request": expanded.model_dump(mode="json"),
        "input_sha256": hashlib.sha256(compact.model_dump_json().encode()).hexdigest(),
        "package_source_sha256": {
            p.relative_to(package).as_posix(): hashlib.sha256(
                p.read_bytes().replace(b"\r\n", b"\n")
            ).hexdigest()
            for p in paths
        },
    }


def bundle_json(bundle: dict[str, Any]) -> str:
    return json.dumps(bundle, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
