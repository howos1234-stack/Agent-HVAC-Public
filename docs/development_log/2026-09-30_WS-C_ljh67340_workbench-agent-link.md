# 작업 기록: WS-C 명령과 WS-E 워크벤치 연결

## 식별 및 범위

- 시작 / 종료 시각 및 시간대: 2026-09-30 14:20 +09:00 / 2026-09-30 14:35 +09:00 (Asia/Seoul)
- 수행자 / human owner: LJH / @ljh67340
- Phase / Workstream: P10-P12 / WS-C·WS-E 연결
- 작업 상태: REVIEW_PENDING / 보완 제출
- 사용자 요청과 목표: 관리자 검토 대기 중 가능한 후속 작업을 조사하고, 공개 integration에 병합된 워크벤치를 Agent가 구조화 호출할 수 있는 최소 결정론적 adapter를 구현한다.
- 허용 파일 / 제외 파일: `agents` adapter·합성 테스트·공개 문서·manifest·상태 기록 / LLM SDK, 공통 schema, 물리 solver, 제품 DB, lockfile 제외
- branch / 시작 commit / 종료 checkpoint(확인된 경우): `codex/ws-c/ljh67340/workbench-agent-link` / `d97edf1` / 미정
- 시작 시 기존 변경: 없음; 별도 worktree 사용
- 읽은 문서 및 버전: `README.md`, `AGENTS.md`, `CURRENT_STATE.md`, `WORK_PROTOCOL.md`, agent tool 계약, workbench command adapter @ `d97edf1`
- 의존 작업 / frozen interface: public PR #3 WS-E workbench와 기존 `SimulationResult`; 공통 schema 변경 금지

## 수정 전 계획과 위험

- 대상 모듈 및 의존성: `src/agent_hvac/agents`, 신규 WS-C 합성 회귀 테스트
- 예정 검증: 집중·전체 base/GUI 테스트, Ruff, format, mypy, GUI mypy, manifest, build, 기록 검사
- 위험과 대응: Agent가 누락 수치를 채우거나 실패를 정상으로 표시하지 않도록 해석·누락·project-ready·completed·failed 상태를 분리한다.

## 수행 내용

| 변경 파일 | 변경 내용 및 이유 |
|---|---|
| `src/agent_hvac/agents/workbench.py` | 구조화 command request/response와 명시적 실행 경계 추가 |
| `tests/ws_c/test_workbench_agent.py` | 누락·project-only·완전 실행·모호/거부·solver 실패 5경로 검증 |
| `docs/validation/p00-source-manifest.json` | 신규 source와 test hash 반영 |
| `src/agent_hvac/app/workbench_command.py` | 잘못된 효율 단위와 상충하는 중복 조건을 명령 해석 단계에서 명시적으로 거부 |
| `tests/ws_c/test_workbench_agent.py` | 입력 거부 시 solver 미호출과 미수렴 결과 보존 회귀 추가 |

## 결정, 가정 및 출처

| 항목 | 결정 또는 가정 | 근거/출처 | 영향 및 후속 확인 |
|---|---|---|---|
| 명령 해석 | 기존 `workbench_command` parser만 사용 | PR #3에서 검증된 공개 adapter | 새 자연어 추론이나 LLM 의존성 없음 |
| 실행 경계 | 명시적 execute와 필수 입력 완비가 모두 필요 | 누락값 생성 금지 | 불완전 명령은 `needs_input` |

- 단위 / 물리식 / 상관식 / 제품 데이터 영향: 없음. 기존 parser와 solver를 호출하는 경계만 추가.
- public interface 영향 / ACR 링크: app-private project를 Agent tool response에 노출하는 신규 공개 adapter. frozen schema 변경 없음.
- 코드·의존성·DB·지침 버전 및 재현 설정: Python 3.12, locked dependency; 새 의존성 없음.

## 검증 결과

