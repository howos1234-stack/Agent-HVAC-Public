# 공개 integration 연결 현황 — 2026-09-29

## 조사 기준과 실제 원격 상태

- 기준: `041121cf7036409d160f462aab87a163a05a8cc6` (`origin/integration`).
- 인증 계정 `howos1234-stack`의 공개 저장소 pull/push 권한을 GitHub API로 확인했다.
- 공개 협업자: `daeyunekim`, `sangryul1208`, `ljh67340`, `howos1234-stack`.
- PR #1: MERGED, head `23c423edba24ef54595de65b32860a0e21286fab`, merge `a200c7bec109cb475c8283e7a1f9a2d9733fb743`.
  병합 후 [CI 36577425396](https://github.com/howos1234-stack/Agent-HVAC-Public/actions/runs/36577425396)는 해당 merge의 4/4 성공 이력이다. 조사 기준 SHA의 새 실행으로 표시하지 않는다.
- PR #2: MERGED, head `7d5387d12b19964160fe6d3e9dd714a07952129e`, merge가 조사 기준 SHA다. Markdown-only Checks 0은 NOT_RUN이다.
- [PR #3](https://github.com/howos1234-stack/Agent-HVAC-Public/pull/3): OPEN / CHANGES_REQUESTED,
  head `9d5bcbd9b85a46a5c646c01419d1c0d9dc472845`, 작성자 `ljh67340`.
  [CI 36579413223](https://github.com/howos1234-stack/Agent-HVAC-Public/actions/runs/36579413223)는 이 head의 4/4 SUCCESS다. 리뷰 승인 또는 integration 반영을 뜻하지 않는다.
- 공개 브랜치/PR 목록에 WS-C 실행 구현 브랜치는 없다. 공개 `agents/tools.py`, `guidelines/rules.py`는 Protocol이며 `hitl`은 초기 패키지다.
- 기존 공용 작업 폴더는 수정하지 않고 공개 origin에서 별도 clone을 생성했다. 비공개 Git 이력·자료·작업 기록을 반입하지 않았다.

## A. 담당별 구현·반영·잔여 범위

| 담당 | integration에서 확인한 구현 | 진행 중 공개 작업 | 검증 근거 | 잔여 및 다음 의존 작업 |
|---|---|---|---|---|
| WS-A / daeyunekim | CoolProp, baseline cycle, TESPy 비교, compressor/valve map, 단상 배관, 1D HX, 합성 회로 수렴·해석 관리 | #1 병합; 이번 조회에서 추가 열린 WS-A PR 없음 | `tests/ws_a`, `tests/ws_a_system`, #1 CI | 실제 제조사 검증·전체 제품 조합/공통 Agent 연결은 별도; baseline과 synthetic 회로를 구분 |
| WS-B / sangryul1208 | ProductRecord 0.2.0, Excel loader, 빈 양식, typed map/HX adapter 소비 | #2 감사 문서 병합 | `tests/ws_b`, `tests/ws_a/test_excel_*_integration.py` | 실제 제조사 자료 권한·검증과 선택 workflow 연결; #2 자체는 새 DB 기능 구현이 아님 |
| WS-C / 공개 담당 미확정 | UserRequirements 및 SimulationTool/ConstraintEngine 계약 | 공개 PR/브랜치 없음 | `agents/tools.py`, `guidelines/rules.py`, `hitl/__init__.py` | 자연어 intake, 실행 제약 엔진, Agent/HITL 서비스의 공개 범위·계약 승인 확인 및 선별 이관 필요 |
| WS-D / ljh67340 | SyntheticGridOptimizer, 명시적 solver/constraint/objective stub, 실패·예산 처리 | 별도 열린 공개 최적화 PR 없음 | `tests/ws_d/test_synthetic_search.py`, `app/synthetic_flow.py` | 실제 WS-A/B/C 서비스와의 제품 후보 최적화 연결 필요 |
| WS-E / ljh67340 | 결과 JSON 뷰어, 별도 합성 해석 화면, JSON/HTML 보고서 생성기 | #3 워크벤치 head 위 참조, 미병합 | `tests/ws_e`, reporting modules | #3 GUI CI 진입점 검사·기록/단위 정합성 리뷰 해결; 합성 AnalysisReport에서 공통 FinalDesignPackage 보고서로의 정식 연결은 없음 |

위 테스트 경로는 존재·검토 근거이며 실행 결과는 이번 [세션 기록](../development_log/2026-09-29_integration-analysis-run-state.md)에 별도로 기록한다. 공개본에 없는 공통 workstream README·개인 지침·동결 승인 문서는 존재한다고 가정하지 않는다. 공통 계약을 수정하지 않는 범위에서 공개 WORK_PROTOCOL과 현재 코드를 기준으로 진행했다.

## B. 사용자 흐름 연결 상태

| 단계 | 실제 연결 | 경계/누락 |
|---|---|---|
| 요구조건 입력 | `analysis_screen_app.collect_input`의 구조화 입력 | 자연어 Agent intake 없음; 고정 raw_requirement 설명은 파서가 아님 |
| 설계조건 검증 | CompactAnalysisInput → expand_analysis; 범위/출처/예산 오류는 실행 차단 | authorization_ref는 인증·HITL 승인 증명이 아님 |
| 제품/합성 후보 선택 | 승인된 축의 합성 preset 후보 생성 | DB 없는 경로; Excel 제품선정과 자동 연결되지 않음 |
| 물리 계산 | run_analysis → design study → system cycle → CoolProp/부품 계산 | 결정론적 실제 계산이지만 입력/장비는 synthetic; 제조사 성능 검증과 다름 |
| 제약 검사 | 후보 수렴·냉방 적합·load balance의 내부 평가 | 공통 ConstraintEngine 구현 또는 전체 법규/제조사 제약 검증 아님 |
| 결과·출처·mock | result_rows, target_found, 입력 출처/패키지 해시, 합성 경고 | COMPLETE는 실행 완료; 목표 달성은 target_found. 재실행 준비 실패/중단 처리에 결함 발견 |
| 저장·보고서 | 합성 실행 bundle JSON 다운로드; 별도 FinalDesignPackage 및 mock OptimizationResult JSON/HTML 생성 | 두 보고서 생성기는 별도 입력 계약을 요구. 합성 AnalysisReport를 final package로 자동 변환하지 않음 |

결과 뷰어는 이미 제공된 계약 JSON을 표시한다. P09→P12/P13 경로는 DeterministicSolverStub·UpperBoundConstraintStub·QuadraticObjectiveStub 기반 MOCK 시나리오다. 세 경로가 각각 동작한다는 사실을 전체 자연어→상용제품→검증→보고서 흐름 완성으로 해석하지 않는다.

## C. 개선 우선순위와 이번 변경

1. **현재 결과의 신뢰성:** 재실행 시 run_metadata가 예외 처리 밖에서 실패하면 이전 완료 bundle이 session에 남는다. 종료 상태 없이 저장된 부분 bundle은 다음 rerun에서 KeyError를 일으킨다. AppTest 3건에서 수정 전 실패를 재현했다. 이번 PR은 새 RUNNING bundle 선저장, 준비 단계 예외 기록, 다음 rerun에서 중단을 ERROR로 표시하는 독립 수정이다.
2. **단위·출처·실패 보존:** 기존 입력변경 무효화, non-converged 빈 성능값, target_found 구분을 유지하고 현재 입력·완료된 부분 기록을 실패 archive에도 보존한다. 제조사 검증/공통 제약 상태는 추정하지 않는다.
3. **인터페이스 연결:** WS-C 공개 이관, WS-A/B/C를 소비하는 실제 최적화, AnalysisReport/최종 보고서 경계를 각 담당자가 공개 계약 검토 후 연결해야 한다. 이번에는 계약을 확장하지 않는다.
4. **재현성:** 이번 호스트의 uv 실행 경로를 확인했고 `.venv-base`와 `.venv-gui`를 분리했다. 과거 문서의 uv 부재는 과거 호스트 검증 사실로 보존한다. PR #3의 mypy 누락 리뷰는 해당 담당 작업으로 유지한다.
5. **GUI 사용성:** 별도 합성 화면과 결과 뷰어/워크벤치 통합 메뉴, 제품 선택·보고서 흐름은 후속 검토 대상이다. 기존 열린 PR의 구현을 대체하지 않는다.

이번 코드 수정은 열린 #3의 코드 파일과 겹치지 않는다. CURRENT_STATE와 source manifest는 공유 관리 파일이므로 후속 병합 시 양쪽 기록을 보존하고 manifest를 재생성해야 한다. 물리식, 수치 허용오차, 단위 계약, frozen interface, 의존성, CV-1~CV-3/P06/production/Gate 상태 변경 없음.

## 원본 대비 공개 반영 범위의 추가 확인

읽기 전용 Git blob 비교에서 공개 PR #3의 design_workbench.py, design_workbench_app.py, workbench_command.py, workbench_canvas_component.py는 이관 원본과 동일했다. 이 네 파일은 공개 PR에는 있지만 조사 기준 integration에는 없다. 공개 integration의 compressor_map.py, expansion_valve_map.py 및 두 map 테스트 파일은 확인한 이관 원본과 동일했다. 이 비교는 해당 여덟 파일에 한정하며 다른 파일/전체 PR의 동등성이나 승인 여부를 의미하지 않는다. 원본의 내부 작업 기록과 Git 이력은 공개 문서에 복제하지 않는다.
