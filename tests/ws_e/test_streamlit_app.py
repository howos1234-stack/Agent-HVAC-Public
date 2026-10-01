import json
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from agent_hvac.app.streamlit_app import _saturation_dome  # noqa: E402
from agent_hvac.app.synthetic_flow import SyntheticScenario, run_synthetic_scenario  # noqa: E402
from agent_hvac.schemas.design import DesignProblem  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def render(data, kind="SimulationResult"):
    return AppTest.from_string(
        "from agent_hvac.app.streamlit_app import render_json\n"
        f"render_json({json.dumps(data)!r}, {kind!r})"
    ).run(timeout=20)


def render_raw(data, kind="SimulationResult"):
    return AppTest.from_string(
        f"from agent_hvac.app.streamlit_app import render_json\nrender_json({data!r}, {kind!r})"
    ).run(timeout=20)


def test_default_app_and_input_contract_switch():
    app = AppTest.from_file(str(ROOT / "src/agent_hvac/app/streamlit_app.py")).run(timeout=20)
    assert not app.exception
    assert any("MOCK" in w.value for w in app.warning)
    assert len(app.metric) == 3
    assert any("release_ready: False" in t.value for t in app.text)
    assert any("file_sha256" in element.value for element in app.json)
    assert len(app.get("download_button")) == 1
    assert len(app.button) == 0  # No simulated approval action.
    app.selectbox[0].select("SimulationResult").run()
    assert not app.exception
    assert any("ConstraintReport" in element.value for element in app.info)


def test_state_charts_render_ph_and_only_render_ts_when_entropy_is_present():
    data = json.loads(
        (ROOT / "tests/fixtures/simulation_result_r744.json").read_text(encoding="utf-8")
    )
    missing_entropy = render(data)
    assert len(missing_entropy.get("vega_lite_chart")) == 1
    assert any("엔트로피 데이터가 없습니다" in item.value for item in missing_entropy.info)

    for index, state in enumerate(data["state_points"].values()):
        state["entropy"] = {"value": 1_000.0 + index * 25.0, "unit": "J/(kg*K)"}
    with_entropy = render(data)
    assert not with_entropy.exception
    assert len(with_entropy.get("vega_lite_chart")) == 2
    assert not any("엔트로피 데이터가 없습니다" in item.value for item in with_entropy.info)
    assert sum("포화액선·포화증기선" in item.value for item in with_entropy.caption) == 2


def test_coolprop_saturation_dome_contains_liquid_and_vapor_boundaries():
    rows = _saturation_dome("R744", samples=12)

    assert len(rows) == 24
    assert {row["series"] for row in rows} == {"포화액선", "포화증기선"}
    assert all(float(row["p"]) > 0 for row in rows)
    assert all(float(row["temperature"]) > 0 for row in rows)
    assert _saturation_dome("NOT-A-REFRIGERANT", samples=12) == ()


@pytest.mark.parametrize(
    "status",
    ["unconverged", "infeasible", "invalid-property-state", "component-envelope-violation"],
)
def test_failure_hides_even_supplied_cop(status):
    data = json.loads(
        (ROOT / "tests/fixtures/simulation_result_r744.json").read_text(encoding="utf-8")
    )
    data.update(status=status, messages=["MOCK failure diagnostic"])
    app = render(data)
    assert not app.exception
    assert not app.metric
    assert app.error
    assert any("MOCK failure diagnostic" in t.value for t in app.text)
    assert len(app.get("download_button")) == 1


def test_invalid_input_has_no_result_or_download():
    app = render({"status": "converged"})
    assert not app.exception
    assert app.error
    assert not app.metric
    assert not app.get("download_button")


def test_mock_release_and_mismatched_ids_rejected():
    data = json.loads(
        (ROOT / "tests/fixtures/final_design_package.json").read_text(encoding="utf-8")
    )
    data["release_ready"] = True
    assert render(data, "FinalDesignPackage").error
    data["release_ready"] = False
    data["selected"]["constraints"]["design_id"] = "different-design"
    assert render(data, "FinalDesignPackage").error


