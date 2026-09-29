# 작업 기록: WS-E 설계 워크벤치 공개 저장소 이관

## 식별 및 범위

- 시작 / 종료 시각 및 시간대: 2026-09-29 22:01:21 +09:00 / 2026-09-29 22:38:14 +09:00 (Asia/Seoul)
- 수행자 / human owner: LJH / @ljh67340
- Phase / Workstream: P12 / WS-E
- 작업 상태: LOCAL_VALIDATED / PR 준비
- 사용자 요청과 목표: private 작업 브랜치의 공개 가능한 설계 워크벤치 코드와 합성 테스트를 새 공개 저장소로 선별 이관하고 실제 브라우저 포인터 검증 및 공개 CI까지 확인한다.
- 허용 파일 / 제외 파일: WS-E app·합성 테스트·공개 설명·manifest·상태 기록 / 제조사 자료·private 작업 기록·인증정보·private Git 이력 제외
- branch / 시작 commit / 종료 checkpoint(확인된 경우): `codex/ws-e/ljh67340/design-workbench-migration` / `f19f2fefc05c78bb050e024b9e15651b0fd4bef4` / 미정
- 시작 시 기존 변경: 없음
- 읽은 문서 및 버전: `README.md`, `AGENTS.md`, `CURRENT_STATE.md`, `docs/development/WORK_PROTOCOL.md` @ `f19f2fe`
- 의존 작업 / frozen interface: 공개본 integration의 `BaselineCycleSolver` 및 schemas; 공통 schema·물리 가정·lockfile 변경 금지

## 수정 전 계획과 위험

- 대상 모듈 및 의존성: design workbench 계열 신규 모듈, Streamlit 결과 chart, WS-E 합성 회귀 테스트
- 예정 검증: focused/base/gui pytest, Ruff, format, mypy, manifest, build, work record, 실제 Chromium 포인터 조작
- 위험과 대응: private 이력·자료 유출을 방지하기 위해 commit cherry-pick/merge 없이 파일별 diff를 검토해 적용한다. 공개본 Ubuntu `network_map` 기존 실패는 별도 식별한다.

## 수행 내용

| 변경 파일 | 변경 내용 및 이유 |
|---|---|
| `src/agent_hvac/app/design_workbench.py` | 프로젝트 모델, 전체 지문, 연결·단위·지원 모델 검증과 baseline adapter 이관 |
| `src/agent_hvac/app/design_workbench_app.py` | 빈 캔버스, 직접 설계조건, baseline 실행, 상태표와 결과 무효화 UI 이관 |
| `src/agent_hvac/app/workbench_canvas_component.py` | 네 면 포트, 노드/포트 drag, 직교 연결선과 Delete 이벤트를 제공하는 자체 HTML/JS component 이관 |
| `src/agent_hvac/app/workbench_command.py` | 제한된 자연어 명령 parser와 단위 검증 이관 |
| `src/agent_hvac/app/streamlit_app.py` | 제공된 상태점 순서의 P-h/T-s 표시 보강 |
| `tests/ws_e/` | 합성 fixture만 사용하는 워크벤치·차트 회귀 테스트 추가 |
| `docs/workstreams/ws_e/`, `docs/validation/ws_e/` | 공개 실행 지침과 인증정보 없는 브라우저 화면 근거 추가 |
| `README.md`, `CURRENT_STATE.md`, source manifest | 공개 실행 방법, 현재 상태와 source hash 갱신 |

## 결정, 가정 및 출처

| 항목 | 결정 또는 가정 | 근거/출처 | 영향 및 후속 확인 |
|---|---|---|---|
| 이관 방식 | private Git 이력을 가져오지 않고 공개본 integration에 코드 diff만 적용 | `AGENTS.md`, `WORK_PROTOCOL.md` | 새 공개 Git 이력 유지 |
| WS-D | 공개본 P09 `synthetic_search.py`와 테스트의 SHA-256이 private source snapshot과 동일 | 파일별 hash 대조 | 이번 GUI PR에서 WS-D를 중복 변경하지 않음 |
| 결과 유효성 | 전체 프로젝트 JSON 지문이 현재 프로젝트와 같을 때만 결과 표시 | 공개 가능한 GUI 동작 계약 | 조건·연결·부품·속성 변경 시 stale 결과 제거 |
| 단위 | 압력은 `bar(a)`만 baseline 입력으로 허용하고 효율은 `dimensionless`만 허용 | 기존 `BaselineCycleSolver` 계약 | `bar(g)`/`barg` 추정 변환 및 효율 단위 오용 차단 |
| 최신 integration | 공개 PR 생성 후 전진한 `integration` `a200c7b`를 merge하고 양쪽 `CURRENT_STATE` 이력을 보존 | 공개 WORK_PROTOCOL | source manifest를 재생성하고 WS-E + network_map 집중 검증 재실행 |

