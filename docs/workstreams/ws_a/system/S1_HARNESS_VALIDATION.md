# S1 합성 입력 → 기존 부품 연결 검증

- 범위: A-System S1 단일 순회와 그에 필요한 S0 typed 입력/CLI. 반복 수렴, 배관, map sweep 미구현.
- 물리 코드 기준: integration `2813c2b`; 문서 기반 PR #37 `de8c264`에서 후속 branch로 작업.
- 기존 compressor/valve/HX/property/schema/loader/lockfile 변경 없음.
- 모델: R744 transcritical, fixed suction/discharge pressure 및 mass flow, eta-is 압축기,
  등엔탈피 밸브, 병류 constant-UA HX 두 개, HX Δp=0, 배관 없음, 건식 2차유체.
- 모든 입력/결과는 is_mock=true. CoolProp 실제 물성을 사용하나 제조사/실험 검증이 아니다.

## 입력 및 출처

[합성 예제](../../../../examples/system_cycle/r744_single_pass.json): R744, 30/90 bar(a),
360 kg/h, eta-is 0.8, trial suction 280 K. 이 다섯 수치는 P02 회귀 입력을 재사용했다.
두 HX는 각각 UA=200 W/K, 80 cells, 2차유체 1 kg/s, 1000 J/(kg K)다.
가스쿨러 2차유체 290 K는 기존 P05/PR #34 조건을 참고했고 증발기 300 K 및 UA는 명시적
AGENT_ASSUMPTION 시험값이다. 결합 결과가 기존 정격점과 일치한다는 주장은 하지 않는다.
source_ref/assumptions를 입력에 필수 보존한다. 원본 JSON과 canonical 모델을 함께 결과에 저장한다.

참조:
- [P02 검증](../P02_BASELINE_CYCLE_VALIDATION.md)
- [P05 검증](../P05_HEAT_EXCHANGER_1D_VALIDATION.md)
- [두 트랙 계획](TWO_TRACK_PLAN.md)

## 구현과 연결 경계

- SyntheticScenario는 차원·유한값·압력 순서·효율 (0,1]·mock·필수 경계를 검사한다.
- evaluate_circuit는 기존 부품 함수를 호출하고 이전 출구를 다음 입구로 전달한다.
- 노드: suction_trial → compressor_outlet → gas_cooler_outlet → valve_outlet → suction_return.
- ComponentTrace는 inlet/outlet node, mass flow, 냉매 유입 부호 Q/W, 모델 경로와 HX cell 결과를 가진다.
- 입력 유량을 모든 부품에 전달한다. 이는 장비 map이 결정한 유량이나 mass-flow matching 검증이 아니다.
- 내부 CircuitResult를 사용하며 기존 HVACSolver/SimulationResult를 변경하거나 converged로 변환하지 않는다.
- status=evaluated여도 cycle_converged=false. 반환 상태가 압축기 입구로 사용 가능한지는 S2에서 다시 검사해야 한다.
- 부품 오류는 stage·설명·partial results를 반환하고 diagnostics는 None으로 남긴다.
  예상하지 못한 RuntimeError 등은 숨기지 않는다.

## 잔차 정의와 기준

Q는 냉매 유입 양수, W는 압축기에서 냉매로 전달되는 일이다. 팬/펌프/모터 손실은 포함하지 않는다.

```text
loop Δh = h_return - h_trial
loop Δp = p_return - p_trial
loop ΔT = T_return - T_trial
net = W_compressor + Q_gas_cooler + Q_evaporator
transport = m_dot * loop Δh
transfer_error = net - transport
relative_transfer_error = abs(transfer_error) / max(abs(W), abs(Q_i), 1 W)
```

transfer 상대오차 1e-10은 P02 보존 검사 수준의 roundoff audit이며 폐회로 수렴 기준이 아니다.
부품별 에너지, 노드 압력·초기 온도 보존도 같은 상대 기준(각 SI 단위 1의 scale floor)으로 검사한다.
기존 P05의 1e-12 검사나 허용오차는 변경하지 않았다. 위 단위/scale과 실패 경계는 코드 상수로 명시한다.

## 실제 실행 결과 (Windows, Python 3.12.14, CoolProp 8.0.0)

| 항목 | 계산 결과 | 의미 |
|---|---:|---|
| 압축기 냉매측 동력 | 6388.690872445994 W | P02 기준과 일치 |
| 가스쿨러 방열 | 9419.30248152867 W | 양수 방열 표시; Q_gc 자체는 음수 |
| 증발기 흡열 | 4062.7768765939477 W | 단일 순회 duty |
| 흡입 trial T / 반환 T | 280 / 287.99165632045447 K | 입력 노드를 덮어쓰지 않음 |
| loop Δh | 10321.652675112535 J/kg | 폐회로 미수렴 |
| loop Δp | 0 Pa | 초기 zero-loss 압력 배치 |
| net | 1032.1652675112714 W | 0이 아님; 수렴 결과로 표시 금지 |
| transfer_error | 1.7962520360015333e-11 W | 한 바퀴 에너지 전달 회계 오차 |
| relative_transfer_error | 1.906990501179889e-15 | 1e-10 이하 |

상태는 gas → supercritical → supercritical → twophase → gas다.
위 회귀값은 이 구현의 deterministic reference이며 독립 제조사 truth가 아니다. tests/ws_a_system에서
P02의 기존 compressor reference와 신규 S1 값은 rel=1e-9로 고정했다. 직접 기존 부품 호출 결과와
모든 노드/HX profile의 동일성, 반복 결과 동일성 및 JSON 왕복을 별도로 검증한다.

## 정상/실패 검사

22개 신규 테스트: 실제 부품 직접 호출 대조, unit equivalence, 필수값/차원/유한값/mock 거부,
알 수 없는 냉매, 액체 흡입, 양쪽 HX 온도방향 오류, 조작된 부품 에너지 오류 검출,
미지 오류 전파, UA=0과 2상 return을 수렴 성공으로 오인하지 않기, CLI 정상/실패/입력 보존/hash 검증.
전체 base: 445 passed, GUI extra 미설치 1 skipped. Ruff check/format PASS, mypy 61 source files PASS.
GUI 포함 전체 462 passed, manifest 126 files 및 sdist/wheel build PASS. 원격 CI는 PR 실제 실행 근거를 따른다.

## 한계 및 다음 작업

R744 조건 후보 전체가 실행 가능하다는 보장은 없다. coarse grid나 phase/온도 방향 오류는 실패로 남긴다.
이번 작업은 grid-independence·초기값 독립성·root finding·전체 MAP·제품 운전영역 검증을 수행하지 않는다.
S2에서 h 기반 trial, 유효 구간 bracket, 폐회로 residual, iteration diagnostics와 재현성을 별도 구현한다.
S3 단상관, S4 sweep, 제조사 적용, P06/Gate 승인은 별도다.

[작업 기록](../../../development_log/2026-09-22_WS-A_system-s1-harness.md).
