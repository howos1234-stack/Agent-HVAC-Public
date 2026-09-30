# 작업 기록: 공개 다중 workbook 오류 격리와 reload 회귀

## 식별 및 범위

- 시작 / 종료 시각 및 시간대: 2026-09-30 20:06 KST / 진행 중
- 수행자 / human owner: Codex / sangryul1208
- Phase / Workstream: WS-B 공개 제품 DB 합성 회귀
- 작업 상태: REVIEW_PENDING
- 사용자 요청과 목표: PR #10 정상 bundle을 확장해 workbook 오류 격리, 중복 ID, 잘못된 참조, reload add/modify/delete 및 복구를 검증한다.
- 허용 파일 / 제외 파일: 합성 pytest·공개 작업 기록·CURRENT_STATE·manifest만 허용. 제조사 자료·실제 제품 수치·private Git 이력은 제외한다.
- branch / 시작 commit / 종료 checkpoint(확인된 경우): `codex/ws-b/public-loader-reload-isolation` / `7277b752ac8493d76cd8e7f1f8041cebdd7bb95c` / 최초 head `93ffe2165c3d07c0cca524baf7ab73aa22756383`, 보완 진행 중
- 시작 시 기존 변경: 없음
- 읽은 문서 및 버전: `AGENTS.md`, `README.md`, `CURRENT_STATE.md`, `docs/development/WORK_PROTOCOL.md`, PR #10 합성 bundle 테스트
- 의존 작업 / frozen interface: ProductRecord 0.2.0, Excel schema 0.2.0, loader 0.2.x 및 기존 격리 계약을 변경하지 않는다.

## 수정 전 계획과 위험

- 대상 모듈 및 의존성: `ExcelComponentRepository.reload()`의 기존 동작을 새 합성 통합 회귀로 검증한다.
- 예정 검증: 단일 workbook 파손, 파일 간 중복 product ID, 교차 workbook source 참조, add/modify/delete 및 복구, database version, stale record/source 비재사용.
- 위험과 대응: 기존 단위 테스트와 중복되지 않도록 3제품 bundle의 연속 상태 변화를 검증한다. 구현 결함은 먼저 재현하며 계약을 임의 변경하지 않는다.

## 수행 내용

| 변경 파일 | 변경 내용 및 이유 |
|---|---|
| `tests/ws_a/test_excel_component_bundle_reload.py` | 합성 다중 workbook의 오류 격리·reload·복구 회귀 추가 |
| 본 작업 기록 | 범위·검증·경계를 공개 가능한 내용으로 기록 |
| `CURRENT_STATE.md` | 진행 범위와 검증 상태 기록 |
| `docs/validation/p00-source-manifest.json` | 새 공개 합성 회귀 파일 등록 |
| latest integration merge | PR #6을 포함한 `75755f9` 반영 및 CURRENT_STATE 양쪽 이력 보존 |

## 결정, 가정 및 출처

| 항목 | 결정 또는 가정 | 근거/출처 | 영향 및 후속 확인 |
|---|---|---|---|
| 격리 단위 | workbook fatal 오류는 해당 파일, 상세 참조 오류는 해당 parent만 격리 | 승인된 loader 계약과 기존 회귀 | 정상 제품과 독립 record가 유지돼야 함 |
| fixture | pytest 임시경로에서 직접 생성한 합성 workbook만 사용 | 공개 저장소 데이터 경계 | 실제 제조사 검증을 의미하지 않음 |

- 단위 / 물리식 / 상관식 / 제품 데이터 영향: 없음. 합성 값과 기존 변환 경로만 사용한다.
- public interface 영향 / ACR 링크: 없음. 계약 변경 없이 기존 동작을 검증한다.
- 코드·의존성·DB·지침 버전 및 재현 설정: 최신 공개 integration `7277b75` 기준.

## 검증 결과

