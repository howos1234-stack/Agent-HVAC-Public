# 합성 배관 폐회로 및 운전맵 검증

## 모델과 단위

기존 P02 eta-is 압축기/등엔탈피 밸브, P04 단상 배관, P05 병류 constant-UA HX를 수정 없이 사용한다.
[P04 근거](../P04_PIPE_1D_VALIDATION.md), [P05 근거](../P05_HEAT_EXCHANGER_1D_VALIDATION.md),
[S2 근거](S2_CONVERGENCE_VALIDATION.md), [사용자 위임/결정](SYNTHETIC_MAP_DECISIONS.md).
P04 셀식은 dp=f_D*(dx/D)*rho*v²/2, q=Uprime*dx*(T_ambient-T_fluid)이며 유효 단상 범위를 검사한다.

7개 부품/8개 노드: 압축기→토출배관→가스쿨러→고압배관→밸브→증발기→흡입배관.
냉매 R744, 흡입3MPa/토출9MPa, 지정 m=0.1kg/s, eta-is=0.8.
HX 각각 UA200W/K, secondary 1kg/s·cp1000J/(kg K), GC290K/EV300K, 80cells.
HX Δp 각각 10000Pa/5000Pa. 배관 각각 L0.5m/D0.02m/roughness1e-6m,
유효 mu1.5e-5Pa*s/Uprime20W/(m K)/ambient295K/10cells. 모두 AGENT_ASSUMPTION.
제조사 rated point를 off-design에 재사용한 결과가 아니다. 물성은 CoolProp8.0.0 실물성이다.

미지수 h_suction/p_valve_outlet의 잔차를 각각 계산한다. 내부 pressure bracket3..3.1MPa,
scan2, 최대60회, tolerance0.01Pa. 외부 h450..480kJ/kg/scan6/max100,
h tolerance0.01J/kg, p1Pa, T1e-4K, energy1e-6/mass1e-12를 모두 통과해야 converged다.
압력은 유효 인접 bracket 안의 secant와 매4번째 bisection을 사용한다.
중간 무효 상태/float 정체/한도 초과는 실패이며 상태값을 수정해 closure를 만들지 않는다.

## 실제 단일 운전점 결과

Windows/Python3.12.14/CoolProp8.0.0, r744_network.json, 기존 CLI closed-loop 모드.

| 항목 | 계산값 | 판정 |
|---|---:|---|
| abs(Δh) | 0.00444317353 J/kg | <=0.01 PASS |
| Δp | 0.00827447744 Pa | 내부<=0.01 및 최종<=1 PASS |
| abs(ΔT) | 3.47122267e-6 K | <=1e-4 PASS |
| 상대 energy | 4.54791649e-8 | <=1e-6 PASS |
| 상대 mass | 0 | <=1e-12 PASS; 지정 유량 일관성 |
| compressor work | 6805.938316 W | 냉매측 |
| evaporator heat | 4088.154321 W | 냉동능력 |
| GC rejection | 9769.689609 W | 방열 |
| pipe Q 합 | -1124.403472 W | 회로 열수지에 포함 |
| COP | 0.6006746066 | 냉매측, 팬/모터/펌프 제외 |
| valve outlet pressure | 3005259.028418 Pa | 흡입압력과 같게 강제하지 않음 |
| h/pressure 평가 횟수 | 21 / 63 | 모든 이력 JSON 저장 |

sum(Q+W)=-0.000444317325W, m*Δh=-0.000444317353W,
전달 회계 오차2.84217e-11W. 에너지 audit는 추가 독립 root 방정식이 아니다.
배관 길이/HX Δp를 0으로 하면 COP0.5199018794의 기존 S2로 환원하며 허용차2e-6 회귀 PASS.

## 발견한 문제와 처리

최초 세 배관 Uprime0.5W/(m K) 예제는 suction pipe 에너지 상대 잔차
2.21159e-12 등으로 기존 P04 기준1e-12를 초과했다. suction만20으로 변경한 별도 실험도
일부 반복에서 high-side pipe 1.43693e-12 실패가 발생했다. 작은 열량과 큰 h의 차감에 민감한
기존 부품 검사 한계로 기록한다. P04 계산식/허용오차를 변경하거나 실패를 흡수하지 않았다.
실패 조건은 test_small_heat_pipe_failure_is_retained_not_relaxed에 보존했다.
작동 검증용 최종 예제는 세 배관 Uprime20이라는 별도 합성 조건을 명시적으로 선택했다.
이는 원래 작은 열누설 case가 해결됐거나 모든 입력이 수렴한다는 주장이 아니다.

초기 긴 줄/타입 진단은 formatter와 정확한 component Literal로 해결했다.
source/lock/입력 hash를 결과에 저장하며 synthetic 값의 출처를 입력에서 명시한다.

## 검증 범위와 한계

집중 55 passed: 실제 네트워크, zero-loss 환원, 작은 열량 실패 보존, 무효 pressure bracket,
반복한도, 부호변화 없음, 맵 전점 보존/순서/단위중복/상한/CSV/CLI 실패 및 S1/S2 회귀.
최종 GUI 전체 495 passed; base 478 passed/1 skipped(Streamlit 없음). Ruff/format/mypy 및 manifest/build PASS. Windows CSV 중복 개행도 실제 CLI 회귀로 수정 확인했다.

[세션 기록](../../../development_log/2026-09-22_WS-A-synthetic-hvac-map.md).
고정 유량·압력에서의 합성 정상상태 맵이며 압축기/밸브 map matching·실제 제품 용량·습공기·
서리·과도·제어·제품 최적화·WS-C ConstraintEngine 또는 Gate 완성이 아니다.
주어진 유한 격자 밖을 보간/외삽하지 않는다. 유일해 또는 전역 유효 영역을 증명하지 않는다.

## 실제 6점 운전맵

| 토출압 bar(a) | GC secondary K | 결과 | COP |
|---|---|---|---:|
|85|290|converged|0.596269824|
|85|295|converged|0.518009987|
|85|400|unconverged / no-valid-evaluations|—|
|90|290|converged|0.600674607|
|90|295|converged|0.525282734|
|90|400|unconverged / no-valid-evaluations|—|

400K는 의도적으로 실패를 확인하는 경계조건이다. 6점 전부 JSON/CSV에 남으며 실패점 성능값은 비워 둔다. CLI exit1은 실패점을 포함한다는 계약상 예상 결과이며 6점 모두 수렴했다는 뜻이 아니다.

구현 commit1e89c9a, working_tree_dirty=false에서 최종 재실행하여 6점 status/result 전체와 반복 이력의 동일성을 확인했다. 400K 실패는 gas_cooler inlet secondary stream 온도 조건 위반이다. CSV header+6행 및 CRCRLF 부재 확인 PASS. 원격 CI는 결제/한도에 따른 시작 전 BLOCKED이며 integration 미병합이다.
