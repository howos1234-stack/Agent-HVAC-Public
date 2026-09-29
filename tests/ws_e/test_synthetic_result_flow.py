import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

import agent_hvac.reporting.optimization_reports as optimization_reports
from agent_hvac.app.synthetic_flow import (
    SyntheticScenario,
    main,
    run_all_scenarios,
    run_synthetic_scenario,
)
from agent_hvac.reporting.optimization_reports import generate_optimization_report_bundle
from agent_hvac.schemas.design import DesignProblem
from agent_hvac.schemas.results import OptimizationResult

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def load_problem() -> DesignProblem:
    return DesignProblem.model_validate_json((FIXTURES / "design_problem_p09.json").read_bytes())


def test_documented_scenarios_preserve_status_rank_and_failure_reason() -> None:
    results = run_all_scenarios(load_problem())

    assert results[SyntheticScenario.NORMAL].status == "completed"
    assert len(results[SyntheticScenario.NORMAL].ranked_designs) == 5
    assert results[SyntheticScenario.INFEASIBLE].status == "infeasible"
    assert results[SyntheticScenario.INFEASIBLE].ranked_designs == ()
    assert results[SyntheticScenario.PARTIAL_SOLVER_FAILURE].status == "completed"
    assert len(results[SyntheticScenario.PARTIAL_SOLVER_FAILURE].ranked_designs) == 4
    assert any(
        "[solver-failure]" in message
        for message in results[SyntheticScenario.PARTIAL_SOLVER_FAILURE].messages
    )
    assert results[SyntheticScenario.ALL_SOLVER_FAILURE].status == "failed"
    assert results[SyntheticScenario.ALL_SOLVER_FAILURE].ranked_designs == ()
    assert results[SyntheticScenario.CANDIDATE_LIMIT].status == "failed"
    assert (
        "candidate count 5 exceeds limit 4"
        in results[SyntheticScenario.CANDIDATE_LIMIT].messages[0]
    )


def test_same_input_and_seed_reproduce_json_and_rank_order() -> None:
    problem = load_problem()
    first = run_synthetic_scenario(problem, SyntheticScenario.NORMAL)
    second = run_synthetic_scenario(problem, SyntheticScenario.NORMAL)

    assert first.model_dump_json() == second.model_dump_json()
    assert [item.design.design_id for item in first.ranked_designs] == [
        item.design.design_id for item in second.ranked_designs
    ]


def test_json_reload_and_html_preserve_provided_result_fields(tmp_path: Path) -> None:
    for scenario, result in run_all_scenarios(load_problem()).items():
        json_artifact, html_artifact = generate_optimization_report_bundle(
            result, tmp_path, scenario.value
        )
        reloaded = OptimizationResult.model_validate_json(Path(json_artifact.path).read_bytes())
        assert reloaded == result
        report = Path(html_artifact.path).read_text(encoding="utf-8")
        assert "MOCK ONLY" in report
        assert f"status: {result.status}" in report
        assert all(message in report for message in result.messages)
        if result.status == "completed":
            assert "RANKED MOCK CANDIDATES" in report
            assert result.ranked_designs[0].design.design_id in report
            assert "specified_pipe_length" in report
            assert "0.5 meter" in report
            assert "Master Plan section 22 example" in report
        else:
            assert "NO VALID OPTIMUM" in report
            assert "<td>1</td>" not in report
        assert "OptimizationResult에는 RunMetadata" in report


def test_cli_writes_five_json_html_pairs(tmp_path: Path, capsys) -> None:
    assert main((str(FIXTURES / "design_problem_p09.json"), str(tmp_path))) == 0
    output = capsys.readouterr().out
    assert len(list(tmp_path.glob("*.json"))) == 5
    assert len(list(tmp_path.glob("*.html"))) == 5
    assert all(scenario.value in output for scenario in SyntheticScenario)


