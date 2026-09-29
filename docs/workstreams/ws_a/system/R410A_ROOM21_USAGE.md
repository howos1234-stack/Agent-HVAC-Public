# R410A 합성 실내21°C 시험 사용법

이 브랜치는 R410A 내장 의사순수 물성, 응축기, 3개 배관, 압축기·밸브·증발기를 연결한다.
제품 DB는 사용하지 않는다. 숫자와 제품 성능 검증을 혼동하지 않는다.

## 실행

저장소의 이 브랜치에서 PowerShell로 실행한다. 정상 입력이지만 목표를 충족하지 못한 결과는
JSON을 저장하고 exit1을 반환한다. 입력·파일 오류는 exit2다.

```powershell
uv sync --locked
uv run --locked python scripts/run_system_cycle.py --mode room-sizing --input examples/system_cycle/r410a_room21_sizing.json --output artifacts/r410a/initial.json
uv run --locked python scripts/run_system_cycle.py --mode room-sizing --input examples/system_cycle/r410a_room21_diagnostic_air15.json --output artifacts/r410a/diagnostic.json
uv run --locked python scripts/run_system_cycle.py --mode closed-loop --input examples/system_cycle/r410a_room21_nonzero_pipes.json --output artifacts/r410a/nonzero.json
```

- 첫 입력은 승인된 초기 합성 가정이며 응축기 출구 2상으로 실패한다.
- 둘째 입력은 명시적 추가 비교 가정이다. 토출압력3.5MPa, 실내공기1.5kg/s이다.
  UA100/200/400은 미수렴, UA800은 수렴하나 3kW 부하를 충족하지 않는다.
- 셋째 입력은 둘째 입력의 UA800에 비영 배관 압력손실을 적용한 정상 회로다.
  exit0은 폐회로 수렴만 뜻하며, 실내 부하 균형 달성을 뜻하지 않는다.

## 입력과 결과 읽기

`condenser`와 `gas_cooler` 중 하나만 입력한다. network의 압력손실 필드도 각각
`condenser_pressure_drop` 또는 `gas_cooler_pressure_drop`로 맞춘다.
기존 R744 gas_cooler JSON은 계속 읽힌다. 새 condenser 입력을 옛 코드에서 읽는 역호환은 없다.
trace/node/진단/맵CSV 이름은 실제 응축기 또는 gas cooler를 반영한다.

room-sizing은 실내 온도를 증발기 공기 입구와 일치시킨다. 미지수는 기존 내부 h/p와
외부 증발기UA다. 인접한 수렴 표본에서 부하 잔차 부호가 바뀔 때만 이분법을 수행한다.
실패한 중간점을 건너뛰지 않으며 지정한 UA 범위를 확대하지 않는다.

- `history`: 모든 UA, 내부 h/p 반복, 실패 원인, 유효한 표본의 부하 잔차와 공급공기 온도.
- `cycle_converged`: 마지막 평가의 폐회로 수렴 여부.
- `load_balance_satisfied`: 마지막 평가의 `abs(Qev-Qload)<=1W` 및 공기 열량 오차<=1e-6W.
- `design_target_satisfied`: 위 두 조건을 모두 만족해야 true.
- `metadata`: 입력·실제소스·lock 해시, Git commit/dirty, Python/CoolProp,
  `COOLPROP_BUILTIN_PSEUDOPURE_R410A`와 원래 reference state 출처.

공기 측은 Q=m_air*cp_air*(T_room-T_supply), 회로는 m*(h_return-h_trial), 귀환압력,
질량 및 전체 Q+W를 독립 검증한다. COP는 냉매측 냉방열/압축기 전달동력이며 팬/모터 전력은 제외한다.

## 결과의 적용 범위

계산은 실내21°C라는 경계에서 성능을 평가한다. 실제 방이21°C에 도달하거나 안정적으로
유지된다는 시간응답 예측은 아니다. 현재3kW 부하 일치는 미달성이다.
잠열·습도·결로·건물축열·인버터/온도제어·실제 제품 map은 포함하지 않는다.
R410A만 승인된 의사순수 예외이며 다른 혼합냉매나 조성 문자열을 임의로 허용하지 않는다.

물성 출처: [CoolProp R410A](https://coolprop.org/fluid_properties/fluids/R410A.html),
Lemmon2003 EOS. 물성 왕복 시험은 같은 EOS의 일관성 검사이며 제조사 또는 독립 EOS 검증이 아니다.
[계획·실행 결과](R410A_ROOM21_TEST_PLAN.md)와 [검증 수치](../../../validation/r410a-room21-results.json)를 참고한다.