- 단위 / 물리식 / 상관식 / 제품 데이터 영향: 물리식과 제품 데이터 변경 없음. 일반 baseline GUI 연결만 대상.
- public interface 영향 / ACR 링크: 별도 Streamlit GUI entrypoint 추가. 공통 schema 변경 없음.
- 코드·의존성·DB·지침 버전 및 재현 설정: 시작 SHA `f19f2fe`, Python 3.12.13, locked dependency, Chrome 153.0.0.0. lockfile·schema·제품 DB 변경 없음.

## 검증 결과

| 검증 대상 | 정확한 명령 또는 검사 방법 | 환경 | PASS/FAIL/NOT_RUN/BLOCKED | 결과 요약 및 증거 |
|---|---|---|---|---|
| 착수 상태 | `git status --short --branch` | Windows / PowerShell | PASS | clean branch에서 시작 |
| 집중 테스트 | `uv run --locked --extra gui pytest tests/ws_e/test_design_workbench.py tests/ws_e/test_streamlit_app.py -q` | Windows / Python 3.12 | PASS | 72 passed |
| WS-E 전체 | `uv run --locked --extra gui pytest tests/ws_e -q` | Windows / Python 3.12 | PASS | 121 passed |
| base 전체 | `uv run --locked pytest -q` | Windows / Python 3.12 | PASS | manifest 갱신 후 669 passed |
| GUI 전체 | `uv run --locked --extra gui pytest -q` | Windows / Python 3.12 | PASS | 669 passed |
| Ruff | `uv run --locked ruff check .` / `uv run --locked ruff format --check .` | Windows | PASS | check pass, 155 files formatted |
| mypy | `uv run --locked mypy` / `uv run --locked --extra gui mypy src/agent_hvac/app/streamlit_app.py` | Windows | PASS | 75 source files 및 GUI entrypoint 통과 |
| manifest | `uv run --locked python scripts/source_manifest.py --check` | Windows | PASS | 155 files verified |
| build | `uv build --no-build-isolation` | Windows | PASS | sdist와 wheel 생성 |
| 실제 브라우저 포인터 | Chromium CDP `Input.dispatchMouseEvent`와 실제 Streamlit DOM, 빈 캔버스부터 재현 | HeadlessChrome 153.0.0.0 / Windows | PASS | 부품 추가·노드 drag·포트 drag 4연결·조건 6개·수렴/상태표·세 종류 invalidation·미지원 배관 차단 확인 |
| 첫 공개 head CI | Actions run `36577131557` @ `54d0e01` | GitHub-hosted | PARTIAL | Windows base/gui PASS; Ubuntu base/gui는 기존 `network_map` 1건만 FAIL. integration 전진 후 최신 head 재실행 필요 |
| integration 반영 집중검사 | `uv run --locked --extra gui pytest tests/ws_e tests/ws_a_system/test_network_map.py -q` | Windows / Python 3.12 | PASS | 137 passed |

- 수치 검증 기준값·단위·출처·허용오차·실제 오차(해당 시): R744 합성 교차확인 입력 30/90 bar(a), 6.85/36.85 °C, 0.1 kg/s, 효율 0.8. 제품 성능 기준값이 아니며 GUI는 물리 합격 허용오차를 판정하지 않는다.
- 실패 재현 및 조치 / 미실행 이유: 최초 base 전체 검사는 새 source manifest 미갱신으로 1 failed, 668 passed였고 manifest를 작성·검토한 뒤 669 passed로 재검증했다. 공개본의 기존 Ubuntu `network_map` 실패는 로컬 Windows에서 재현되지 않았으며 관련 물리 코드·허용오차·테스트를 변경하지 않았다.
- diff 검토 결과: 제조사 파일·수치자료, private 작업 기록, 인증정보, private Git 이력, schema, lockfile, 제품 DB 및 WS-D/WS-C 코드는 포함하지 않았다. 테스트의 제품명 예시는 `Synthetic compressor`로 일반화했다.

## 종료 및 인수인계

- 완료한 범위: 공개 안전 코드 이관, local 전체 검사와 actual Chromium 포인터 검증, 공개 근거 작성.
- 남은 작업 / 알려진 한계 / blocker: branch push, 공개 PR과 원격 CI 확인. 물리 장치의 사람 손 마우스가 아니라 Chromium의 trusted pointer input으로 자동 재현했으며, 표준 버튼 제출은 실제 DOM click, 텍스트는 브라우저 keyboard input을 사용했다.
- 다음 담당자와 첫 실행 작업: LJH가 공개 branch를 push하고 integration PR의 Windows/Ubuntu × base/gui 결과를 확인한다.
- `CURRENT_STATE.md` 갱신 여부: 완료(아직 integration 미병합 상태로 기록).
- Phase checklist / Gate 상태와 증거: production·CV·P06·Gate 승인 범위 아님.
- PR / 리뷰 / 승인 / integration merge / CI 상태(없으면 미수행): local validated; PR·원격 CI·리뷰·병합 미수행.
