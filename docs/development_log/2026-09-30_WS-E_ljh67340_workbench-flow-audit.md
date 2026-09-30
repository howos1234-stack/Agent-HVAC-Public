# WS-E workbench flow and export-boundary audit

## 작업 정보

- 담당: LJH / WS-E
- Phase / Workstream: P12-P13 / WS-E
- 작업 상태: REVIEW_PENDING
- 브랜치: `codex/ws-e/ljh67340/workbench-flow-audit`
- 시작 integration: `a42be4346c6868f57ae8d552b4ebe3d8374c6cae`
- 선행 완료: 공개 PR #12 integration 병합 및 post-merge CI run 36719833476 SUCCESS

## 범위와 경계

이번 작업은 기존 워크벤치의 입력 준비도, 계산 가능 여부, 마지막 계산 상태와 결과 내보내기 경계를 한 화면에서 일관되게 표시하는 GUI 품질 보강이다. 공통 schema, 물리 solver, 제품 DB, lockfile과 동결 계약은 변경하지 않는다. 실제 제조사 제품 선정, 목표 달성 판정, production, CV/P06 전체와 Gate 승인을 의미하지 않는다.

프로젝트의 조건, 연결, 부품, 속성, 편집 이력 또는 JSON 가져오기가 바뀌면 기존 계산 결과와 캐시된 Agent 완료 응답을 함께 무효화한다. 무효화 사유를 화면에 표시하며, 현재 프로젝트 지문과 일치하는 결과만 표시·내보낸다. 계산 실패 결과는 실패 상태와 원인을 유지하고 정상 성능 카드로 표시하지 않는다.

## 수행 내용

- 입력 준비도, 계산 가능 여부, 마지막 계산, 목표 달성 평가 여부, MOCK/일반 baseline 구분을 독립 상태로 표시한다.
- 직접 baseline과 Agent 명시 실행은 공통 결과 등록 경로를 사용한다.
- 프로젝트 변경은 이전 실행이 있을 때 무효화 사유를 남기고 결과·지문·Agent 캐시를 제거한다.
- 조건, 연결, 부품, 속성, Undo/Redo, JSON 업로드별 무효화와 명시적 재계산을 AppTest로 검증한다.
- 현재 프로젝트와 지문이 같은 실패 결과는 status/reason을 내보낼 수 있지만 COP 등 정상 성능 카드가 나타나지 않는지 검증한다.

## 결정, 가정 및 출처

| 항목 | 결정 또는 가정 | 근거/출처 | 영향 및 후속 확인 |
|---|---|---|---|
| 결과 유효성 | 전체 프로젝트 지문이 일치하는 결과만 표시·내보낸다. | 기존 PR #3·#12 계약과 관리자 지시 | 프로젝트 변경 뒤 명시적 재계산 필요 |
| 목표 상태 | 계산 완료와 목표 달성을 분리하고 목표는 평가하지 않음으로 표시한다. | 현재 baseline에 목표 평가 계약이 없음 | 향후 계약 승인 전 달성으로 표시하지 않음 |
| 제품 데이터 | 제품 DB 소비를 이번 변경에 추가하지 않는다. | WS-B 인계가 별도 진행 중 | 실제 제품 선택·검증을 의미하지 않음 |

## 실제 브라우저 확인

AppTest의 프로젝트 주입 검증과 아래 실제 포인터 조작은 별도 근거다. 확인 환경은 in-app Chromium, 로컬 Streamlit `http://127.0.0.1:8522`, 현재 작업 head다.

1. 기본 R744 프로젝트에서 누락된 질량유량·효율을 직접 입력하고 baseline을 실행했다. 6/6 준비, 실행 가능, `계산 완료 · 수렴`, `일반 baseline`, 컴포넌트 입·출구 상태표와 P-h/T-s 표시를 확인했다.
2. 계산 뒤 압축기→gas cooler 연결을 삭제했다. 결과와 결과 다운로드가 즉시 사라지고 `연결이 삭제되었습니다` 및 재계산 필요 안내가 표시되며 실행이 차단됐다. Undo로 연결을 복원해도 과거 결과는 복원되지 않았고 새 명시 실행 뒤에만 결과가 다시 표시됐다.
3. `R134a 기본 냉동사이클을 구성해줘`라는 불완전 자연어 입력은 여섯 필수 조건을 임의 생성하지 않고 추가 입력 필요로 표시했다. 프로젝트 적용 후 3/12 bar(a), 10/35 degC, 0.05 kg/s, 효율 0.75를 직접 입력해 수렴 결과와 상태점을 확인했다.
4. 새 빈 캔버스에서 실제 UI 버튼으로 압축기, gas cooler, 팽창밸브, 증발기를 추가하고 연결 편집기로 폐회로 연결을 순차 구성했다. 이는 코드로 프로젝트 JSON을 주입한 AppTest와 구분한다.

이전 PR #3의 Chromium 153 검증은 포트 드래그와 노드 이동을 포함한 역사적 근거이며, 이번 기록의 현재-head 확인과 혼동하지 않는다.

## 검증 결과

| 대상 | 명령/방법 | 결과 |
|---|---|---|
| WS-C·WS-E 집중 | `uv run --locked --extra gui pytest tests/ws_e/test_design_workbench.py tests/ws_c/test_workbench_agent.py -q` | PASS, 76 passed |
| 실제 브라우저 | 위 네 흐름을 in-app Chromium에서 조작 | PASS |
| base 전체 | `uv run --locked pytest -q` | PASS, 714 passed |
| GUI 전체 | `uv run --locked --extra gui pytest -q` | PASS, 714 passed |
| 품질·계약 | Ruff check/format, mypy, 두 GUI entry strict mypy, source manifest, build | PASS; 77 source files, 2 GUI entrypoints, 162-file manifest, sdist/wheel |

## 남은 제한

- 결과 JSON은 현재 `SimulationResult` 경계이며 HTML/PDF 보고서나 묶음 transaction을 새로 추가하지 않았다.
- 제품 DB 적재·reload 상태 소비와 실제 제품 자동선정은 WS-B 인계 이후 별도 계약 검토 대상이다.
- 자연어는 결정론적 adapter의 지원 문법만 처리하며 자유형 LLM/API는 연결하지 않았다.

## 종료 및 인수인계

- 완료한 범위: 상태 표시 일관성, 변경 사유가 있는 결과 무효화, 현재 프로젝트 결과만 표시·내보내기, 실패 결과 경계와 회귀, 실제 브라우저 흐름 확인.
- 다음 담당자와 첫 실행 작업: 관리자가 PR diff, AppTest와 실제 Chromium 근거, 최신 원격 CI를 검토한다.
- CURRENT_STATE 갱신: 완료.
- Gate 경계: GUI 품질 개선이며 CV/P06 전체, production, Gate 승인 아님.