| 검증 대상 | 정확한 명령 또는 검사 방법 | 환경 | PASS/FAIL/NOT_RUN/BLOCKED | 결과 요약 및 증거 |
|---|---|---|---|---|
| 신규 집중 회귀 | private 작업환경 Python으로 public `src`를 우선 import하고 `pytest -p no:cacheprovider --basetemp=.test-tmp/reload-focused tests/ws_a/test_excel_component_bundle_reload.py -q` 실행 | Windows local | PASS | 4 passed |
| bundle 및 장비별 Excel 통합 | 동일 실행기로 bundle/reload/compressor/valve/HX 통합 파일 5개 실행 | Windows local | PASS | 11 passed |
| 관련 전체 회귀 최초 실행 | 동일 실행기로 `tests/contracts tests/ws_b tests/ws_a -q` 실행 | Windows local | FAIL | manifest 갱신 전 manifest 검사 1건만 실패, 347 passed |
| 관련 전체 회귀 최종 실행 | 동일 실행기로 `tests/contracts tests/ws_b tests/ws_a -q` 실행 | Windows local | PASS | 348 passed |
| Ruff 집중 검사 | `python -m ruff check tests/ws_a/test_excel_component_bundle_reload.py` 및 `python -m ruff format --check ...` | Windows local | PASS | format 1회 적용 후 check/format PASS |
| Ruff 전체 검사 | `python -m ruff check .`; `python -m ruff format --check src tests scripts` | Windows local | PASS | check PASS; 135 files formatted |
| mypy | `python -m mypy`; `python -m mypy src/agent_hvac/app/streamlit_app.py` | Windows local | PASS | 75 source files + GUI entry 1 file |
| source manifest | `python scripts/source_manifest.py --write`; `python scripts/source_manifest.py --check` | Windows local | PASS | 159 files verified |
| 공개자료 경계 | `python scripts/check_public_data_boundary.py` | Windows local | PASS | 빈 15-sheet template 1개, 제한 자료 없음 |
| package build | `python -m build --no-isolation` | Windows local (sandbox 밖 임시경로) | PASS | sdist/wheel 생성 |
| 최초 head 원격 CI | [Foundation CI run 36710170632](https://github.com/howos1234-stack/Agent-HVAC-Public/actions/runs/36710170632) | GitHub Windows/Ubuntu × base/gui | PASS | head `93ffe21`, 4/4 PASS; 보완 head 결과와 구분 |
| WS-A 보완 Excel 통합 | 동일 실행기로 bundle/reload/compressor/valve/HX 통합 파일 5개 실행 | Windows local | PASS | 정상 adapter 사용·격리 정격점 선택 실패·복구 후 재사용 포함 11 passed |
| 최신 integration 관련 전체 회귀 | 동일 실행기로 `tests/contracts tests/ws_b tests/ws_a -q` 실행 | Windows local | PASS | `75755f9` 반영 후 352 passed |
| 보완 head 정적 검사 | `python -m ruff check src tests scripts`; `python -m ruff format --check src tests scripts`; `python -m mypy`; GUI entry mypy | Windows local | PASS | Ruff 138 files, mypy 77 source files + GUI entry |
| 보완 head manifest·경계 | `python scripts/source_manifest.py --write/--check`; `python scripts/check_public_data_boundary.py` | Windows local | PASS | manifest 162 files, 공개 제한 자료 없음 |
| 보완 head package build | `python -m build --no-isolation` | Windows local (sandbox 밖 임시경로) | PASS | sdist/wheel 생성 |

- 수치 검증 기준값·단위·출처·허용오차·실제 오차(해당 시): 해당 없음.
- 실패 재현 및 조치 / 미실행 이유: 표준 `uv`가 로컬 PATH에 없어 기존 GUI-capable Python 환경으로 public `src`를 명시적으로 우선 import했다. pytest 기본 임시경로 권한 문제는 workspace `--basetemp`로 격리했다. 최초 전체 관련 회귀의 유일한 실패는 새 테스트 등록 전 manifest 불일치였으며 manifest를 갱신했다.
- diff 검토 결과: production 코드 변경 없음. 합성 테스트·상태·작업 기록·manifest만 변경. 제조사 자료·실제 제품 수치 없음.

## 종료 및 인수인계

- 완료한 범위: 다중 workbook의 fatal 오류, 중복 product ID, 잘못된 source 참조, add/modify/delete, stale 제거와 수정 후 복구 회귀 및 로컬 관련 검증.
- 남은 작업 / 알려진 한계 / blocker: WS-A 요청 보완의 로컬 재검증, 새 head push와 Windows/Ubuntu × base/gui CI, 최종 검토·병합.
- 다음 담당자와 첫 실행 작업: WS-A가 loader → ProductRecord → adapter 소비 관점의 격리 범위를 검토한다.
- `CURRENT_STATE.md` 갱신 여부: 완료.
- Phase checklist / Gate 상태와 증거: CV-1~CV-3, P06 전체, production 및 Gate 상태 변경 없음.
- PR / 리뷰 / 승인 / integration merge / CI 상태(없으면 미수행): 공개 PR [#11](https://github.com/howos1234-stack/Agent-HVAC-Public/pull/11) 제출. 최초 head `93ffe21` CI 4/4 PASS, WS-A 보완 요청 수신. 보완 head 리뷰·승인·병합 및 원격 CI는 NOT_RUN.
