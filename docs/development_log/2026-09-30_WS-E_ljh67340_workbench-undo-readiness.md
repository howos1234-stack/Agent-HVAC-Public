# 작업 기록: WS-E 워크벤치 Undo와 입력 준비도 개선

## 식별 및 범위

- 시작 / 종료 시각 및 시간대: 2026-09-30 17:10 +09:00 / 2026-09-30 17:45 +09:00 (Asia/Seoul)
- 수행자 / human owner: LJH / @ljh67340
- Phase / Workstream: P12 / WS-E
- 작업 상태: REVIEW_PENDING
- 사용자 요청과 목표: 관리자 검토 대기 중 GUI 사용성을 실제 브라우저에서 점검하고 편집 실수 복구와 누락 입력 발견성을 개선한다.
- 허용 파일 / 제외 파일: WS-E app·canvas asset·합성 GUI 테스트·공개 기록·manifest / 공통 schema, 물리 solver, 제품 DB, lockfile 제외
- branch / 시작 commit / 종료 checkpoint(확인된 경우): `codex/ws-e/ljh67340/workbench-ux-followup` / `d97edf1f5854e44607d657d58710d320f5c8fa94` / 미정
- 시작 시 기존 변경: 없음; 별도 worktree 사용
- 읽은 문서 및 버전: `AGENTS.md`, `CURRENT_STATE.md`, `WORK_PROTOCOL.md`, WS-E app/tests @ `d97edf1`
- 의존 작업 / frozen interface: integrated public PR #3 workbench; 공통 schema와 baseline solver 계약 유지

## 수정 전 계획과 위험

- 대상 모듈 및 의존성: Streamlit session history, canvas shortcut event, condition editor
- 예정 검증: WS-E 집중·전체 base/GUI, Ruff, format, mypy, manifest, build, 실제 브라우저 추가/Undo/Redo 확인
- 위험과 대응: history에는 검증된 WorkbenchProject JSON만 저장하고 최대 50단계로 제한한다. 복원 시 계산 결과와 widget 상태를 제거한다.

## 수행 내용

| 변경 파일 | 변경 내용 및 이유 |
|---|---|
| `src/agent_hvac/app/design_workbench_app.py` | 검증된 프로젝트 JSON snapshot 기반 50단계 Undo/Redo와 결과 무효화, 누락 조건 자동 펼침 |
| `src/agent_hvac/app/workbench_canvas_component.py` | 캔버스 `Ctrl+Z`, `Ctrl+Y`, `Ctrl+Shift+Z` 단축키와 도움말 |
| `tests/ws_e/test_design_workbench.py` | 추가/삭제 Undo, Redo, 결과 무효화, 초기 입력 준비도, 단축키 wiring 회귀 |
| `CURRENT_STATE.md` | 검토 대기 범위와 한계 기록 |

## 결정, 가정 및 출처

| 항목 | 결정 또는 가정 | 근거/출처 | 영향 및 후속 확인 |
|---|---|---|---|
| history | 프로젝트 전체 JSON snapshot, 50단계 | 기존 엄격 JSON loader와 project fingerprint | 모든 편집 유형을 동일하게 복원 |
| 결과 상태 | Undo/Redo 때 기존 계산 결과 삭제 | stale 결과 금지 규칙 | 복원 후 재계산 필요 |

- 단위 / 물리식 / 상관식 / 제품 데이터 영향: 없음.
- public interface 영향 / ACR 링크: GUI session 동작과 canvas action만 추가; frozen interface 변경 없음.
- 코드·의존성·DB·지침 버전 및 재현 설정: Python 3.12, Streamlit locked GUI extra; 새 의존성 없음.

## 검증 결과

| 검증 대상 | 정확한 명령 또는 검사 방법 | 환경 | PASS/FAIL/NOT_RUN/BLOCKED | 결과 요약 및 증거 |
|---|---|---|---|---|
| 실제 브라우저 사전 점검 | local Streamlit `8520`, in-app Chromium | Windows | PASS | 기본 입력 4/6인데 조건 편집기가 닫혀 있고 편집 복구가 없음을 확인 |
| 실제 브라우저 중간 점검 | 부품 추가 후 sidebar Undo | Windows / in-app Chromium | PASS | 4→5개, history 1단계, Undo로 4개 복구와 Redo 활성화 확인 |
| WS-E 집중 | `uv run --locked --extra gui pytest tests/ws_e/test_design_workbench.py -q` | Windows / GUI | PASS | 55 passed |
| Ruff / format | `uv run --locked ruff check ...`; `uv run --locked ruff format --check ...` | Windows | PASS | 3개 변경 코드 파일 통과 |
| GUI strict mypy | `uv run --locked --extra gui mypy --strict src/agent_hvac/app/streamlit_app.py src/agent_hvac/app/design_workbench_app.py` | Windows / GUI | PASS | 2개 진입점 통과 |
| 전체 base 사전 실행 | `uv run --locked pytest -q` | Windows / 기존 GUI-capable 환경 | FAIL | 683 passed, manifest 갱신 전 계약 검사 1건만 실패 |
| 전체 GUI 사전 실행 | `uv run --locked --extra gui pytest -q` | Windows / GUI | FAIL | 683 passed, manifest 갱신 전 계약 검사 1건만 실패 |
| source manifest와 계약 | `uv run --locked python scripts/source_manifest.py --write`; 계약 집중 검사 | Windows | PASS | 157 files, 계약 9 passed |
| 전체 base 최종 | `uv run --locked pytest -q` | Windows / 기존 GUI-capable 환경 | PASS | 684 passed |
| 전체 GUI 최종 | `uv run --locked --extra gui pytest -q` | Windows / GUI | PASS | 684 passed |
| 전체 품질 | `uv run --locked ruff check .`; `uv run --locked ruff format --check .`; `uv run --locked mypy src` | Windows | PASS | Ruff/format 162 files, mypy 75 source files 통과 |
| package build | `uv build` | Windows | PASS | sdist와 wheel 생성 |

- 수치 검증 기준값·단위·출처·허용오차·실제 오차(해당 시): 해당 없음.
- 실패 재현 및 조치 / 미실행 이유: 전체 사전 검사에서 새 테스트 때문에 source manifest만 불일치했다. manifest를 157 files로 갱신한 뒤 계약 검사와 전체 base/GUI를 재실행해 모두 통과했다.
- diff 검토 결과: 공통 schema, solver, 제품 DB, lockfile 변경 없음.

## 종료 및 인수인계

- 완료한 범위: 프로젝트 편집 history, 단축키, 누락 입력 자동 펼침과 합성 회귀.
- 남은 작업 / 알려진 한계 / blocker: 원격 CI와 관리자 검토. 브라우저에서 sidebar 동작은 확인했으며 OS별 단축키 실제 키 입력은 자동 회귀로 보완했다.
- 다음 담당자와 첫 실행 작업: 관리자가 PR diff와 원격 CI를 검토한다.
- `CURRENT_STATE.md` 갱신 여부: 완료.
- Phase checklist / Gate 상태와 증거: GUI 편집 UX이며 production·CV·Gate 승인 아님.
- PR / 리뷰 / 승인 / integration merge / CI 상태(없으면 미수행): PR과 원격 CI는 제출 전.
