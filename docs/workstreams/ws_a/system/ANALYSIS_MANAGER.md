# 합성 해석 관리 모듈 사용 지침

현재 범위: A-System 내부 정상상태 condenser 냉방 시험 관리. 자연어 Agent, 일반 P08 제약 엔진,
최적화, 동적 실내 제어, 제조사 envelope 검증을 구현한 것은 아니다. 기존 공통 frozen interface는 유지한다.
사용자의 2026-09-23 요청에 따라 Lead가 이 모듈을 추가했다. 향후 WS-C는 이 결정론적 실행기를
도구로 감싸되 공통 SimulationTool 계약 변경이 필요하면 별도 ACR 절차를 따른다.

## 입력과 변경 권한

1. 원래 요구를 raw_requirement에 기록한다. study 첫 case가 기준 입력이다.
2. 냉매·연속 유량·실내 경계·부하·외기·효율·배관·물리 모델·수렴 허용오차는 기본 고정이다.
3. 변경할 변수만 permissions에 path, canonical SI unit, minimum/maximum, authorization_ref로 명시한다.
4. study.cases에 실행할 유한 후보를 기준점부터 순서대로 넣는다. 입력 전체를 사전 검증하며
   한 후보라도 금지 변경이나 범위 위반이면 계산을 시작하지 않는다.
5. max_cases는 기준점 포함 1..100; 후보를 몰래 자르거나 범위를 늘리지 않는다.

지원 조정: 흡입/토출압력(Pa), 응축기/증발기 공기 유량(kg/s), UA(W/K),
h 초기 구간(J/kg), scan_intervals/max_iterations(dimensionless). 모든 다른 값은 고정이다.
압력 변경 시 추가 네트워크 경계 변경이 필요하다면 현 버전은 이를 자동 변환하지 않고 거부한다.
공통 단위 모델이 후보를 SI로 정규화하므로 50g/s와0.05kg/s는 같은 고정값이다.
permissions 단위 문자열은 예제의 Pa, kg/s, W/K, J/kg, dimensionless를 사용한다.

authorization_ref는 출처 기록이며 로그인/사용자 권한 인증 장치가 아니다. 향후 Agent 연결 시
사용자가 승인한 요청과 범위를 신뢰 경계 밖에서 보관하고 Agent가 권한 자체를 생성·확장하지 못하게 해야 한다.
자연어 문구는 수치 권한을 덮어쓰지 않는다. 현재 CLI는 신뢰할 수 있는 작성자의 구조화 입력을 받는다.

## 실행 및 결과

저장소 루트에서:

    uv run --locked python scripts/run_analysis_manager.py --input examples/system_cycle/r410a_analysis_manager.json --output-dir artifacts/analysis-manager/new-run

기존 output-dir는 재사용하지 않는다. 입력 오류는 exit2이며 계산 전에 거부한다.
새 디렉터리에 metadata.json(원입력·UTC시각·commit·dirty·소스/lock hash·Python/CoolProp),
case-NNN.json(전체 solver 이력), report.json(분류·변경 path·대안)을 저장한다.
목표 일치가 있으면 exit0, 모두 평가했지만 없으면 exit1이다. exit1은 코드 실행 오류가 아니다.
예상하지 못한 solver 예외는 error.json 및 이전 case 기록을 보존하고 exit3으로 종료한다.
I/O 실패는 exit2이며 저장 성공을 보장하지 않는다.

run_analysis(backend, request, on_point=...)는 CLI 없이도 사용할 수 있다.
모든 입력은 다시 검증하고, 반환된 case가 요청과 일치하는지 확인한 뒤 callback에 전달한다.
기존 solver를 cold-start 호출하며 물리식 수정, 허용오차 완화, 자동 코드 패치, 숨은 외삽을 하지 않는다.
재시도 후보도 명시적 유한 입력이다. 첫 성공 뒤에도 요청된 후보를 모두 보존한다.

| 결과 코드 | 의미와 다음 조치 |
|---|---|
| TARGET_MET | 기존1W 부하·1e-6W 공기 열수지 및 상조건을 통과한 정상상태 합성점 |
| TARGET_MISMATCH | 유효 회로지만 목표부하 미달/초과; 허용 후보 비교 |
| MODEL_OR_CONSTRAINT_LIMIT | 해당 표본의 모델/상조건 제한; 현실 전체 불가능 판정 아님 |
| PROPERTY_STATE_FAILURE | 물성 상태 오류; 냉매 대체 금지 |
| NUMERICAL_FAILURE | 수치 수렴 또는 독립 공기열수지 문제; 허용된 bracket 등 검토 |
| UNRESOLVED | 실패 근거가 혼합되거나 부족함; 원인 확정 보류 |

실패 원인은 구조화된 history.status와 압력 탐색의 내부 pressure_history를 함께 사용한다.
압력 수렴 실패가 실제 단상 배관 적용 제한을 감싼 경우 내부 근거로 분류한다. 메시지 키워드로 특정 열역학 메커니즘이나
코드 결함을 추정하지 않는다. 원문 stage/message 이력도 보존한다.
closest_eligible_case_id는 유효 표본 중 절대 부하 잔차가 가장 작은 후보다.
미수렴점은 비교 대상이 아니며, 가까운 후보를 목표 달성/최적 설계로 표시하지 않는다.
global_infeasibility_proven=false 및 requirement_change_applied=false를 항상 유지한다.

## 요구 재조정과 코드 수정

허용 범위 내부 후보는 추가 승인 없이 실행 가능하다. 표본을 모두 평가한 후 목표가 없으면
원래 요구를 보존하고 근거 검토·고정조건/가정 재검토·별도 모델 확장을 제안한다.
고정 유량, 냉매, 실내 조건, 목표부하 또는 범위를 바꾸려면 승인 근거가 담긴 새로운 입력/실행으로 분리한다.
3kW를 결과 냉방열로 바꿔 기존 실행의 성공으로 만들지 않는다.
코드 결함 의심은 실패 입력·SHA·trace로 재현하고 별도 테스트/리뷰 후 수정한다.
기존 실패 기록을 지우거나 상 guard 제거/허용오차 완화로 성공시켜서는 안 된다.

## Synthetic example

기존 [R410A 설계 조사](R410A_DESIGN_STUDY.md)의 세 후보를 재사용한다.
사용자 고정값은 R410A·연속0.05kg/s·실내21°C다.
외기35°C, 현열부하3000W, 풍량/UA/압력 후보는 AGENT_ASSUMPTION이며 제조사 사양이 아니다.
사용자는 합성 입력과 허용조건 탐색 구현을 요청했다. 예제의 구체 수치 범위는 기존 조사에서
재사용한 개발 시험 범위이며 보편적 운전 허용 범위나 제조사 보증으로 사용하지 않는다.

실제 실행: 첫 후보 no-valid-evaluations이며 내부 단상 배관 guard 근거로 MODEL_OR_CONSTRAINT_LIMIT,
나머지 두 후보 closure-satisfied.
냉방7.608861kW 및5.391132kW; 두 후보 모두 TARGET_MISMATCH.
가장 가까운 후보 low-capacity-cu260-eu800도3kW보다2.391132kW 크며 목표 달성이 아니다.
실내21°C는 경계조건이며 방의 도달시간·온도 유지 제어를 계산하지 않는다.
재현 및 검증 결과는 [세션 기록](../../../development_log/2026-09-23_WS-A-analysis-manager.md)을 따른다.
