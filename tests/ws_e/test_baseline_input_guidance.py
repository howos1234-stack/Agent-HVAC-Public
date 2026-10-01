from agent_hvac.app.baseline_input_guidance import baseline_guidance_checks, failure_explanation
from agent_hvac.app.design_workbench import default_r744_project, update_condition


def _messages(project):
    return [(item.level, item.message) for item in baseline_guidance_checks(project)]


def _complete_project():
    project = default_r744_project()
    project = update_condition(
        project, "refrigerant_mass_flow", value=0.1, unit="kg/s", source_ref="test"
    )
    return update_condition(
        project,
        "compressor_isentropic_efficiency",
        value=0.8,
        unit="dimensionless",
        source_ref="test",
    )


def test_complete_r744_example_reports_pressure_relation_and_transcritical_mode():
    messages = _messages(_complete_project())
    assert ("pass", "고압측 압력이 저압측보다 높습니다.") in messages
    assert any("gas-cooling" in message for _, message in messages)


def test_guidance_flags_reversed_pressures_without_changing_values():
    project = update_condition(
        _complete_project(), "high_side_pressure", value=20.0, unit="bar(a)", source_ref="test"
    )
    messages = _messages(project)
    assert any(level == "error" and "고압측 압력" in message for level, message in messages)
    condition = next(item for item in project.conditions if item.name == "high_side_pressure")
    assert condition.value == 20.0


def test_guidance_flags_liquid_or_two_phase_compressor_inlet():
    project = update_condition(
        _complete_project(),
        "compressor_inlet_temperature",
        value=-20.0,
        unit="degC",
        source_ref="test",
    )
    assert any("액·2상 유입" in message for _, message in _messages(project))


def test_incomplete_project_requests_remaining_inputs():
    project = default_r744_project().model_copy(update={"conditions": ()})
    assert _messages(project) == [
        ("info", "필수값을 모두 입력하면 냉매 상태 기반 점검을 표시합니다.")
    ]


def test_negative_mass_flow_and_efficiency_are_explicit_errors():
    project = update_condition(
        _complete_project(), "refrigerant_mass_flow", value=-0.1, unit="kg/s", source_ref="test"
    )
    project = update_condition(
        project,
        "compressor_isentropic_efficiency",
        value=-0.8,
        unit="dimensionless",
        source_ref="test",
    )
    messages = _messages(project)
    assert any(level == "error" and "질량유량" in message for level, message in messages)
    assert any(level == "error" and "등엔트로피 효율" in message for level, message in messages)


def test_failure_explanation_translates_known_capacity_failure_to_actions():
    explanation, actions = failure_explanation(("evaporator capacity must be positive",))
    assert "열을 흡수" in explanation
    assert any("고압측 압력" in action for action in actions)
    assert any("출구온도" in action for action in actions)


def test_unknown_failure_keeps_safe_generic_recovery_steps():
    explanation, actions = failure_explanation(("unexpected synthetic failure",))
    assert "완료하지 못했습니다" in explanation
    assert any("원문 사유" in action for action in actions)
