"""Isolated screen workflow and real-result/failure presentation."""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from agent_hvac.solvers.system_cycle import analysis_manager  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "src/agent_hvac/app/analysis_screen_app.py"


def app():
    return AppTest.from_file(str(APP)).run(timeout=30)


def test_default_screen_and_candidate_preview():
    at = app()
    assert not at.exception
    assert any("SYNTHETIC" in w.value for w in at.warning)
    assert any("생성 후보 2개" in c.value for c in at.caption)
    assert not at.metric and not at.dataframe
    at.button(key="preview").click().run()
    assert not at.exception and len(at.dataframe) == 1
    assert len(at.dataframe[0].value) == 2
    assert len(at.get("download_button")) == 1


def test_budget_and_wrong_boundary_block_execution():
    at = app()
    at.number_input(key="budget").set_value(1).run()
    assert at.error and not at.button
    at.number_input(key="budget").set_value(20)
    at.number_input(key="room").set_value(-300).run()
    assert at.error and not at.button and not at.get("download_button")


def test_real_run_preserves_failure_and_input_change_invalidates_result():
    at = app()
    at.button(key="run").click().run(timeout=120)
    assert not at.exception
    bundle = at.session_state["analysis_bundle"]
    assert bundle["status"] == "COMPLETE"
    assert bundle["report"]["target_found"] is False
    rows = at.dataframe[0].value
    assert len(rows) == 2
    assert rows["냉방 W"].isna().sum() == 1
    assert len(bundle["completed_points"]) == 2
    assert bundle["metadata"]["compact_input"]["refrigerant_mass_flow"]["value"] == 0.05
    assert bundle["metadata"]["package_source_sha256"]
    assert len(at.get("download_button")) == 1
    at.number_input(key="load").set_value(0).run()
    assert not at.exception and at.error
    assert "analysis_bundle" not in at.session_state
    assert not at.dataframe and not at.get("download_button")


def test_real_target_match_is_distinct_from_room_control():
    at = app()
    at.checkbox(key="enable_discharge_pressure").uncheck()
    at.number_input(key="load").set_value(7608.861253860285).run()
    at.button(key="run").click().run(timeout=120)
    assert not at.exception and at.success
    assert at.session_state["analysis_bundle"]["report"]["target_found"]
    assert any("동적 온도 유지" in c.value for c in at.caption)


def test_unexpected_error_is_archived_without_success(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("deliberate GUI integration error")

    monkeypatch.setattr(analysis_manager, "run_analysis", broken)
    at = app()
    at.button(key="run").click().run(timeout=30)
    assert not at.exception and at.error and not at.success
    bundle = at.session_state["analysis_bundle"]
    assert bundle["status"] == "ERROR" and "report" not in bundle
    assert "deliberate GUI integration error" in bundle["error"]["message"]
    assert len(at.get("download_button")) == 1
    assert not at.metric


def test_input_change_clears_previous_candidate_preview():
    at = app()
    at.button(key="preview").click().run()
    assert at.dataframe
    at.number_input(key="mass").set_value(0.04).run()
    assert not at.dataframe and not at.get("download_button")


def test_invalid_source_is_not_assumed():
    at = app()
    at.text_input(key="source_ref").set_value("").run()
    assert at.error and not at.button


def test_expansion_is_downloadable_without_numerical_execution():
    at = app()
    at.button(key="preview").click().run()
    assert "analysis_bundle" not in at.session_state
    assert at.dataframe[0].value["후보"].tolist() == ["candidate-000", "candidate-001"]
    assert "합성" in at.title[0].value
