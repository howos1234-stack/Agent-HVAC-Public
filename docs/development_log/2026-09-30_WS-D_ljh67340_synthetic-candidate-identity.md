# 작업 기록: WS-D synthetic 후보 식별성 회귀 보강

## 식별 및 범위

- 시작 / 종료 시각 및 시간대: 2026-09-30 13:45 +09:00 / 2026-09-30 13:58 +09:00 (Asia/Seoul)
- 수행자 / human owner: LJH / @ljh67340
- Phase / Workstream: P09 / WS-D
- 작업 상태: REVIEW_PENDING (public PR #7)
- 사용자 요청과 목표: 공개 PR #3 관리자 검토 대기 중 독립적으로 진행 가능한 작업을 조사하고, P09 synthetic 탐색의 후보 식별성 공백을 보강한다.
- 허용 파일 / 제외 파일: P09 synthetic optimizer·합성 회귀 테스트·공개 작업 기록·manifest·현재 상태 / WS-E PR #3 파일, 공통 schema, 물리 solver, 제품 DB, lockfile 제외
- branch / 시작 commit / 종료 checkpoint(확인된 경우): `codex/ws-d/ljh67340/synthetic-search-audit` / `041121cf7036409d160f462aab87a163a05a8cc6` / 구현 commit `f5d95cb19dee5b75ec2d91e3e82b77db88f812db`
- 시작 시 기존 변경: 없음
- 읽은 문서 및 버전: `AGENTS.md`, `CURRENT_STATE.md`, `docs/development/WORK_PROTOCOL.md`, P09 구현·테스트 @ `041121c`
- 의존 작업 / frozen interface: 기존 `DesignOptimizer`, `DesignProblem`, `OptimizationResult` 계약 유지

## 수정 전 계획과 위험

- 대상 모듈 및 의존성: `optimization/synthetic_search.py`, `tests/ws_d/test_synthetic_search.py`
- 예정 검증: P09 집중 테스트, 전체 base/GUI 테스트, Ruff, format, mypy, manifest, build, 작업 기록 검사
- 위험과 대응: 중복 후보를 조용히 제거하면 입력 오류를 숨기므로 탐색 전에 명시적 failed 결과로 거부하고 solver·조합 생성 미호출을 검증한다.

## 수행 내용

| 변경 파일 | 변경 내용 및 이유 |
|---|---|
| `src/agent_hvac/optimization/synthetic_search.py` | 중복 candidate `product_id`를 조합 생성 전에 선형 시간으로 탐지하고 기존 failed 결과로 명시적 거부 |
| `tests/ws_d/test_synthetic_search.py` | 중복 ID 입력에서 assignments·product combinations·solver가 호출되지 않는 회귀 추가 |
| `docs/validation/p00-source-manifest.json` | 변경 source hash 갱신 |

## 결정, 가정 및 출처

| 항목 | 결정 또는 가정 | 근거/출처 | 영향 및 후속 확인 |
|---|---|---|---|
| 후보 식별자 | 한 탐색 입력 안의 `product_id`는 유일해야 함 | 후보 design ID와 순위의 결정론적 식별성 | 중복 입력만 탐색 전에 거부 |

- 단위 / 물리식 / 상관식 / 제품 데이터 영향: 없음. synthetic 입력 검증만 변경.
- public interface 영향 / ACR 링크: frozen schema 변경 없음. 기존 failed `OptimizationResult` 경로 사용.
- 코드·의존성·DB·지침 버전 및 재현 설정: Python 3.12, locked dependency; DB·lockfile 변경 없음.

## 검증 결과

| 검증 대상 | 정확한 명령 또는 검사 방법 | 환경 | PASS/FAIL/NOT_RUN/BLOCKED | 결과 요약 및 증거 |
|---|---|---|---|---|
| 착수 상태 | `git status --short --branch` | Windows / PowerShell | PASS | clean `origin/integration` 기반 별도 브랜치 |
| P09 집중 테스트 | `uv run --locked pytest tests/ws_d/test_synthetic_search.py -q` | Windows / Python 3.12 | PASS | 10 passed |
| WS-D 전체 | `uv run --locked pytest tests/ws_d -q` | Windows / Python 3.12 | PASS | 10 passed |
| base 전체 | `uv run --locked pytest -q` | Windows / 기존 `.venv` | PASS | 618 passed; 별도 clean base-only 환경 증거로 사용하지 않음 |
| GUI 전체 | `uv run --locked --extra gui pytest -q` | Windows / GUI dependency | PASS | 618 passed |
| 정적 검사 | `uv run --locked ruff check .`; `ruff format --check .`; `mypy` | Windows | PASS | 151 files formatted, 72 source files typed |
| manifest | `uv run --locked python scripts/source_manifest.py --check` | Windows | PASS | 150 files verified |
| build | `uv build --no-build-isolation` | Windows | PASS | sdist와 wheel 생성 |
| 최신 integration 집중검사 | `uv run --locked pytest tests/ws_d/test_synthetic_search.py tests/ws_e -q` | Windows / Python 3.12 | PASS | PR #3 병합 commit `49dcfbc` 반영 후 131 passed |
| GUI 진입점 mypy | `uv run --locked --extra gui mypy src/agent_hvac/app/streamlit_app.py src/agent_hvac/app/design_workbench_app.py` | Windows | PASS | 최신 integration의 두 GUI entrypoint 통과 |

- 수치 검증 기준값·단위·출처·허용오차·실제 오차(해당 시): 해당 없음.
- 실패 재현 및 조치 / 미실행 이유: 같은 `product_id`를 가진 서로 다른 mock 제품 두 개가 기존에는 같은 candidate design ID를 생성할 수 있었다. 새 검증은 탐색 materialization 전에 failed 결과를 반환한다. 원격 CI는 PR push 후 확인 예정.
- diff 검토 결과: 공통 schema·물리 solver·WS-E PR #3·제품 DB·lockfile 변경 없음. 합성 fixture만 사용.

## 종료 및 인수인계

- 완료한 범위: P09 후보 식별자 중복 사전 거부, 회귀 테스트, 로컬 전체 검증.
- 남은 작업 / 알려진 한계 / blocker: public PR #7의 최신 integration 반영 head 원격 CI와 관리자 리뷰.
- 다음 담당자와 첫 실행 작업: 관리자가 새 PR의 중복 후보 거부 범위와 원격 CI를 검토한다.
- `CURRENT_STATE.md` 갱신 여부: 완료.
- Phase checklist / Gate 상태와 증거: mock synthetic 범위이며 실제 HVAC·production·Gate 승인 아님.
- PR / 리뷰 / 승인 / integration merge / CI 상태(없으면 미수행): public PR #7 REVIEW_PENDING; 최초 head 원격 CI 실행 중에 integration이 전진해 최신 `49dcfbc`를 merge했으며 새 head CI 재실행 예정; integration 미병합.