| 검증 대상 | 정확한 명령 또는 검사 방법 | 환경 | PASS/FAIL/NOT_RUN/BLOCKED | 결과 요약 및 증거 |
|---|---|---|---|---|
| 착수 상태 | `git status --short --branch` | Windows / 별도 worktree | PASS | clean latest integration `d97edf1` |
| WS-C 집중검사 | `uv run --locked --extra gui pytest tests/ws_c -q` | Windows / Python 3.12 | PASS | 5 passed |
| base 전체 | `uv run --locked pytest -q` | Windows / 기존 `.venv` | PASS | 688 passed; clean base-only 환경 증거로 사용하지 않음 |
| GUI 전체 | `uv run --locked --extra gui pytest -q` | Windows / GUI dependency | PASS | 688 passed |
| Ruff/format | `uv run --locked ruff check .`; `ruff format --check .` | Windows | PASS | 164 files formatted |
| mypy | `uv run --locked mypy`; GUI 두 entrypoint 별도 mypy | Windows | PASS | 기본 76 source files, GUI 2 files |
| manifest | `uv run --locked python scripts/source_manifest.py --check` | Windows | PASS | 159 files verified |
| build | `uv build --no-build-isolation` | Windows | PASS | sdist와 wheel 생성 |
| 최초 head 원격 CI | [run 36686253990](https://github.com/howos1234-stack/Agent-HVAC-Public/actions/runs/36686253990) | Windows/Ubuntu × base/gui | PASS | 4/4; 검토 보완 전 head `fcdf50c` |
| 검토 보완 집중검사 | `uv run --locked --extra gui pytest tests/ws_c/test_workbench_agent.py -q` | Windows / GUI | PASS | 8 passed; 잘못된 단위·상충 조건 solver 미호출과 미수렴 결과 보존 포함 |
| 보완 head base 전체 | `uv run --locked pytest -q` | Windows / 기존 GUI-capable 환경 | PASS | 691 passed; clean base-only 환경 증거로 사용하지 않음 |
| 보완 head GUI 전체 | `uv run --locked --extra gui pytest -q` | Windows / GUI dependency | PASS | 691 passed |
| 보완 head 품질·계약 | Ruff, format, mypy, GUI strict mypy, manifest 계약, build | Windows | PASS | 159-file manifest, 계약 9 passed, sdist/wheel 생성 |

- 수치 검증 기준값·단위·출처·허용오차·실제 오차(해당 시): 제품 기준값 없음; 기존 합성 baseline 입력만 사용 예정.
- 실패 재현 및 조치 / 미실행 이유: 최초 테스트의 잘못된 기대 2건은 기존 계약에 맞게 정정했다. 관리자 검토에서 효율의 잘못된 단위와 상충하는 중복 조건이 조용히 승인되는 결함을 재현해 실행 전 거부와 solver 미호출 회귀를 추가했다. 보완 head 로컬 검증은 모두 통과했고 원격 CI는 push 후 확인한다.
- diff 검토 결과: LLM SDK·공통 schema·물리 solver·제품 DB·lockfile 변경 없음. 일반 baseline 결과는 기존 계약대로 `is_mock=false`이며 제조사 제품 검증을 의미하지 않는다.

## 종료 및 인수인계

- 완료한 범위: 구조화 명령 해석, 누락 입력 보존, 명시적 계산 실행, 실패 상태 변환과 회귀 검증.
- 남은 작업 / 알려진 한계 / blocker: PR #8 보완 head 원격 CI와 관리자 재검토. 실제 LLM 연동과 자유형 명령 이해는 별도 범위.
- 다음 담당자와 첫 실행 작업: 관리자가 adapter 상태 경계와 원격 CI를 검토한다.
- `CURRENT_STATE.md` 갱신 여부: 완료.
- Phase checklist / Gate 상태와 증거: 실제 AI 추론·HVAC production·Gate 승인 범위 아님.
- PR / 리뷰 / 승인 / integration merge / CI 상태(없으면 미수행): 공개 PR #8 보완 제출 준비; 최초 head CI 4/4 PASS; 보완 head 로컬 검증 PASS; 새 원격 CI 대기; integration 미병합.
