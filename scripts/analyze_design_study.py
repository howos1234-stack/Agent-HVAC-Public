"""Reproducible analysis of explicit R410A study outputs; no new cycle equations."""

import argparse
import hashlib
import json
from pathlib import Path

from CoolProp.CoolProp import PropsSI

from agent_hvac.solvers.system_cycle.design_study import (
    DesignStudyRequest,
    DesignStudyResult,
    assess_fan_control,
)
from agent_hvac.utils.units import Power


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main", type=Path, required=True)
    parser.add_argument("--stability", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = [args.main, args.stability, args.candidate]
    if args.output.resolve() in {p.resolve() for p in paths}:
        raise ValueError("output must differ from study inputs")
    studies = [DesignStudyResult.model_validate_json(p.read_bytes()) for p in paths]
    if any(s.request.refrigerant != "R410A" for s in studies):
        raise ValueError("phase diagnostic is scoped to approved built-in R410A")
    points = tuple(p for s in studies for p in s.points)
    data = studies[0].request.model_dump(mode="json")
    data["cases"] = [p.case.model_dump(mode="json") for p in points]
    combined = DesignStudyResult(request=DesignStudyRequest.model_validate(data), points=points)
    rows = []
    for point in points:
        s = point.case.cycle_request.scenario
        c = point.cycle
        last = c.last_evaluation
        failures = list(
            dict.fromkeys(
                f"{p.failed_stage}: {p.message}"
                for h in c.history
                for p in h.pressure_history
                if p.failed_stage
            )
        )
        rows.append(
            {
                "case": point.case.case_id,
                "family": point.case.family,
                "cycle_converged": c.cycle_converged,
                "eligible": point.cooling_design_eligible,
                "load_matched": point.load_balance_satisfied,
                "ps_Pa": s.suction_pressure.value,
                "pd_Pa": s.discharge_pressure.value,
                "outdoor_K": s.high_side_hx.secondary_inlet_temperature.value,
                "indoor_air_kg_s": s.evaporator.secondary_mass_flow.value,
                "outdoor_air_kg_s": s.high_side_hx.secondary_mass_flow.value,
                "condenser_UA_W_K": s.high_side_hx.total_thermal_conductance.value,
                "evaporator_UA_W_K": s.evaporator.total_thermal_conductance.value,
                "HX_cells": s.evaporator.cell_count,
                "cooling_W": point.cooling.value if point.cooling else None,
                "supply_K": point.supply_temperature.value if point.supply_temperature else None,
                "load_residual_W": point.load_residual.value if point.load_residual else None,
                "air_balance_error_W": point.air_balance_error.value
                if point.air_balance_error
                else None,
                "COP": c.performance.cooling_cop if c.performance else None,
                "diagnostics": last.diagnostics.model_dump(mode="json")
                if last and last.diagnostics
                else None,
                "reason": c.reason,
                "failure_examples": failures,
            }
        )
    reference = "grid-p3.5-air1.5-ua800"
    best = min(
        (p for p in studies[0].points if p.cooling_design_eligible),
        key=lambda p: abs(p.load_residual.value),
    )
    # 101 samples per pressure axis are an explicit diagnostic resolution, not a proof
    # of monotonicity/absence of unsampled roots in a continuous EOS domain.
    ps_values = [p.case.cycle_request.scenario.suction_pressure.value for p in studies[0].points]
    pd_values = [p.case.cycle_request.scenario.discharge_pressure.value for p in studies[0].points]
    ps = [min(ps_values) + (max(ps_values) - min(ps_values)) * i / 100 for i in range(101)]
    pd = [min(pd_values) + (max(pd_values) - min(pd_values)) * i / 100 for i in range(101)]
    hg = [PropsSI("Hmass", "P", p, "Q", 1, "R410A") for p in ps]
    hf = [PropsSI("Hmass", "P", p, "Q", 0, "R410A") for p in pd]
    mass = combined.request.refrigerant_mass_flow.value
    phase = {
        "source": "CoolProp8.0.0 R410A built-in pseudo-pure, same EOS; not independent validation",
        "assumptions": [
            "adiabatic pipes",
            "isenthalpic valve",
            "liquid condenser outlet",
            "dry gas suction",
        ],
        "pressure_sampling": (
            "101 uniform samples per declared pressure interval; not a continuous proof"
        ),
        "ps_Pa": ps,
        "hg_J_kg": hg,
        "pd_Pa": pd,
        "hf_J_kg": hf,
        "minimum_hg_J_kg": min(hg),
        "maximum_hf_J_kg": max(hf),
        "sampled_phase_lower_bound_W": mass * (min(hg) - max(hf)),
        "requested_load_W": 3000,
        "required_outlet_h_at_min_hg_J_kg": min(hg) - 3000 / mass,
    }
    by_id = {r["case"]: r for r in rows}
    checks = []
    for ref, alt, tolerance, label in [
        (reference, "stability-alternative-h-bracket", 1e-5, "baseline-initial-bracket"),
        (reference, "stability-cells-160", 0.02, "baseline-80-to-160-cells"),
        (best.case.case_id, "candidate-alternative-h-bracket", 1e-5, "candidate-initial-bracket"),
        (best.case.case_id, "candidate-cells-160", 0.02, "candidate-80-to-160-cells"),
    ]:
        a, b = by_id[ref], by_id[alt]
        errors = (
            {key: abs(a[key] - b[key]) / abs(b[key]) for key in ["cooling_W", "COP"]}
            if a["eligible"] and b["eligible"]
            else None
        )
        checks.append(
            {
                "check": label,
                "reference": ref,
                "comparison": alt,
                "relative_tolerance": tolerance,
                "relative_errors": errors,
                "status": "PASS" if errors and max(errors.values()) <= tolerance else "FAIL",
            }
        )
    controls = {
        ref: [
            d.model_dump(mode="json")
            for d in assess_fan_control(
                combined, ref, tuple(Power(value=q, unit="W") for q in [2500, 3000, 3500])
            )
        ]
        for ref in [reference, best.case.case_id]
    }
    result = {
        "is_mock": True,
        "fixed": {
            "refrigerant": "R410A",
            "continuous_mass_flow_kg_s": mass,
            "room_temperature_K": combined.request.room_temperature.value,
        },
        "input_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        "counts": {
            "cases": len(rows),
            "converged": sum(p.cycle.cycle_converged for p in points),
            "eligible": sum(p.cooling_design_eligible for p in points),
            "load_matched": sum(p.load_balance_satisfied for p in points),
        },
        "main_counts": {
            "cases": len(studies[0].points),
            "converged": sum(p.cycle.cycle_converged for p in studies[0].points),
            "load_matched": sum(p.load_balance_satisfied for p in studies[0].points),
        },
        "best_declared_design_case": best.case.case_id,
        "cases": rows,
        "phase_diagnostic": phase,
        "numerical_sensitivity_checks": checks,
        "fan_control_assessment": controls,
        "control_scope": (
            "finite steady fan candidates only; duty is reference arithmetic rejected "
            "under continuous fixed-flow requirement; "
            "no transient/controller stability claim"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "counts": result["counts"],
                "best": result["best_declared_design_case"],
                "checks": checks,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
