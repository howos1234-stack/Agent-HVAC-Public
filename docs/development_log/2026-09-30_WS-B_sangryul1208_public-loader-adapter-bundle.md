# 작업 기록: 공개 합성 제품 bundle 전달 검증

## 식별 및 범위

- 시작 / 종료 시각 및 시간대: 2026-09-30 KST / 진행 중
- 수행자 / human owner: WS-B `sangryul1208`
- Phase / Workstream: public repository / WS-B product database
- 작업 상태: REVIEW_PENDING
- 사용자 요청과 목표: PR #5 병합 후 최신 공개 integration에서 다음 WS-B 작업을 진행한다. 합성 compressor·valve·HX workbook을 동시에 적재해 loader → ProductRecord → WS-A adapter 전달 경계를 검증한다.
- 허용 파일 / 제외 파일: 직접 생성한 합성 pytest fixture와 공개 작업 기록만 허용한다. 제조사 자료, 실제 제품 수치, private Git 이력은 제외한다.
- branch / 시작 commit / 종료 checkpoint(확인된 경우): `codex/ws-b/public-loader-adapter-audit` / `0d6f886046a1b8730ee6bf992d8dbac7ccec1d44` / 진행 중.
- 시작 시 기존 변경: 없음.
- 읽은 문서 및 버전: `README.md`, `AGENTS.md`, `CURRENT_STATE.md`, `docs/development/WORK_PROTOCOL.md`, Excel loader·ProductRecord·WS-A adapter 합성 테스트 at `0d6f886`.
- 의존 작업 / frozen interface: ProductRecord 0.2.0, Excel schema 0.2.0, loader 0.2.x, WS-A compressor/valve/HX adapter 계약을 변경하지 않는다.

## 수정 전 계획과 위험

- 대상 모듈 및 의존성: 공개 합성 multi-workbook integration test, 상태·manifest 기록.
- 예정 검증: 세 제품 동시 적재, 고유 ID·source 보존, `is_mock=true`, compressor/valve map adapter 및 HX rated-point adapter 전달, 기존 회귀·Ruff·mypy·manifest·build·CI.
- 위험과 대응: 실제 제품값을 합성 fixture로 위장하지 않는다. 기존 합성 생성기를 사용하고 제품 간 식별자만 결정론적으로 분리한다.

## 수행 내용

| 변경 파일 | 변경 내용 및 이유 |
|---|---|
| `tests/ws_a/test_excel_component_bundle_integration.py` | 세 합성 workbook의 동시 적재, product/map/rated-point/point/value ID 비충돌, source·원단위 보존과 WS-A adapter 전달을 검증한다. |
| `CURRENT_STATE.md` | 공개 bundle 검증 범위와 상태를 기록한다. |
| `docs/validation/p00-source-manifest.json` | 새 합성 회귀와 작업 기록의 source hash를 반영한다. |

## 결정, 가정 및 출처

| 항목 | 결정 또는 가정 | 근거/출처 | 영향 및 후속 확인 |
|---|---|---|---|
| 합성 전용 | 모든 workbook은 pytest 임시경로에서 생성하고 `is_mock=true`를 유지한다. | 공개 저장소 자료 경계와 기존 합성 fixture 계약. | 실제 제조사 검증·production 승인 근거로 사용하지 않는다. |
| provenance 검증 범위 | bundle은 세 제품의 source ID, map/rated-point source와 map/rated 값의 원단위·값별 source prefix를 직접 확인한다. | PR #10 WS-A 검토 요청. | 파일·sheet·row 등 전체 provenance와 정확한 SI 값은 기존 장비별 Excel 통합 테스트가 검증하며 두 범위를 혼동하지 않는다. |

- 단위 / 물리식 / 상관식 / 제품 데이터 영향: 없음.
- public interface 영향 / ACR 링크: 없음. 기존 공개 계약의 통합 회귀만 추가한다.
- 코드·의존성·DB·지침 버전 및 재현 설정: 새 의존성 없음.

## 검증 결과

