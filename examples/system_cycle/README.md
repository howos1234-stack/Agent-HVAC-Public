# DB 없는 R744 단일 순회 예제

이 예제는 합성 입력으로 기존 압축기 → 가스쿨러 → 밸브 → 증발기를 한 번 계산합니다.
**수렴 solver가 아니며, 실행 성공이어도 cycle_converged=false입니다.**

저장소 루트에서:

```powershell
uv sync --locked
uv run --locked python scripts/run_system_cycle.py --input examples/system_cycle/r744_single_pass.json --output artifacts/system_cycle/r744_single_pass.json
```

현재 로컬 전용 worktree에서 bundled uv 사용 시:

```powershell
Set-Location E:\Agent-HVAC\.tools\workstreams\ws-a-system-harness
& 'E:\Agent-HVAC\.tools\uv-package\bin\uv.exe' run --locked python scripts/run_system_cycle.py --input examples/system_cycle/r744_single_pass.json --output artifacts/system_cycle/r744_single_pass.json
```

입력 JSON에서 압력·유량·효율·UA·2차유체 경계조건과 격자 수를 바꿉니다. 모든 값은 합성
시험 가정이며 DB나 제조사 자료를 사용하지 않습니다. 냉매 물성은 CoolProp입니다.
미지원 냉매를 다른 냉매로 바꾸거나 누락 입력을 자동 보충하지 않습니다.

출력 JSON은 원본 입력(원단위 포함), 입력/코드/lock hash, canonical 시나리오, 다섯 노드 상태,
네 부품의 열량·동력 및 모델 경로, HX 전체 cell profile과 열린 회로 잔차를 보존합니다.
에너지 전달 오차가 작아도 회로 폐쇄 잔차가 0이라는 뜻은 아닙니다. COP는 아직 출력하지 않습니다.
흡입 trial 노드와 return 노드를 구분하며 return이 2상이더라도 다음 압축이 유효하다고 간주하지 않습니다.

CLI 종료 코드:
- 0: 단일 순회 평가 완료. 폐회로 수렴·제품 검증 완료가 아님.
- 1: 부품 물리/수치 실패. failed_stage, message, 직전까지의 결과를 JSON에 저장.
- 2: 입력 또는 파일 I/O 오류. 기존 결과를 정상 결과로 바꾸지 않음.

잘못된 예: is_mock=false, 누락된 2차유체 유량, 역전 압력, 잘못된 단위는 실행 전 거부합니다.
과냉 액체 압축기 흡입, 가스쿨러보다 뜨거운 냉각 유체, 증발기보다 차가운 열원은 부품 오류로
보고합니다. 오류를 abs/clamp/default/fallback으로 숨기지 않습니다.

자세한 검증과 한계: [S1 검증 기록](../../docs/workstreams/ws_a/system/S1_HARNESS_VALIDATION.md).


## S2: 고정 압력·유량 단일 운전점 폐회로 수렴

```powershell
uv run --locked python scripts/run_system_cycle.py --mode closed-loop --input examples/system_cycle/r744_closed_loop.json --output artifacts/system_cycle/r744_closed_loop.json
```

S2는 `scenario`와 `settings`를 함께 받습니다. settings의 엔탈피 구간을 scan한 뒤
유효한 인접 점의 부호변화 구간을 이분법으로 좁힙니다. 냉매 물성은 실제 CoolProp을 사용합니다.
S1의 trial_suction_temperature는 원본 메타데이터로 남으며 S2의 고정 경계조건이 아닙니다.
압력·유량·효율·UA·2차유체 조건은 합성 입력이며 압력/유량 자체를 푸는 solver가 아닙니다.

출력에는 전체 반복 이력, 시도 엔탈피, 실패 원인과 최종 회로 상태가 있습니다.
외부 `result.cycle_converged=true`일 때만 COP가 제공됩니다. 내부 `last_evaluation`은
단일 순회 결과이므로 그 객체의 cycle_converged는 항상 false입니다.
CLI exit 0은 폐회로 수렴, 1은 미수렴, 2는 입력/I/O 오류입니다.
S1 기본 모드와 기존 실행 명령은 그대로 유지됩니다.