def test_committed_normal_fixture_is_reproducible() -> None:
    expected = json.loads((FIXTURES / "optimization_result_p09.json").read_text(encoding="utf-8"))
    actual = run_synthetic_scenario(load_problem(), SyntheticScenario.NORMAL)
    assert actual.model_dump(mode="json") == expected


def test_optimization_html_escapes_failure_message(tmp_path: Path) -> None:
    result = OptimizationResult(
        status="failed",
        messages=('<script>alert("x")</script>',),
        is_mock=True,
    )
    _, html_artifact = generate_optimization_report_bundle(result, tmp_path, "escape")
    report = Path(html_artifact.path).read_text(encoding="utf-8")
    assert "<script>alert" not in report
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in report


def test_report_revalidates_nested_mutation_before_writing(tmp_path: Path) -> None:
    result = run_synthetic_scenario(load_problem(), SyntheticScenario.NORMAL)
    result.ranked_designs[0].simulation.state_points.clear()

    with pytest.raises(ValidationError, match="Converged result requires"):
        generate_optimization_report_bundle(result, tmp_path, "mutated")

    assert not list(tmp_path.iterdir())


def test_optimization_html_escapes_identifiers_and_provenance(tmp_path: Path) -> None:
    raw = json.loads((FIXTURES / "optimization_result_p09.json").read_text(encoding="utf-8"))
    candidate = raw["ranked_designs"][0]
    unsafe_id = '<img src=x onerror="alert(1)">'
    unsafe_source = '<script>alert("source")</script>'
    candidate["design"]["design_id"] = unsafe_id
    candidate["simulation"]["design_id"] = unsafe_id
    candidate["constraints"]["design_id"] = unsafe_id
    candidate["design"]["fixed"][0]["provenance"]["source_ref"] = unsafe_source
    result = OptimizationResult.model_validate(raw)

    _, html_artifact = generate_optimization_report_bundle(result, tmp_path, "html-special")
    report = Path(html_artifact.path).read_text(encoding="utf-8")

    assert unsafe_id not in report
    assert unsafe_source not in report
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in report
    assert "&lt;script&gt;alert(&quot;source&quot;)&lt;/script&gt;" in report


@pytest.mark.parametrize("artifact_names", [("run/a", "run?a"), ("...", "///")])
def test_distinct_unsafe_names_do_not_collide_or_escape(
    tmp_path: Path, artifact_names: tuple[str, str]
) -> None:
    result = run_synthetic_scenario(load_problem(), SyntheticScenario.NORMAL)
    bundles = [
        generate_optimization_report_bundle(result, tmp_path, name) for name in artifact_names
    ]
    paths = [Path(artifact.path) for bundle in bundles for artifact in bundle]

    assert len({path.name for path in paths}) == 4
    assert all(path.parent == tmp_path.resolve() for path in paths)
    assert all(path.exists() for path in paths)


def test_path_traversal_name_stays_inside_output_directory(tmp_path: Path) -> None:
    result = run_synthetic_scenario(load_problem(), SyntheticScenario.NORMAL)
    artifacts = generate_optimization_report_bundle(result, tmp_path, "../../outside")

    assert all(Path(artifact.path).parent == tmp_path.resolve() for artifact in artifacts)
    assert all(".." not in Path(artifact.path).name for artifact in artifacts)


def _changed_result() -> OptimizationResult:
    original = run_synthetic_scenario(load_problem(), SyntheticScenario.NORMAL)
    data = original.model_dump(mode="json")
    data["messages"].append("[storage-regression] updated bundle")
    return OptimizationResult.model_validate(data)


def _existing_bundle(tmp_path: Path) -> tuple[dict[str, Path], dict[Path, bytes]]:
    original = run_synthetic_scenario(load_problem(), SyntheticScenario.NORMAL)
    artifacts = generate_optimization_report_bundle(original, tmp_path, "storage-matrix")
    paths = {Path(artifact.path).suffix: Path(artifact.path) for artifact in artifacts}
    return paths, {path: path.read_bytes() for path in paths.values()}


