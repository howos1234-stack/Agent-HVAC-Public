# 합성 운전 범위 및 수렴 안정성 검증

## 범위와 결정

PR43 head529387f를 보존한 후속 A-System 작업이다. 사용자 요청은 직전 안내의 검토·통합 준비와
DB 없는 운전 범위 확대이며 제품 matching/공통 계약/부품 solver 변경은 포함하지 않는다.
PR43은 조회 당시 OPEN, 독립 리뷰 0건이었다. 최종 head의 CI run35738271021은 결제·한도 문제로
job 시작 전에 차단됐다. 승인 또는 integration 병합 완료로 기록하지 않는다.

## 확장한 입력

`OperatingMapRequest.mass_flows`는 선택적 지정 유량 축이다. 생략하면 기존 base 유량 하나를 쓰며
기존 2D 입력과 이전 2D JSON 결과를 읽을 수 있다. 새 결과는 각 점에 `prescribed_mass_flow`를 저장한다.
순서는 pressure → temperature → mass flow(가장 빠른 축)다. SI 정규화 후 축 중복을 거부하고
전체 곱에 max_points<=100을 적용한다. 실패/invalid-input점에도 원래 지정 유량과 좌표가 남는다.
CSV의 유량은 base 고정값이 아니라 해당 점의 값이다. 이 유량은 미지수 해석 결과가 아니다.
3D 결과에서 유량 누락/좌표 불일치/solve 요청 불일치를 거부한다. 이전 소비자가 새 필드를 읽을 수
있다는 역방향 호환은 보장하지 않는다. 공통 frozen public schema 변경은 없다.

`examples/system_cycle/r744_range_map.json`:
- 토출압 80/90/100 bar(a), GC secondary inlet 285/305 K, 지정 유량0.08/0.10/0.12 kg/s: 총18점.
- 흡입30bar(a), eta0.8, UA200W/K, HX80cells, 배관10cells 및 다른 입력은 기존 예제와 동일.
- 모든 선택은 AGENT_ASSUMPTION이며 제조사 envelope/안전 운전 범위가 아니다.
- 기존 h450..480kJ/kg, pressure3..3.1MPa, 허용오차/최대 반복을 유지한다.
- 실패점의 범위를 몰래 늘리거나 warm-start/재시도/보간하지 않는다.

## 재현 명령

저장소 루트에서 lock 환경을 사용한다. map exit1은 일부 실패점 보존이라는 계약상 예상 상태일 수 있다.

```console
uv sync --locked
uv run --locked python scripts/run_system_cycle.py --mode map --input examples/system_cycle/r744_range_map.json --output artifacts/range/range.json --csv artifacts/range/range.csv
uv run --locked python scripts/run_system_cycle.py --mode closed-loop --input examples/system_cycle/stability/bracket-wide.json --output artifacts/range/bracket-wide.json
uv run --locked python scripts/run_system_cycle.py --mode closed-loop --input examples/system_cycle/stability/bracket-shifted.json --output artifacts/range/bracket-shifted.json
uv run --locked python scripts/run_system_cycle.py --mode closed-loop --input examples/system_cycle/stability/pressure-narrow.json --output artifacts/range/pressure-narrow.json
uv run --locked python scripts/run_system_cycle.py --mode closed-loop --input examples/system_cycle/stability/bracket-misses-root.json --output artifacts/range/bracket-misses-root.json
uv run --locked python scripts/run_system_cycle.py --mode closed-loop --input examples/system_cycle/stability/grid-coarse.json --output artifacts/range/grid-coarse.json
uv run --locked python scripts/run_system_cycle.py --mode closed-loop --input examples/system_cycle/stability/grid-fine.json --output artifacts/range/grid-fine.json
```

## 민감도 정의

- 기본 h450..480kJ/kg/scan6 대비 wide440..490/scan10, shifted452..482/scan6.
- pressure narrow3..3.02MPa/scan4; h 및 나머지 조건 불변.
- root 누락 h470..480kJ/kg/scan2: 기존 근462.655kJ/kg를 포함하지 않는 명시적 실패 사례.
- HX40/80/160cells: 두 HX를 함께 변경, 배관10cells 고정. 배관 격자 독립성 검증으로 확대하지 않는다.
- closure 기준 abs(dh)<=0.01J/kg, abs(dp)<=1Pa(내부0.01Pa), abs(dT)<=1e-4K,
  relative energy<=1e-6, mass<=1e-12. 원래의 부품 기준도 변경하지 않는다.