기본 80-cell 예제는 160-cell 비교에서 COP 1% 이내 기준을 통과합니다.
40-cell 시험은 1.25% 차이로 이 해상도 기준을 실패했으므로 사용하지 않습니다.
격자 정확도와 root 수렴은 별개입니다. 상세 수치·한계는
[S2 검증 기록](../../docs/workstreams/ws_a/system/S2_CONVERGENCE_VALIDATION.md)을 참조합니다.


## 배관 포함 폐회로 및 운전맵

사용자 위임에 따른 현재 합성 경로는 S2의 지정 압력/유량을 유지하며,
밸브 출구 압력을 추가로 풀어 배관/HX 손실 후 흡입 압력까지 맞춥니다.
기존 P04/P05 함수와 실제 CoolProp을 사용합니다. 모든 입력/결과는 mock입니다.

```powershell
uv sync --locked
uv run --locked python scripts/run_system_cycle.py --mode closed-loop --input examples/system_cycle/r744_network.json --output artifacts/system_cycle/r744_network.json
uv run --locked python scripts/run_system_cycle.py --mode map --input examples/system_cycle/r744_operating_map.json --output artifacts/system_cycle/r744_operating_map.json --csv artifacts/system_cycle/r744_operating_map.csv
```

맵은 85/90 bar(a) × 냉각측 290/295/400 K의 6점입니다. 400 K는 실패점 기록을 확인하기 위한
의도적인 시험 조건입니다. `base`에서 유량/흡입 압력/UA/배관/경계조건을 설정하고,
`discharge_pressures`, `sink_inlet_temperatures`에서 축을 설정합니다.
`max_points`는 명시적 계산 상한(최대100)이며 단위 변환 후 중복 좌표는 거부합니다.
배관 점도/Uprime·HX Δp는 해당 source_ref에 기록한 합성 값입니다.

네트워크 예제는 토출→가스쿨러 전 배관, 가스쿨러→밸브 전 배관, 증발기→흡입 배관을 포함합니다.
2상 배관, 역전 압력, HX 온도 방향 오류 및 수치 검사 실패는 실패로 반환합니다.
작은 열누설에서 기존 P04의 1e-12 energy 기준에 걸리는 경우도 성공으로 숨기지 않습니다.
배관 cell profile, HX profile 및 압력 내부 반복 이력은 전체 JSON에 저장합니다.

각 점은 같은 초기 구간으로 cold-start하며 실패점을 제거하거나 보간하지 않습니다.
JSON에는 모든 원입력/단위, code/source/lock hash, 노드/부품/반복/실패가 남고 CSV는 요약입니다.
CSV의 성능 칸은 수렴점만 채웁니다. 지정 유량과 냉매측 COP임을 명시합니다.
맵 CLI exit 0은 모든 점 수렴, exit 1은 파일 생성 완료지만 하나 이상 실패, exit 2는 입력/I/O 오류입니다.
따라서 기본 400 K 실패점이 포함된 예제의 exit 1은 맵 생성 실패와 구분해야 합니다.

계약·수치 결정: [결정 기록](../../docs/workstreams/ws_a/system/SYNTHETIC_MAP_DECISIONS.md).
실측·검증·한계: [네트워크/맵 검증](../../docs/workstreams/ws_a/system/SYNTHETIC_MAP_VALIDATION.md).

## 3축 운전 범위와 수렴 민감도

`r744_range_map.json`은 압력3 × 온도2 × 지정 유량3의 18점 cold-start 입력이다.
선택적 `mass_flows`를 생략하면 기존 2D 예제가 그대로 동작한다. 유량은 예측값이 아니며
실패점도 JSON/CSV에 보존한다. `stability/*.json`은 탐색구간 및 HX 격자 비교 입력이다.
명령·조건·실제 결과 및 부품 한계는
[운전 범위 검증](../../docs/workstreams/ws_a/system/MAP_RANGE_VALIDATION.md)을 따른다.
