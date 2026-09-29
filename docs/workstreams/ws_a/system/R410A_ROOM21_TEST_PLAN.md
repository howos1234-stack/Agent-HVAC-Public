# R410A / 0.05kg/s / 목표 실내21°C 합성 냉방 시험 계획

상태: ACR-0004 사용자 승인 후 구현·시험 수행. 초기 조건 실패, 추가 비교 조건 폐회로 수렴, 3kW 목표 미충족.
승인 근거: 2026-09-23 현재 대화 “응 해줘”. GitHub Approve/Gate 승인 아님.
기준 PR44 e94e262. 사용자 확인: 21°C는 에어컨 토출공기가 아니라 방 안의 목표 실내온도다.
[제한 지원 ACR](../../../architecture/ACR-0004-r410a-pseudopure-limited.md).

## 고정 요청과 시험 가정

| 항목 | 값 | 출처 |
|---|---:|---|
| 냉매 | R410A | USER, 표기 R-410 A를 내장 식별자로 명시 대응 |
| 냉매 유량 | 0.05kg/s | USER, 정상 운전 유량; 임의 duty 평균으로 변경하지 않음 |
| 목표 실내/증발기 공기 입구 | 21°C | USER, 완전 혼합 실내의 정상상태 경계 |
| 외기/응축기 공기 입구 | 35°C | AGENT_ASSUMPTION, 설계 규격/실측값 아님 |
| 실내 현열 부하 | 3000W | AGENT_ASSUMPTION, 실제 방의 부하 계산 아님 |
| 증발기 공기 질량유량 | 0.50kg/s | AGENT_ASSUMPTION |
| 응축기 공기 질량유량 | 0.80kg/s | AGENT_ASSUMPTION |
| 공기 유효 비열 | 1006J/(kg K) | AGENT_ASSUMPTION, 건식 상수비열 시험 |
| 압축기 등엔트로피 효율 | 0.75 | AGENT_ASSUMPTION |
| 초기 흡입/토출 절대압 후보 | 1.0/2.8MPa | AGENT_ASSUMPTION, 모델 지원·phase·수렴 확인 전 유효 운전점으로 단정 금지 |
| 응축기 UA 후보 | 800W/K | AGENT_ASSUMPTION |
| 증발기 UA 탐색 후보 | 100/200/400/800W/K | AGENT_ASSUMPTION, 상한 밖 무표시 외삽/자동 확대 금지 |

배관 geometry는 기존 명시 합성 입력을 복사하되 점도/열누설은 R410A 실측값으로 표기하지 않는다.
최초 zero-loss 회귀와 비영 배관 입력을 분리한다. 기존 P04 작은 열량 잔차 문제는 여전히 별도다.

## 어떻게 21°C 목표를 평가하는가

단순히 증발기 공기 입구를21°C로 설정했다는 이유로 room_target_met=true로 표시하지 않는다.
목표 정상상태 식은 Q_evaporator = Q_room_load이다. 공기측 현열식은
Q_evaporator = m_air * cp_air * (T_room - T_supply).
위 가정의 필요 토출온도는21 - 3000/(0.50*1006) = 약15.036°C다.
이 값은 회로 계산 결과가 아닌 부하식에서 구한 요구 조건이다.

R410A 응축기 폐회로를 먼저 검증한 뒤, 고정 냉매 유량/압력·실내21°C 경계에서 증발기 UA를
명시된 구간으로 탐색한다. 미지수 h_suction, p_valve_outlet에 외부 UA sizing 변수를 더하며
독립 residual은 귀환 h 차이, 귀환 p 차이, Q_evap-Q_load다. 기존 energy audit를 중복 방정식으로
세지 않는다. 모든 내부 폐회로가 정상 수렴한 유효 인접 구간에서만 UA 이분법을 적용한다.
실패점/무효 구간을 가로지르지 않는다. 초기 UA 후보에 bracket이 없으면 설계 목표 불충족으로
보고하며 임의 유량 변경이나 열부하 축소로 통과시키지 않는다.

