import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_hvac.reporting.file_generators import (
    HtmlReportGenerator,
    JsonReportGenerator,
    generate_report_bundle,
    main,
)
from agent_hvac.reporting.generator import ReportGenerator
from agent_hvac.schemas.results import FinalDesignPackage

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "final_design_package.json"


def load_package() -> FinalDesignPackage:
    return FinalDesignPackage.model_validate_json(FIXTURE.read_bytes())


def test_generators_satisfy_frozen_protocol(tmp_path: Path) -> None:
    generators: tuple[ReportGenerator, ...] = (
        JsonReportGenerator(tmp_path),
        HtmlReportGenerator(tmp_path),
    )
    assert len(generators) == 2


def test_json_and_html_bundle_contains_mock_provenance_and_units(tmp_path: Path) -> None:
    json_artifact, html_artifact = generate_report_bundle(load_package(), tmp_path)
    assert json_artifact.media_type == "application/json"
    assert html_artifact.media_type == "text/html; charset=utf-8"
    assert json_artifact.is_mock is html_artifact.is_mock is True

    archived = FinalDesignPackage.model_validate_json(Path(json_artifact.path).read_bytes())
    assert archived == load_package()
    report = Path(html_artifact.path).read_text(encoding="utf-8")
    for expected in (
        "MOCK REPORT",
        "R744",
        "specified_pipe_length",
        "0.5 meter",
        "MOCK-NOT-A-REAL-WORKBOOK.xlsx",
        "Synthetic contract check",
        "에너지 잔차",
        "목적함수 값",
        "압력손실",
        "열교환기 duty",
        "장비 운전범위 margin",
        "설계 제약 정의",
        "dependency_lock_sha256",
        "pending / False",
    ):
        assert expected in report


def test_html_escapes_all_user_text(tmp_path: Path) -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["selected"]["design"]["requirements"]["raw_prompt"] = '<script>alert("x")</script>'
    package = FinalDesignPackage.model_validate(raw)
    artifact = HtmlReportGenerator(tmp_path).generate(package)
    report = Path(artifact.path).read_text(encoding="utf-8")
    assert "<script>alert" not in report
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in report


def test_generation_revalidates_mutable_nested_data_before_writing(tmp_path: Path) -> None:
    package = load_package()
    package.selected.simulation.state_points.clear()
    with pytest.raises(ValidationError):
        generate_report_bundle(package, tmp_path)
    assert not list(tmp_path.iterdir())


def test_run_id_cannot_escape_output_directory(tmp_path: Path) -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["metadata"]["run_id"] = "../../unsafe run"
    artifact = HtmlReportGenerator(tmp_path).generate(FinalDesignPackage.model_validate(raw))
    assert Path(artifact.path).parent == tmp_path.resolve()
    assert Path(artifact.path).name.startswith("agent-hvac-unsafe_run-")
    assert Path(artifact.path).suffix == ".html"


def test_cli_generates_both_artifacts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main((str(FIXTURE), str(tmp_path))) == 0
    output = capsys.readouterr().out
    assert "application/json" in output
    assert "text/html; charset=utf-8" in output
    assert {path.suffix for path in tmp_path.iterdir()} == {".json", ".html"}


@pytest.mark.parametrize(
    "run_ids",
    [
        ("run/a", "run?a"),
        ("설계", "검토"),
        ("RUN", "run"),
        ("a" * 300 + "1", "a" * 300 + "2"),
        ("...", "///"),
    ],
)
def test_distinct_runs_preserve_both_archives(tmp_path: Path, run_ids: tuple[str, str]) -> None:
    outputs = []
    for run_id in run_ids:
        raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
        raw["metadata"]["run_id"] = run_id
        outputs.append(generate_report_bundle(FinalDesignPackage.model_validate(raw), tmp_path))
    assert len(list(tmp_path.iterdir())) == 4
    for run_id, artifacts in zip(run_ids, outputs, strict=True):
        archived = FinalDesignPackage.model_validate_json(Path(artifacts[0].path).read_bytes())
        assert archived.metadata.run_id == run_id
        assert run_id in Path(artifacts[1].path).read_text(encoding="utf-8")
        assert all(len(Path(artifact.path).name) < 150 for artifact in artifacts)


def test_same_run_regeneration_replaces_only_its_artifacts(tmp_path: Path) -> None:
    package = load_package()
    original = generate_report_bundle(package, tmp_path)
    raw = package.model_dump(mode="json")
    raw["warnings"] = ["MOCK regenerated report"]
    updated = FinalDesignPackage.model_validate(raw)
    regenerated = generate_report_bundle(updated, tmp_path)
    assert regenerated == original
    assert len(list(tmp_path.iterdir())) == 2
    assert FinalDesignPackage.model_validate_json(Path(original[0].path).read_bytes()) == updated
    assert "MOCK regenerated report" in Path(original[1].path).read_text(encoding="utf-8")
