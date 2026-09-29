"""Generate clearly fictional P00 contract examples, never engineering reference values."""

import json
from pathlib import Path

from agent_hvac.schemas.components import ProductRecord
from agent_hvac.schemas.design import DesignSpecification
from agent_hvac.schemas.results import (
    ConstraintReport,
    FinalDesignPackage,
    OptimizationResult,
    SimulationResult,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
source = {"source_type": "AGENT_ASSUMPTION", "source_ref": "P00 synthetic fixture; NOT PHYSICS"}
user = {"source_type": "USER", "source_ref": "Master Plan section 22 example"}


def parameter(name, value, origin=source):
    return {"name": name, "value": value, "provenance": origin}


def product(kind):
    return {
        "product_id": f"MOCK-{kind}",
        "component_type": kind,
        "manufacturer": "FICTIONAL-P00",
        "model": f"MOCK-{kind}",
        "supported_refrigerants": ["R744"],
        "status": "unverified",
        "is_mock": True,
        "source": {
            "excel_file": "MOCK-NOT-A-REAL-WORKBOOK.xlsx",
            "sheet": "products",
            "row": 2,
            "document_ref": "P00 synthetic fixture; NO manufacturer evidence",
            "original_manufacturer": "FICTIONAL-P00",
            "original_model": f"MOCK-{kind}",
            "workbook_modified_at": "2026-09-09T00:00:00+09:00",
            "retrieved_at": "2026-09-09T00:00:00+09:00",
            "file_sha256": "0" * 64,
            "loader_version": "mock-only",
            "schema_version": "0.1.0",
        },
    }


compressor = product("compressor")
evaporator = product("evaporator")
fluid = parameter("refrigerant", "R744", user)
pipe = parameter("specified_pipe_length", {"value": 50, "unit": "cm"}, user)
design = {
    "design_id": "MOCK-r744",
    "is_mock": True,
    "requirements": {
        "raw_prompt": "냉매 R744, 지정 배관 길이 50 cm (P00 구조 예제)",
        "parameters": [fluid, pipe],
        "hitl_mode": "REVIEW",
        "missing": [
            {
                "name": "target_capacity",
                "classification": "essential",
                "reason": "Not supplied; P00 fixture does not resolve design requirements",
            }
        ],
    },
    "refrigerant": fluid,
    "topology": parameter("topology", "mock-single-stage"),
    "fixed": [pipe],
    "selected_products": [compressor, evaporator],
    "objectives": [{"metric": "cop", "direction": "maximize", "provenance": source}],
}
# These numbers only exercise serialization. They are not a solved state or cycle.
state = {
    "fluid": "R744",
    "pressure": {"value": 1, "unit": "MPa"},
    "temperature": {"value": 300, "unit": "K"},
    "enthalpy": {"value": 100, "unit": "kJ/kg"},
    "density": {"value": 1, "unit": "kg/m^3"},
    "phase": "mock-unspecified",
}
simulation = {
    "design_id": "MOCK-r744",
    "status": "converged",
    "is_mock": True,
    "state_points": {"example": state},
    "mass_flow": {"value": 1, "unit": "kg/s"},
    "compressor_power": {"value": 1, "unit": "W"},
    "evaporator_capacity": {"value": 1, "unit": "W"},
    "heat_rejection": {"value": 1, "unit": "W"},
    "cop": 1,
    "energy_balance_error": 1,
    "mass_balance_error": 1,
    "messages": ["MOCK ONLY: arbitrary placeholders; no physical convergence or validation"],
}
constraints = {
    "design_id": "MOCK-r744",
    "is_mock": True,
    "feasible": True,
    "checks": [
        {
            "rule_id": "MOCK",
            "passed": True,
            "hard": True,
            "message": "Synthetic contract check, not engineering validation",
        }
    ],
}
ranked = {
    "design": design,
    "simulation": simulation,
    "constraints": constraints,
    "objective_value": {"value": 1, "unit": "dimensionless"},
}
optimization = {"status": "completed", "ranked_designs": [ranked], "is_mock": True}
package = {
    "metadata": {
        "run_id": "MOCK-P00",
        "created_at": "2026-09-09T00:00:00+09:00",
        "code_version": "P00-mock",
        "dependency_lock_sha256": "0" * 64,
        "database_version": "mock-only",
        "guideline_version": "mock-only",
        "solver_settings": {"implemented": False},
        "is_mock": True,
    },
    "selected": ranked,
    "warnings": ["MOCK ONLY - NOT A VALIDATED HVAC DESIGN"],
    "approval_status": "pending",
    "release_ready": False,
}
records = {
    "compressor_product": (ProductRecord, compressor),
    "evaporator_product": (ProductRecord, evaporator),
    "design_spec_r744": (DesignSpecification, design),
    "simulation_result_r744": (SimulationResult, simulation),
    "constraint_report": (ConstraintReport, constraints),
    "optimization_result": (OptimizationResult, optimization),
    "final_design_package": (FinalDesignPackage, package),
}
for name, (schema, data) in records.items():
    validated = schema.model_validate_json(json.dumps(data))
    (FIXTURES / f"{name}.json").write_text(
        validated.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
print(f"Generated {len(records)} validated MOCK fixtures")
