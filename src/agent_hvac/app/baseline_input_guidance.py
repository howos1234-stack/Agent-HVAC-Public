"""Beginner guidance for the app-private baseline cycle inputs."""

from __future__ import annotations

from dataclasses import dataclass

from CoolProp.CoolProp import PropsSI

from agent_hvac.app.design_workbench import WorkbenchProject, condition_for_parameter


@dataclass(frozen=True)
class GuidanceCheck:
    level: str
    message: str


EXAMPLE_CONDITIONS: dict[str, str] = {
    "R134a": "3 / 12 bar(a), 흡입 10 °C, 응축기 출구 35 °C, 0.05 kg/s, 효율 0.75",
    "R410A": "8 / 25 bar(a), 흡입 10 °C, 응축기 출구 35 °C, 0.05 kg/s, 효율 0.75",
    "R744": "30 / 90 bar(a), 흡입 6.85 °C, gas cooler 출구 36.85 °C, 0.10 kg/s, 효율 0.80",
}


def _pressure_pa(value: float, unit: str) -> float:
    normalized = unit.strip().lower().replace(" ", "")
    factors = {
        "pa": 1.0,
        "kpa": 1_000.0,
        "mpa": 1_000_000.0,
        "bar": 100_000.0,
        "bar(a)": 100_000.0,
        "bara": 100_000.0,
    }
    if normalized not in factors:
        raise ValueError("압력은 Pa, kPa, MPa, bar, bar(a), bara 중 하나를 사용하세요.")
    return value * factors[normalized]


def _temperature_k(value: float, unit: str) -> float:
    normalized = unit.strip().lower().replace("°", "deg")
    if normalized in {"k", "kelvin"}:
        return value
    if normalized in {"c", "degc", "celsius"}:
        return value + 273.15
    raise ValueError("온도는 K 또는 °C(degC)를 사용하세요.")


def baseline_guidance_checks(project: WorkbenchProject) -> tuple[GuidanceCheck, ...]:
    """Return explanatory checks without changing any user value."""
    names = (
        "evaporator_pressure",
        "high_side_pressure",
        "compressor_inlet_temperature",
        "heat_rejection_outlet_temperature",
        "refrigerant_mass_flow",
        "compressor_isentropic_efficiency",
    )
    conditions = {name: condition_for_parameter(project, name) for name in names}
    if any(value is None for value in conditions.values()):
        return (GuidanceCheck("info", "필수값을 모두 입력하면 냉매 상태 기반 점검을 표시합니다."),)

    try:
        low = conditions["evaporator_pressure"]
        high = conditions["high_side_pressure"]
        suction = conditions["compressor_inlet_temperature"]
        outlet = conditions["heat_rejection_outlet_temperature"]
        flow = conditions["refrigerant_mass_flow"]
        efficiency = conditions["compressor_isentropic_efficiency"]
        assert low and high and suction and outlet and flow and efficiency
        low_pa = _pressure_pa(low.value, low.unit)
        high_pa = _pressure_pa(high.value, high.unit)
        suction_k = _temperature_k(suction.value, suction.unit)
        outlet_k = _temperature_k(outlet.value, outlet.unit)
    except (AssertionError, ValueError) as error:
        return (GuidanceCheck("error", str(error)),)

    checks: list[GuidanceCheck] = []
    if low_pa <= 0 or high_pa <= 0:
        checks.append(GuidanceCheck("error", "절대압력은 0보다 커야 합니다."))
    elif high_pa <= low_pa:
        checks.append(GuidanceCheck("error", "고압측 압력은 증발·저압측 압력보다 커야 합니다."))
    else:
        checks.append(GuidanceCheck("pass", "고압측 압력이 저압측보다 높습니다."))
    if suction_k <= 0 or outlet_k <= 0:
        checks.append(GuidanceCheck("error", "절대온도 0 K 이하의 온도는 사용할 수 없습니다."))
    if flow.value <= 0:
        checks.append(GuidanceCheck("error", "냉매 질량유량은 0보다 커야 합니다."))
    maximum_efficiency = 100.0 if efficiency.unit in {"%", "percent"} else 1.0
    if not 0 < efficiency.value <= maximum_efficiency:
        checks.append(
            GuidanceCheck("error", "등엔트로피 효율은 0 초과 1 이하(또는 0–100%)여야 합니다.")
        )

    if not any(item.level == "error" for item in checks):
        try:
            critical_pressure = float(PropsSI("pcrit", project.refrigerant))
            if low_pa < critical_pressure:
                low_saturation = float(PropsSI("T", "P", low_pa, "Q", 1, project.refrigerant))
                superheat = suction_k - low_saturation
                if superheat < 0:
                    checks.append(
                        GuidanceCheck(
                            "warning",
                            f"압축기 흡입이 포화증기온도보다 {abs(superheat):.1f} K 낮아 "
                            "액·2상 유입 가능성이 있습니다.",
                        )
                    )
                else:
                    checks.append(
                        GuidanceCheck("pass", f"흡입 과열도 참고값은 약 {superheat:.1f} K입니다.")
                    )
            if high_pa < critical_pressure:
                high_saturation = float(PropsSI("T", "P", high_pa, "Q", 0, project.refrigerant))
                subcooling = high_saturation - outlet_k
                if subcooling < 0:
                    checks.append(
                        GuidanceCheck(
                            "warning",
                            f"응축기 출구가 포화액온도보다 {abs(subcooling):.1f} K 높아 "
                            "액체 출구가 아닐 수 있습니다.",
                        )
                    )
                else:
                    checks.append(
                        GuidanceCheck(
                            "pass",
                            f"응축기 출구 과냉도 참고값은 약 {subcooling:.1f} K입니다.",
                        )
                    )
            else:
                checks.append(
                    GuidanceCheck(
                        "info",
                        "고압측이 임계압력 이상이므로 응축 대신 gas-cooling 조건으로 점검합니다.",
                    )
                )
        except (TypeError, ValueError):
            checks.append(
                GuidanceCheck(
                    "warning", "CoolProp에서 이 냉매·압력의 포화 기준을 계산하지 못했습니다."
                )
            )
    return tuple(checks)