제안 sizing 기준: abs(Q_evap-Q_load)<=1W, 최대40회, UA100..800W/K 범위.
이는 실측 정확도 기준이 아닌 명시한 합성 수치 시험의 허용오차다. 초기값/평가별 잔차를 보존한다.
폐회로 기준은 abs(dh)<=0.01J/kg, abs(dp)<=1Pa(내부압력0.01Pa), abs(dT)<=1e-4K,
relative energy<=1e-6, mass<=1e-12를 유지한다.
최종에는 공기측 열량과 냉매측 증발기 열량도 대조한다.

결과는 cycle_converged, load_balance_satisfied, design_target_satisfied를 구분한다.
'21°C 유지 가능'은 지정한 정상상태 부하·모델에서의 계산상 조건 충족이며 실제 방의 도달 시간,
온도제어 안정성, 습도·응축수/잠열, 침기·벽체 축열 또는 실제 제품 성능 검증을 뜻하지 않는다.

## 실행 순서

1. ACR-0004 제한 지원안 승인 및 A-Component 경로 조율.
2. R410A 물성 검증과 응축기 연결, 기존 R744 회귀.
3. 0.05kg/s 단일 정상점 수렴 및 실패 검사.
4. 실내21°C/부하3000W UA sizing, 목표 충족/불충족 명확히 판정.
5. 실제 계산된 COP/냉동능력/전달 동력/공기 토출온도/전체 노드 및 profile 시각화.

## 승인 전 확인한 실행 근거 (과거 기록)

CoolProp8.0.0 get_fluid_param_string('R410A','pure') → false.
현재 backend state_pt('R410A',1MPa,294.15K) → InvalidPropertyStateError:
mixture and pseudo-pure inputs require an approved contract extension.
이는 환경 설치 오류나 수렴 실패가 아닌, 현재 승인된 입력 범위의 명시적 거부다.
미지원 입력을 거부하는 현재 동작 확인은 PASS; 요청한 R410A 시스템 해석은 NOT_RUN이다.


## 승인 후 실제 실행 결과와 조치

초기 1.0/2.8MPa, 실내공기0.50kg/s, 응축기UA800W/K에서 응축기 출구가 2상이었다.
P04 단상 배관 거부를 보존했으며 초기 UA100/200/400/800 모두 유효 수렴근을 찾지 못했다.
별도 진단1은 토출압력3.5MPa, 실내공기0.8kg/s로 변경했으나 흡입 배관의 2상 조건 때문에
정상근을 찾지 못했다. 진단2는 실내공기1.5kg/s로 명시 변경했고 UA800에서 폐회로가 수렴했다.
유량0.05kg/s, 냉매R410A, 실내21°C, 외기35°C, 부하3000W는 모든 시험에서 유지했다.

- 진단2 zero-loss: Qev=7608.861119W, Wcomp=2407.335287W, COP=3.160698536.
- 부하 잔차 +4608.861119W, 공급 공기15.957680°C. cycle_converged=true,
  load_balance_satisfied=false, design_target_satisfied=false.
- 같은 진단2의 비영 배관(L0.5m, 단열Uprime0, HX dp10/5kPa):
  Qev=7604.569886W, Wcomp=2406.573416W, COP=3.159916018.
  상대 에너지 잔차1.41590e-8, 압력 귀환 오차-1.78861e-6Pa, 엔탈피 귀환 오차0.00283495J/kg.
- 배관 mu15microPa.s/거칠기1um/D20mm는 합성 가정이며 R410A 실측 물성 아님.
  비영 열누설 배관은 이번 검증 범위 밖이며 기존 P04 작은 열량 잔차 문제는 그대로 남는다.
- UA 구간 밖 자동 확대, 부하 축소, 유량 변경, 임의 duty-cycle로 성공 처리하지 않았다.
  실패점은 heat duty/COP를 노출하지 않고 전체 내부 반복과 실패 원인을 JSON에 보존한다.

[정량 요약](../../../validation/r410a-room21-results.json).
[사용법 및 한계](R410A_ROOM21_USAGE.md). 제조사·독립 EOS benchmark는 NOT_RUN이다.
실내21°C에서 회로를 계산할 수 있다는 것과 지정 부하의 정상 균형 달성은 구분해야 한다.
다음 설계 작업은 실제 실내부하/풍량을 확정한 뒤, 별도 명시한 압력·용량·제어 변수 계약으로
3kW 부하에 맞는 설계를 탐색하는 것이다. 현재 유효 UA 표본만으로 전역 불가능을 주장하지 않는다.