| 검증 대상 | 정확한 명령 또는 검사 방법 | 환경 | PASS/FAIL/NOT_RUN/BLOCKED | 결과 요약 및 증거 |
|---|---|---|---|---|
| bundle 집중 회귀 | `python -m pytest -q -p no:cacheprovider --basetemp=.artifact_work/pytest-bundle tests/ws_a/test_excel_component_bundle_integration.py` | Windows | PASS | 1 passed. |
| bundle + 기존 장비별 Excel 통합 | `python -m pytest -q -p no:cacheprovider --basetemp=.artifact_work/pytest-bundle-final tests/ws_a/test_excel_component_bundle_integration.py tests/ws_a/test_excel_compressor_integration.py tests/ws_a/test_excel_valve_integration.py tests/ws_a/test_excel_hx_integration.py` | Windows | PASS | 7 passed. |
| 관련 전체 회귀 | `PYTHONPATH=src python -m pytest -q --tb=short -p no:cacheprovider --basetemp=.artifact_work/pytest-wsb-wsa-bundle-final tests/contracts tests/ws_b tests/ws_a` | Windows, GUI 의존성 환경 | PASS | 344 passed. |
| 전체 GUI 회귀 | `PYTHONPATH=src python -m pytest -q --tb=short -p no:cacheprovider --basetemp=.artifact_work/pytest-full-bundle-public-final2` | Windows, GUI 의존성 환경 | BLOCKED | 52% 이후 WS-E AppTest 구간이 장시간 정체되어 수동 중단했다. 수치 실패나 새 bundle 실패는 관찰되지 않았으며 원격 base/gui CI에서 재검증한다. |
| Ruff | `ruff check .`, `ruff format --check .` | Windows | PASS | 162 files formatted. |
| mypy | `mypy`, `mypy src/agent_hvac/app/streamlit_app.py` | Windows | PASS | 75 source files와 GUI entry 통과. |
| 공개자료 경계 | `python scripts/check_public_data_boundary.py` | Windows | PASS | 허용 template·GUI 증빙 외 제한 artifact와 component data 없음. |
| source manifest | `python scripts/source_manifest.py --write`, `--check` | Windows | PASS | 158 files. |
| build | `python -m build --no-isolation` | Windows | PASS | sdist와 wheel 생성. |
| 최초 원격 CI | PR #10 head `30f87573434b1a81e4c2b01f75a15dea7c849776`, [run 36694757988](https://github.com/howos1234-stack/Agent-HVAC-Public/actions/runs/36694757988) | GitHub Actions | PASS | Windows/Ubuntu × base/gui 4/4 PASS. manifest·공개자료 경계·pytest·build 단계 포함. |
| 보완 head 원격 CI | PR #10 보완 head | GitHub Actions | NOT_RUN | ID·provenance assertion 보완 push 후 재실행한다. |

- 수치 검증 기준값·단위·출처·허용오차·실제 오차(해당 시): 기존 합성 fixture 기준만 사용하며 실제 제품 허용오차와 무관하다.
- 실패 재현 및 조치 / 미실행 이유: 최초 Ruff 검사에서 긴 assertion 1건을 확인해 formatter로 정정했다. 첫 전체 테스트는 재사용 venv가 private editable package를 우선 참조해 공개 WS-E module collection이 실패하여 `PYTHONPATH=src`로 수정했다. 이후 전체 GUI 실행은 WS-E AppTest 장시간 정체로 중단했으나 직접 관련된 contracts·WS-B·WS-A 344개는 완주했다. WS-A 보완 후 첫 관련 회귀는 manifest 갱신 전이라 343 passed/manifest 1 failed였고 `source_manifest.py --write` 후 344 passed로 재확인했다.
- diff 검토 결과: production loader·ProductRecord·WS-A adapter 구현은 변경하지 않고 합성 통합 회귀와 기록만 추가한다.

## 종료 및 인수인계

- 완료한 범위: 합성 3종 workbook 동시 적재와 WS-A adapter 전달 회귀.
- 남은 작업 / 알려진 한계 / blocker: 공개 PR의 Windows/Ubuntu × base/gui CI와 검토. 로컬 전체 GUI AppTest 완주는 BLOCKED 상태다.
- 다음 담당자와 첫 실행 작업: WS-A는 기존 adapter 소비 계약 유지 여부를 검토한다.
- `CURRENT_STATE.md` 갱신 여부: 갱신.
- Phase checklist / Gate 상태와 증거: CV-1~CV-3, P06 전체, production 및 Gate 상태 변경 없음.
- PR / 리뷰 / 승인 / integration merge / CI 상태(없으면 미수행): 공개 PR #10, WS-A 보완 요청 반영 중, 미병합. 최초 head CI 4/4 PASS, 보완 head CI NOT_RUN.
