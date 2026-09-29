# 간소화 조건 입력과 유한 후보 생성

이 기능은 합성 condenser 냉방 해석용이다. 공통 SimulationTool/DesignOptimizer 계약을 변경하지 않는다.
원래 조건·환경 가정·허용 축·계산 예산을 한 번 입력하면 기존 AnalysisRequest를 생성한다.

## 실행

전용 checkout에서 다음을 실행한다. 예제 기준2개 후보가 생성된다.

    uv run --locked python scripts/run_analysis_manager.py --format compact --input examples/system_cycle/compact_analysis.json --output-dir artifacts/my-new-analysis

output-dir는 새로운 경로여야 한다. 기존 --format expanded 입력은 계속 지원한다.
exit0 목표 일치, exit1 유한 후보 내 목표 미발견, exit2 입력/저장 오류, exit3 예상 밖 solver 오류다.
원입력, 정규화·확장 입력, preset/source/lock hash, 모든 후보 이력과 결과를 저장한다.

## 값의 의미

- refrigerant, refrigerant_mass_flow, room_temperature: 이번 실행의 사용자 고정조건.
- outdoor_temperature, sensible_load: 필수 경계값. boundary_source_type/ref에 실측/사용자/합성 출처를 명시한다.
- baseline: 흡입/토출압력, 실내/실외 공기유량, 두 HX UA를 단위와 함께 지정한다.
- lower/upper_enthalpy 및 valve_pressure_lower/upper: 명시적 수치 탐색구간.
- preset synthetic-condenser-v1: 초기 R410A 비교점의 zero-length adiabatic pipe, eta_is0.75,
  dry-air cp1006J/(kg K), HX80cells, 기존 수렴 설정/허용오차를 고정한 버전이다.
  패키지에 원본 상세 JSON이 포함되며 모델 가정을 결과에 명시한다.
- axes: 변경을 허용한 변수, 최소/최대값, 균등 표본 수, 허용 근거.
- max_cases: 기준점 포함 최대 계산 수1..100. 초과는 입력 오류이며 몰래 잘라 실행하지 않는다.

지원 축: suction_pressure, discharge_pressure, indoor_air_flow, outdoor_air_flow,
condenser_ua, evaporator_ua. 냉매·연속유량·실내온도·목표부하·외기·허용오차는 축으로 허용하지 않는다.
새 실행에서 요구조건을 변경할 수 있지만 기존 실행을 그 변경값으로 덮어쓰지 않는다.
자연어 raw_requirement는 기록용이며 자동으로 parsing하거나 구조화 값보다 우선하지 않는다.
새 냉매는 backend 지원 여부와 적절한 명시 bracket가 필요하며 자동 수렴을 보장하지 않는다.

## 생성 규칙

기준점이 첫 후보이며, 축 이름을 정렬한 Cartesian grid를 결정론적으로 생성한다.
기준점이 grid에 포함되면 중복 실행하지 않는다. 포함되지 않으면 별도1개로 예산에 센다.
모든 기준값은 승인 범위 내부여야 한다. 압력 조합은 토출>흡입이고 고정된 valve bracket가
흡입압력 후보 범위를 포함해야 한다. 범위 확대·외삽·물리식/허용오차 변경은 수행하지 않는다.

최적화 알고리즘이나 연속 전역해 탐색이 아니다. 결과는 유한 후보 안에서만 판정하며
실패·제약 위반 후보의 성능을 유효 후보 순위에 사용하지 않는다.
기존 모델 적용제한과 수렴 실패의 상세 규칙은 [관리 지침](ANALYSIS_MANAGER.md)을 따른다.

## Python 연결

    compact = CompactAnalysisInput.model_validate_json(input_bytes)
    expanded = expand_analysis(compact)
    report = run_analysis(CoolPropBackend(), expanded, on_point=archive_point)

각 함수는 system_cycle.analysis_input / analysis_manager에서 가져온다.
새 SDK나 네트워크 LLM 의존성은 없다. 향후 Agent는 승인된 입력을 소비하고
실제 결과와 상태를 설명한다. 권한 범위를 Agent가 직접 확장하게 해서는 안 된다.

## 단계별 검증·공유

- [예제](../../../../examples/system_cycle/compact_analysis.json)
- [세션 기록](../../../development_log/2026-09-24_WS-A-analysis-input.md)
- PR48 → [PR49](https://github.com/howos1234-stack/Agent-HVAC/pull/49) → 이번 후속 순서.
- PR48/49는 정상 integration 병합. PR49 원격CI는 실제 결제/사용 한도 annotation과 steps=[]로 BLOCKED. Git 반영/로컬PASS와 CI/Gate 승인은 별개다.
- LJH의 PR36 기존 GUI 파일은 보존하고 다음 단계는 별도 synthetic analysis 화면으로 연결한다.