def test_optimization_result_shows_rank_fixed_source_and_reproduction():
    data = json.loads(
        (ROOT / "tests/fixtures/optimization_result_p09.json").read_text(encoding="utf-8")
    )
    app = render(data, "OptimizationResult")
    assert not app.exception
    assert any("synthetic 탐색 결과" in warning.value for warning in app.warning)
    assert any("Optimization status: completed" in text.value for text in app.text)
    assert len(app.metric) == 1
    assert len(app.dataframe) == 2
    assert any("seed=73" in text.value for text in app.text)
    assert any("RunMetadata" in info.value for info in app.info)
    assert len(app.get("download_button")) == 1


@pytest.mark.parametrize(
    "scenario",
    [
        SyntheticScenario.INFEASIBLE,
        SyntheticScenario.ALL_SOLVER_FAILURE,
        SyntheticScenario.CANDIDATE_LIMIT,
    ],
)
def test_optimization_failure_never_shows_rank_or_metric(scenario):
    problem = DesignProblem.model_validate_json(
        (ROOT / "tests/fixtures/design_problem_p09.json").read_bytes()
    )
    result = run_synthetic_scenario(problem, scenario)
    app = render(result.model_dump(mode="json"), "OptimizationResult")
    assert not app.exception
    assert app.error
    assert not app.metric
    assert not app.dataframe
    assert any("후보 순위: 제공되지 않음" in info.value for info in app.info)
    assert len(app.get("download_button")) == 1


def test_partial_solver_failure_keeps_valid_ranks_and_failure_reason():
    problem = DesignProblem.model_validate_json(
        (ROOT / "tests/fixtures/design_problem_p09.json").read_bytes()
    )
    result = run_synthetic_scenario(problem, SyntheticScenario.PARTIAL_SOLVER_FAILURE)
    app = render(result.model_dump(mode="json"), "OptimizationResult")
    assert not app.exception
    assert len(app.metric) == 1
    assert len(app.dataframe) == 2
    assert any("[solver-failure]" in text.value for text in app.text)


def test_non_mock_optimization_result_is_rejected_before_display_or_export():
    data = json.loads(
        (ROOT / "tests/fixtures/optimization_result_p09.json").read_text(encoding="utf-8")
    )
    data["is_mock"] = False
    for candidate in data["ranked_designs"]:
        candidate["design"]["is_mock"] = False
        candidate["simulation"]["is_mock"] = False
        candidate["constraints"]["is_mock"] = False

    app = render(data, "OptimizationResult")

    assert not app.exception
    assert any("mock OptimizationResult 전용" in error.value for error in app.error)
    assert not app.warning
    assert not app.metric
    assert not app.dataframe
    assert not app.get("download_button")


def test_malformed_optimization_json_is_rejected_without_display_or_export():
    app = render_raw("{", "OptimizationResult")

    assert not app.exception
    assert any("입력 JSON 검증 실패" in error.value for error in app.error)
    assert not app.warning
    assert not app.metric
    assert not app.dataframe
    assert not app.get("download_button")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data.pop("is_mock"),
        lambda data: data["ranked_designs"][0]["simulation"].update(design_id="different-design"),
        lambda data: data["ranked_designs"][0]["constraints"].update(is_mock=False),
    ],
    ids=["missing-required", "id-mismatch", "mixed-mock"],
)
def test_invalid_optimization_contract_has_no_display_or_download(mutate):
    data = json.loads(
        (ROOT / "tests/fixtures/optimization_result_p09.json").read_text(encoding="utf-8")
    )
    mutate(data)

    app = render(data, "OptimizationResult")

    assert not app.exception
    assert any("입력 JSON 검증 실패" in error.value for error in app.error)
    assert not app.warning
    assert not app.metric
    assert not app.dataframe
    assert not app.get("download_button")