def _assert_failed_bundle_state(
    tmp_path: Path,
    paths: dict[str, Path],
    original_bytes: dict[Path, bytes],
    updated: OptimizationResult,
    failed_suffix: str,
) -> None:
    expected_json = updated.model_dump_json(indent=2).encode("utf-8")
    if failed_suffix == ".json":
        assert paths[".json"].read_bytes() == original_bytes[paths[".json"]]
    else:
        assert paths[".json"].read_bytes() == expected_json
        assert paths[".json"].read_bytes() != original_bytes[paths[".json"]]
    assert paths[".html"].read_bytes() == original_bytes[paths[".html"]]
    assert set(tmp_path.iterdir()) == set(paths.values())


@pytest.mark.parametrize("failed_suffix", [".json", ".html"], ids=["json", "html"])
def test_replace_failure_is_independent_by_format_and_preserves_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failed_suffix: str
) -> None:
    paths, original_bytes = _existing_bundle(tmp_path)
    updated = _changed_result()
    original_replace = optimization_reports.os.replace
    temporary_paths: list[Path] = []

    def fail_selected_replace(source: os.PathLike[str], destination: os.PathLike[str]) -> None:
        temporary_paths.append(Path(source))
        if Path(destination).suffix == failed_suffix:
            raise OSError(f"MOCK {failed_suffix} replace failure")
        original_replace(source, destination)

    monkeypatch.setattr(optimization_reports.os, "replace", fail_selected_replace)
    artifacts = None

    with pytest.raises(OSError, match=f"MOCK {failed_suffix} replace failure"):
        artifacts = generate_optimization_report_bundle(updated, tmp_path, "storage-matrix")

    assert artifacts is None
    assert temporary_paths and all(not path.exists() for path in temporary_paths)
    _assert_failed_bundle_state(tmp_path, paths, original_bytes, updated, failed_suffix)


@pytest.mark.parametrize("failed_suffix", [".json", ".html"], ids=["json", "html"])
@pytest.mark.parametrize("partial_write", [False, True], ids=["before-write", "partial-write"])
def test_write_failure_is_independent_by_format_and_cleans_partial_temporary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failed_suffix: str,
    partial_write: bool,
) -> None:
    paths, original_bytes = _existing_bundle(tmp_path)
    updated = _changed_result()
    original_named_temporary_file = optimization_reports.tempfile.NamedTemporaryFile
    failed_call = 1 if failed_suffix == ".json" else 2
    temporary_paths: list[Path] = []
    failed_temporary_sizes: list[int] = []

    class SelectedWriteFailingTemporary:
        def __init__(self, *args, **kwargs) -> None:
            self._stream = original_named_temporary_file(*args, **kwargs)
            self._call = len(temporary_paths) + 1
            temporary_paths.append(Path(self._stream.name))

        def __enter__(self):
            self._stream = self._stream.__enter__()
            return self

        def __exit__(self, *args):
            return self._stream.__exit__(*args)

        @property
        def name(self) -> str:
            return self._stream.name

        def write(self, content: str) -> int:
            if self._call != failed_call:
                return self._stream.write(content)
            if partial_write:
                prefix_length = max(1, len(content) // 3)
                self._stream.write(content[:prefix_length])
                self._stream.flush()
            failed_temporary_sizes.append(Path(self.name).stat().st_size)
            raise OSError(f"MOCK {failed_suffix} write failure")

    monkeypatch.setattr(
        optimization_reports.tempfile,
        "NamedTemporaryFile",
        SelectedWriteFailingTemporary,
    )
    artifacts = None

    with pytest.raises(OSError, match=f"MOCK {failed_suffix} write failure"):
        artifacts = generate_optimization_report_bundle(updated, tmp_path, "storage-matrix")

    assert artifacts is None
    assert failed_temporary_sizes
    assert (failed_temporary_sizes[0] > 0) is partial_write
    assert all(not path.exists() for path in temporary_paths)
    _assert_failed_bundle_state(tmp_path, paths, original_bytes, updated, failed_suffix)