- 격자 비교는 차이와 감소 추세를 보고한다. 결과를 본 뒤 기준을 완화하거나 제조사 정확도를 주장하지 않는다.

## 부품 트랙 인수인계: 작은 열누설

대상은 PR43의 기존 P04 `components/pipe.py`다. 시스템 쪽에서 부품 검사식을 변경하지 않았다.
재현: `uv run --locked pytest tests/ws_a_system/test_network_map.py -k small_heat -q`.
입력은 r744_network.json에서 세 배관 Uprime0.5W/(m K), trial h450000J/kg,
valve pressure3MPa로 `network.traverse_network`를 호출한다. suction_pipe의 energy closure 잔차
2.21159e-12가 기존1e-12를 초과하며 component-numerical-failure/diagnostics=None으로 보존된다.
큰 엔탈피의 차감과 작은 열량에서 부동소수점 상쇄가 의심되지만 부품 결함의 최종 원인/수정 승인은
별도다. A-Component는 원래 열량/상태 전달을 보존하면서 누적·상쇄 오차를 분석하고 독립 회귀와
함께 수정안을 검토해야 한다. 임의 tolerance 완화나 Uprime 변경을 원래 실패의 해결로 보지 않는다.

## 완료 범위

로컬 구현·검증, PR 검토, 원격 CI, integration 반영을 구분한다. 최종 실측 표와 검사 결과는 아래와
[세션 기록](../../../development_log/2026-09-22_WS-A-map-range-validation.md)에 남긴다.

## 이번 탐색에서 발견·수정한 연결 검사 결함

최초18점은11수렴/7미수렴이었다. 7점 중3점은 P04가 정상 반환한 고압배관을 시스템의
`_audit(p_in-p_out, reported_dp)`가 거부한 사례였다. MPa 압력에서 수십Pa 손실을 되찾는
차감 오차를 손실 크기 기준으로 비교해 연결 오류로 잘못 분류했다.

| p_high bar(a) | secondary K | mass kg/s | trial h J/kg | 차감 dp Pa | P04 보고 dp Pa |
|---:|---:|---:|---:|---:|---:|
|90|305|0.08|468125|46.394936023280025|46.39493601818522|
|100|285|0.08|454531.25|31.336534982547164|31.336534978783515|
|100|305|0.08|466250|40.09664744324982|40.096647438544466|

모두 valve trial3MPa였다. 수정은 A-System `network._audit_pipe_pressure`에 한정한다.
P04의 실제 식 `p_next=p_current-dp_cell`을 동일 순서로 재구성하여 각 셀 inlet/outlet 및
최종 outlet 압력을 **정확히 일치**하는지 검사한다. 보고된 total dp는 cell dp의 fsum과
기존 `_audit` 기준으로 비교한다. 큰 두 끝점 압력을 빼서 손실을 재생성하지 않는다.
부품 압력/에너지 closure 기준, 시스템 root 허용오차 및 `_audit` 상수는 그대로다.
이는 압력강하 물리식이나 부품 계산값을 바꾸는 수정이 아니다. P04 현재 pressure marching
계약을 소비하는 검사이며 향후 marching 방식 변경 시 이 검증도 함께 검토해야 한다.

동일 실제 입력3개의 단일 순회가 정상 평가됨을 확인했다(폐회로 수렴 판정과는 별개).
손상된 outlet(+0.001Pa), total dp(+0.01Pa), 셀 outlet 및 셀 연결은 각각 거부하는 회귀를 추가했다.
원래18점 및6개 민감도는 이 수정 후 다시 계산하며, 수정 전 결과는 별도 artifact로 보존한다.
부품 자체의 작은 열량 energy 잔차 실패는 이 압력 검사 수정으로 해결됐다고 주장하지 않는다.

### Uprime20 예제에서도 재현되는 P04 에너지 잔차

확장 범위의 초기 결과에서는 Uprime20을 유지해도 아래4점의 마지막 실패 샘플에서
suction_pipe 자체의 energy 검사 실패가 관찰됐다. 단순히 합성 열누설 값을 키우는 것으로
부품 수치 안정성 문제가 일반적으로 해결되지 않는다. 이 표는 부품 트랙 재현 자료이며
해당 운전점이 물리적으로 불가능하다는 판정은 아니다.

