"""A contract wiring test, not a physical or optimization validation."""

from agent_hvac.agents.tools import SimulateDesignInput, SimulateDesignOutput
from agent_hvac.database.repository import ComponentRepository
from agent_hvac.guidelines.rules import ConstraintEngine
from agent_hvac.optimization.optimizer import DesignOptimizer
from agent_hvac.reporting.generator import ReportArtifact, ReportGenerator
from agent_hvac.schemas.components import ComponentQuery, ProductRecord, ReloadSummary
from agent_hvac.schemas.design import DesignProblem, DesignSpecification
from agent_hvac.schemas.results import (
    ConstraintReport,
    FinalDesignPackage,
    OptimizationResult,
    SimulationResult,
)
from agent_hvac.solvers.base_cycle_solver import HVACSolver


def test_services_exchange_typed_contracts(fixture_data):
    design = DesignSpecification.model_validate(fixture_data("design_spec_r744"))
    package = FinalDesignPackage.model_validate(fixture_data("final_design_package"))

    class MockRepository:
        def search(self, query: ComponentQuery) -> list[ProductRecord]:
            return [
                p
                for p in design.selected_products
                if p.component_type == query.component_type
                and query.refrigerant in p.supported_refrigerants
            ]

        def reload(self) -> ReloadSummary:
            return ReloadSummary(
                valid_files=0, rejected_files=0, loaded_products=2, database_version="mock-only"
            )

    class MockSolver:
        def simulate(self, supplied: DesignSpecification) -> SimulationResult:
            assert supplied == design
            return SimulationResult.model_validate(fixture_data("simulation_result_r744"))

    class MockConstraints:
        def evaluate(
            self, supplied: DesignSpecification, result: SimulationResult
        ) -> ConstraintReport:
            assert supplied.design_id == result.design_id
            return ConstraintReport.model_validate(fixture_data("constraint_report"))

    class MockOptimizer:
        def optimize(self, problem: DesignProblem) -> OptimizationResult:
            assert problem.baseline == design
            return OptimizationResult.model_validate(fixture_data("optimization_result"))

    class MockReport:
        def generate(self, supplied: FinalDesignPackage) -> ReportArtifact:
            assert supplied.metadata.is_mock
            return ReportArtifact(
                path="MOCK-NOT-WRITTEN.html", media_type="text/html", is_mock=True
            )

    repository: ComponentRepository = MockRepository()
    solver: HVACSolver = MockSolver()
    constraints: ConstraintEngine = MockConstraints()
    optimizer: DesignOptimizer = MockOptimizer()
    report: ReportGenerator = MockReport()
    products = repository.search(ComponentQuery(component_type="compressor", refrigerant="R744"))
    assert products and all(p.is_mock for p in products)
    request = SimulateDesignInput(design=design)
    output = SimulateDesignOutput(result=solver.simulate(request.design))
    assert SimulateDesignOutput.model_validate_json(output.model_dump_json()) == output
    assert constraints.evaluate(design, output.result).is_mock
    assert optimizer.optimize(DesignProblem(baseline=design)).is_mock
    assert report.generate(package).is_mock
