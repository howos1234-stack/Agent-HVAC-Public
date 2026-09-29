# WS-A 두 트랙 운영 및 DB 없는 전체 1D 회로 계획


최신 사용자 지시: 2026-09-22 사용자가 미해결 수치 결정을 위임하고 합성 전체 맵 작업을 계속하도록 지시했다.
[합성 맵 결정 기록](SYNTHETIC_MAP_DECISIONS.md)이 아래 초기 착수/세션 제한 및 과거 승인 대기 설명을
이번 DB 없는 A-System 경로에 한해 갱신한다. 제품 CL-1·map 토출 ACR·제조사 검증·Gate 승인은 별도다.

- 결정일: 2026-09-22 (Asia/Seoul)
- 근거: 책임자가 현재 대화에서 두 트랙 분리와 Git 공유, DB 없는 합성 입력 검증을 명시적으로 요청했다.
- 기준: integration `2813c2bed6f02eefa50d56e7d081bb7dbcead758` (PR #34 병합).
- 상태: 담당·시험 방향은 사용자 지정. 본 계획은 문서 PR 검토 대상이며 시스템 구현·수렴 검증은 NOT_STARTED.
- 이 문서는 P06 전체 완료, frozen interface 변경 또는 Integration Gate 1 승인이 아니다.

## 1. 담당 및 파일 경계

| 트랙 | Human owner | 담당 | 전용 경로 |
|---|---|---|---|
| A-Component | @daeyunekim | 기존 P01–P06 흐름의 부품 모델·물성·회귀·제조사 검증, 시스템이 발견한 부품 결함 보완 | 기존 properties/, physics/, components/, tests/ws_a/ 및 기존 부품 문서 |
| A-System | @howos1234-stack | 기존 부품 소비, 냉매 상태 연결, 폐회로 수렴, 운전조건 sweep/성능맵 | solvers/system_cycle/, tests/ws_a_system/, examples/system_cycle/, docs/workstreams/ws_a/system/, scripts/run_system_cycle.py |

위 src 경로는 `src/agent_hvac/` 기준이다. 기존 P02 solver 및 TESPy 검증은 A-Component가 유지한다.
A-System은 부품 방정식이나 검증 허용오차를 직접 수정하지 않는다. 부품 문제가 보이면 재현 입력,
대상 SHA, 기대/실제 결과를 기록해 A-Component의 별도 수정 PR로 해결한다. 회로 연결 결함은 A-System이 해결한다.
공통 CURRENT_STATE 및 manifest 충돌은 최신 integration을 반영해 양쪽 기록을 보존한다.
공통 schema, units, PropertyBackend/HVACSolver/SimulationResult 계약 변경은 기존 ACR 절차를 따른다.
CODEOWNERS의 system 경로를 Lead로 분리하되 이는 리뷰 라우팅이며 branch 보호·독립 승인 강제가 아니다.
시스템 코드의 독립 검토는 A-Component에 요청할 수 있지만 수용이나 승인 사실은 실제 근거가 있을 때만 기록한다.

### 기존 PR과 조율

- [PR #35](https://github.com/howos1234-stack/Agent-HVAC/pull/35)는 대연킴의 제품/Excel 기반 Gate 1 폐회로 계획으로 OPEN이다.
  이번 사용자 지시에서는 초기 폐회로 구현 owner를 A-System으로 지정하고 DB/제품 경로는 제외한다.
  #35의 기술적 주의사항(압축기 동력 경계, HX 정격점의 off-design 금지, 2상 배관 제외)은 보존한다.
  #35의 기존 담당·CL-0/CL-1을 별도 경쟁 구현으로 착수하지 않고, 병합 전에 이 분담과 맞추어 정리한다.
  이 문서가 #35를 승인·닫기·병합하거나 그 작성자의 수용을 기록하는 것은 아니다.
- [PR #36](https://github.com/howos1234-stack/Agent-HVAC/pull/36)의 WS-E workbench는 별도 GUI 작업이다.
  A-System은 GUI 파일을 수정하지 않는다. GUI가 현재 baseline을 호출하더라도 시스템 solver 연결 완료라고 부르지 않는다.
- WS-B의 ProductRecord #17·loader #24는 병합 완료지만 초기 A-System의 실행 의존성은 아니다.
  미래 제품 연결은 A-Component/WS-B의 검증된 adapter 및 명시된 모델 의미를 소비하는 별도 PR로 진행한다.

## 2. 지금 시작 가능한 범위

기존 CoolPropBackend의 state_pt/state_ph/state_ps, P02 evaluate_compressor/evaluate_expansion_valve,
P05 evaluate_heat_exchanger_1d, P04 evaluate_pipe_1d를 재사용할 수 있다.
초기 모델은 단일단 R744 transcritical 냉방, 정상상태, fixed-mass-flow, constant-UA, 건식 2차유체다.
냉매 이름은 입력으로 보존하고 미지원 냉매를 대체하지 않는다. 첫 검증 냉매가 R744라는 것이 전 냉매 지원을 뜻하지 않는다.

```text
흡입 → 효율 기반 압축기 → [토출 단상관] → 가스쿨러
     → [고압 단상관] → 등엔탈피 밸브 → 증발기 → [흡입 단상관] → 흡입
```

대괄호 배관은 S3에서 추가한다. 밸브 후단 2상 배관은 P04에 연결하지 않는다.
S1/S2는 배관을 생략하고 HX 압력강하를 0으로 명시한 단순화로 시작한다.
제품 compressor/valve map, HX rated-point 선택, Excel loader, ProductRecord, DB를 생성하거나 호출하지 않는다.
UA를 제품 정격점에서 끌어와 off-design에 재사용하지 않고 별도 시험 시나리오의 가정값으로 제공한다.
압축기 동력은 P02의 냉매 엔탈피 상승에 해당하며 전기 입력동력·모터 효율·팬/펌프 소비전력을 포함하지 않는다.
따라서 초기 COP는 해당 모델의 냉동 COP이며 상용 시스템 전기효율이 아니다.

## 3. 합성 입력 정책

임의값은 재현 가능한 합성 시험 파라미터이며 제품 DB의 대체 자료가 아니다.
사용자의 합성 입력 요청과 개별 수치 선정 근거를 구분해 기록한다. Codex가 고른 값은
AGENT_ASSUMPTION과 scenario ID로 추적하고 USER 실측값/제조사값으로 표시하지 않는다.
모든 시나리오·결과는 is_mock=true, DB version은 N/A — no DB, release 대상 제외다.

**냉매 물성 자체를 임의로 만들지는 않는다.** 실제 R744 회로는 기존 CoolPropBackend를 사용한다.
상수 물성 test double은 별도의 수학/연결 unit test에만 사용하고 실제 냉매 결과와 분리한다.

| 입력군 | 초기 후보 또는 정책 | 출처와 확인 |
|---|---|---|
| 냉매 | R744 | 기존 P02/P05 검증 냉매; property backend 8.0.0 유지 |
| 흡입/토출 절대압 | 3 MPa / 9 MPa | P02 회귀 입력을 초기 후보로 재사용 |
| 냉매 유량 / 등엔트로피 효율 | 0.1 kg/s / 0.8 | P02 회귀 입력; 유량은 계산 결과가 아닌 prescribed 값 |
| 흡입 온도 초기 추정 | 280 K | P02 회귀 기준. 수렴 후 온도를 고정하지 않음 |
| 가스쿨러 UA | 200 W/K 후보 | P05/PR #34 합성 case. 해당 회로에서의 수렴 보장은 없음 |
| 증발기 UA | S0에서 명시적 시험값·범위 선정 | 제조사 근거 없음. 정상/실패 case를 분리해 기록 |
| 2차유체 온도·유량·비열 | S0에서 양쪽 모두 단위 포함으로 지정 | 건식·상수 유효 비열 가정. 누락 시 실행 거부 |
| HX 격자 | 80 cells 후보, 이후 40/80/160 비교 | 기존 1D 검증 방식 참고. 전체 회로 격자오차는 새로 확인 |
| 배관 길이·내경·조도·점도·U′·주변온도 | S3에서 명시 | 단상 적용범위; P04 입력의 점도/U′는 근거 있는 시험 가정 |
| solver 설정 | bracket/bounds, residual scale, tolerance, max_iterations | 실행 전에 case와 함께 버전 고정 |

이 표는 실행 완료 사례가 아니다. S0에서 실제 가용 API/phase와 모든 필수 입력을 확인하고,
S2 첫 reference를 얻은 후 입력 및 기대값을 고정한다. 실패를 숨기려고 tolerance를 바꾸지 않는다.

## 4. 작은 PR별 실행 순서와 통과 기준

### S0 — 입력·상태 연결 명세와 실행 환경

- 계획 병합 후 최신 integration에서 `codex/ws-a/system-s0-harness`와 새 worktree로 시작한다.
- DB 없는 typed scenario, 단위/가정/초기값/모델 경계, 노드 ID와 결과 저장 구조를 만든다.
- 기존 solver 공개 계약을 바꾸지 않고 내부 scenario/diagnostics 모델을 사용한다.
- 이후 HVACSolver adapter가 필요하면 기존 서명을 유지하며 추가 공통 필드가 필요할 때만 ACR을 올린다.
- uv sync --locked 후 필수 입력·단위·비유한 값 거부, JSON roundtrip과 mock 전파를 확인한다.
- solver용 SciPy는 현재 직접 의존성에 없으므로 전이 의존성에 기대어 import하지 않는다.
  S2 scalar bracket 알고리즘은 새 의존성 없이 가능하다. S3의 다변수 알고리즘/직접 의존성 추가는 별도 구현 PR에서 정한다.

### S1 — 한 바퀴 계산 harness (수렴 완료 아님)

- 압축기→가스쿨러→밸브→증발기를 실제 부품 API로 순서대로 호출한다.
- 고압·저압·질량유량·효율·UA·2차유체 조건을 고정하고 흡입 h를 trial로 준다.
- 결과: 모든 노드 p/T/h/rho/phase, 부품별 Q/W, HX profile, 반환 h와 trial h의 잔차.
- 최종 상태를 입력 상태로 덮어써 폐회로가 닫힌 것처럼 만들지 않는다.
- 온도방향·압축기 흡입 phase·부품 적용범위 위반을 원인/노드와 함께 실패로 기록한다.
- 직접 부품 호출과 연결 결과 동일성 및 잘못된 연결을 주입한 회귀가 통과해야 S2로 간다.

### S2 — 첫 단일 운전점 폐회로 수렴

- 초기 S2에서는 HX Δp=0, 배관 없음, p_suction/p_discharge/m_dot는 고정한다.
- 미지수는 h_suction 하나, 방정식은 R_h = h_return - h_suction = 0 하나다.
- 흡입 온도와 열교환기 출구 온도를 동시에 강제하지 않는다. 이들은 계산 결과다.
- 유효 phase/운전범위 안의 연속 구간에서 부호가 바뀌는 bracket을 확인한 경우에만 이분법을 적용한다.
  map 단조성이나 해 존재를 가정하지 않는다. 중간 property/phase 실패를 가로질러 bracket을 연결하지 않는다.
- bracket 미발견, 반복 한도, 정체, property 오류를 구분하고 마지막 유효 잔차를 남긴다.
- 기준안: |R_h| <= 1e-2 J/kg 및 독립 whole-cycle energy relative residual <= 1e-6,
  mass residual <= 1e-12, 최대 100회. S0/S2 구현 시작에 scale·판정식을 확정하여 테스트와 문서에 고정한다.
  이는 제안된 수치 설정이며 실행 PASS나 부품 기존 tolerance 변경이 아니다.
- 같은 유량을 전달해서 mass residual이 0이라는 사실만으로 유량 예측·밸브 용량 일치라고 주장하지 않는다.
- 여러 초기 bracket, 반복 재현성, known-failure, max-iteration, 단위 동등성, 격자 수렴을 검증한다.
- 결과는 'prescribed-pressure/flow synthetic coupled cycle'로 표기한다.

### S3 — 단상 배관과 압력강하 결합

- 토출·고압·흡입 배관과 HX 지정 Δp를 추가한다. 열누설도 전체 에너지식에 부호와 함께 포함한다.
- p_suction/p_discharge/m_dot는 계속 외부 지정한다.
- 후보 미지수 (h_suction, p_valve_outlet), 잔차 (h_return-h_suction, p_return-p_suction)로
  방정식 수를 맞춘다. 유량과 속도/밸브 opening까지 동시에 자유화하지 않는다.
- bounds/scaling/알고리즘을 별도 PR에서 확정하고 압력 잔차 기준안 1 Pa와 전체 보존 기준을 검증한다.
- 역전 압력, 2상 배관 진입, 과도한 Δp, 열교환기 온도교차, 발산을 명시적으로 실패시킨다.
- Δp/열유입 0의 S2 환원과 비영 압력강하 case를 각각 검증한다.

### S4 — 전체 운전맵 생성

- 여기서 '맵'은 부품 연결도 + 지정 운전조건 격자별 전체 회로 결과표/성능맵을 뜻한다.
- 먼저 p_high × sink inlet temperature의 작은 격자를 사용하고 나머지 입력은 고정한다.
- 각 점은 S2/S3 solver를 독립 실행한다. COP/capacity/power, 유량(지정값), 노드 상태,
  반복 횟수, 잔차, 상태 코드 및 실패 이유를 JSON/CSV로 저장한다.
- 유효하지 않은 점을 삭제하거나 보간으로 채우지 않고 전체 시도 점수와 실패율을 함께 보고한다.
- 고정 순서 sweep, cold-start 재검증, warm-start 사용 여부를 기록한다. 성능 최적화와 구분한다.
- CLI runner를 우선하며 GUI/Agent/WS-D optimizer 결합은 이 단계에 넣지 않는다.

S0–S4는 실행 순서이며 한 세션에 모두 구현하지 않는다. 다음 구현 세션은 S0/S1 중 하나의 제한된 범위로 시작한다.

## 5. 검증 및 완료 판정

각 구현 PR은 관련 회귀와 `uv sync --locked`, `uv run --locked pytest`,
`uv run --locked ruff check .`, `uv run --locked ruff format --check .`, `uv run --locked mypy`,
manifest/work-record 검사를 수행한다. physics 변경은 식·기준·단위·출처·허용오차·실제 오차를 남긴다.
동결 schema 호환, 실패 결과의 비성공 상태, 동일 입력 재현성을 별도 확인한다.
전체 수렴의 증거는 실제 각 부품 출력에서 계산한 상태 연속성과 부호 포함 에너지 수지다.
입력으로 구성한 baseline 항등식만으로 전체 1D 결합을 검증하지 않는다.

- 물리 모델 근거: Master Plan §7, 기존 P02/P04/P05 코드 및 검증 문서. 새 상관식 도입 없음.
- 코드 통과와 물리 유효성, 합성 수렴과 제조사 정확도, 로컬 완료와 integration 반영을 구분한다.
- S4 완료도 P06 manufacturer validation 또는 Gate 1 승인이 아니다.
- 미래 Gate 1은 Excel→DesignSpecification→HVACSolver→SimulationResult→ConstraintReport와 WS-E 연결을 별도 검증한다.
- WS-C production constraint 구현/담당, 제품 동력 정의와 off-design HX는 초기 합성 트랙을 막지 않지만 제품/Gate 통합에는 남는 의존성이다.

## 6. 다른 담당자의 시작 지침

A-Component는 기존 부품 경로에서 검증을 계속한다. A-System의 전용 경로를 중복 구현하지 않는다.
A-System은 최신 승인·병합된 부품 SHA만 기준으로 사용한다. 미병합 #35/#36을 몰래 의존성으로 쓰지 않는다.
부품 interface 변경이 필요하면 현재 공통/부품 계약과 영향받는 소비자를 명시하고 양 트랙을 조율한다.
공유 Git 표시는 본 계획 PR·CURRENT_STATE·OWNERSHIP·CODEOWNERS이며 개별 개발자 응답은 아직 요청/수신하지 않았다.
'담당 배정됨', 'PR 게시됨', '수용됨', '병합됨', '수렴 검증됨'을 구분해서 기록한다.