| p_high bar(a) | secondary K | mass kg/s | trial h J/kg | trial valve p Pa | P04 상대 energy |
|---:|---:|---:|---:|---:|---:|
|80|305|0.08|469584.9609375|3050000|1.07747e-12|
|80|305|0.10|468750|3000000|1.09124e-12|
|80|305|0.12|480000|3005382.466684057|1.00354e-12|
|90|305|0.12|469375|3050000|1.02838e-12|

기준1e-12는 그대로다. 특히 no-bracket은 유효 인접 부호변화 탐색 실패이며 전역 해 부재가 아니다.
원래의 입력 JSON, point index, h/pressure_history를 보존한다. 자동 bounds 조정이나 실패점 삭제로
수렴률을 올리지 않는다. A-Component의 별도 검토/수정 후 동일 조건의 재검증이 필요하다.

## 최종 실측 결과

최종18점: **14 converged / 4 unconverged**. CLI exit1은 실패점 포함을 뜻한다.
구현 commit0923c7ff59615d8370d0f8dfc1def106f355f73c, working_tree_dirty=false.
수정 전11개 정상점의 result 전체(수치와 반복 이력)는 동일하고 index9/12/15의3점을 회복했다.
남은4점(index3/4/5/11)은 위 P04 energy 잔차 재현 사례다. 물리적 불가능 판정으로 바꾸지 않는다.
전18점 JSON/CSV, 각 점 지정유량, 실패점 성능 공란, 정상점의 실제 p/h/T/mass/energy 잔차,
모든 산출물의 실제 source_sha256과 최종 소스 일치 검사를 Python assertion으로 확인했다.

최대 abs(dh)=0.00888027152J/kg, abs(dp)=0.00836143643Pa, relative energy=8.61527517e-8.
기존 기준 모두 충족한 점만 converged다. 상세 요약과 원본 artifact hash:
[MAP_RANGE_RESULTS.json](MAP_RANGE_RESULTS.json).

| p_high bar(a) | secondary K | 지정 mass kg/s | 상태 | COP |
|---:|---:|---:|---|---:|
|80|285|0.08|converged|0.911080094|
|80|285|0.10|converged|0.676252785|
|80|285|0.12|converged|0.502487616|
|80|305|0.08|unconverged|—|
|80|305|0.10|unconverged|—|
|80|305|0.12|unconverged|—|
|90|285|0.08|converged|0.923347044|
|90|285|0.10|converged|0.679090690|
|90|285|0.12|converged|0.501016029|
|90|305|0.08|converged|0.555286919|
|90|305|0.10|converged|0.382184387|
|90|305|0.12|unconverged|—|
|100|285|0.08|converged|0.934176645|
|100|285|0.10|converged|0.682444443|
|100|285|0.12|converged|0.500701276|
|100|305|0.08|converged|0.585137671|
|100|305|0.10|converged|0.403313596|
|100|305|0.12|converged|0.266718582|

### 최종 민감도

| 입력 변경 | 상태 | COP | 기본80cell 대비 상대차 |
|---|---|---:|---:|
|bracket-misses-root|unconverged|—|—|
|bracket-shifted|converged|0.6006746702|1.05912286e-07|
|bracket-wide|converged|0.6006746066|0|
|grid-coarse|converged|0.6065780045|0.00982794659|
|grid-fine|converged|0.5977505650|-0.00486792933|
|pressure-narrow|converged|0.6006746081|2.51842081e-09|

기본80cell COP0.6006746066. 40→80→160cell에서 변화가 감소하고 80/160차이는 약0.49%다.
이는 관측한 격자 민감도이며 전체 영역 격자 독립성/제조사 정확도를 보장하지 않는다.
초기 h/압력 탐색의 정상 변형은 같은 근 부근으로 수렴했다. root를 제외한 구간은 no-bracket으로
실패하고 performance=None이다. 6개 민감도 결과와 반복 이력도 수정 전후 동일하다.
민감도 산출물은 수정 후 소스 해시와 일치하는 dirty checkout에서 실행됐으며 18점 최종 맵은
같은 구현의 위 clean checkpoint를 metadata에 기록했다.

최종 코드: base485 passed/1 skipped(Streamlit 없음), GUI502 passed, Ruff/format/mypy/manifest/build
PASS. 실제 구형6점 결과 읽기와 문서 링크 및 work record 검사 PASS. 원격 CI는 구현0923c7f의
run35742841262, Windows/Ubuntu × base/gui 모두 steps=[]이며 결제/사용 한도로 시작 전 BLOCKED.
integration 반영 및 code owner 독립 리뷰는 미완료다.
