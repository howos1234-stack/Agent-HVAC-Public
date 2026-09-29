# 작업 기록: 합성 해석 재실행 상태 및 공개 통합 감사

## 식별 및 범위

- 시작 / 종료 시각 및 시간대: 2026-09-29 23:27 KST / 2026-09-29 23:46 KST (로컬 검증)
- 수행자 / human owner: Codex 통합·품질 담당 / 요청자 howos1234-stack
- Phase / Workstream: 기존 합성 해석 GUI 통합 품질 / WS-F 및 WS-E 경계; 신규 major phase 진행 없음
- 작업 상태: REVIEW_PENDING
- 사용자 요청과 목표: 최신 공개 integration 및 담당별 연결 현황 조사 후 작고 독립적인 개선 PR 제출. merge/Gate 승인 제외.
- 허용 파일 / 제외 파일: analysis_screen_app.py, test_analysis_screen.py, 공개 조사·기록, CURRENT_STATE, manifest. 물리·계약·의존성·제조사 자료·열린 PR #3 코드 제외.
- branch / 시작 commit / 종료 checkpoint(확인된 경우): codex/integration/analysis-run-state / 041121cf7036409d160f462aab87a163a05a8cc6 / 코드 checkpoint 73b9b780b9c6b9691173ae4aa04a8ff61019a71c (이후 문서만 갱신)
- 시작 시 기존 변경: 기존 비공개 checkout에 CURRENT_STATE 수정과 다수 untracked 기록이 있었고 보존했다. 기존 공개 checkout은 clean detached HEAD였으며 그대로 보존했다. 공개 origin의 integration을 별도 integration-quality 폴더에 clone; 작업 시작 clean.
- 읽은 문서 및 버전: 공개 기준 SHA의 AGENTS, README, CURRENT_STATE, WORK_PROTOCOL, SESSION_TEMPLATE, WS-A analysis screen/manager 안내, WS-A/WS-B 최신 작업 기록, DEPENDENCIES, CI, pyproject, lock 및 관련 코드·테스트·schema. 마스터 플랜 v0.3 및 공통 절차는 읽기 전용 참조; 내부 문서/이력 복사 없음. 공개 workstream README·공통 freeze 승인 문서 부재를 확인했고 공통 계약은 수정하지 않았다.
- 의존 작업 / frozen interface: CompactAnalysisInput, AnalysisReport와 기존 GUI 내부 bundle 사용. 공통 서비스·물리 계약 변경 없음. PR #3 코드 파일과 중복 없음; CURRENT_STATE/manifest 공유 파일은 향후 병합 시 조율 필요.

## 수정 전 계획과 위험

- 대상 모듈 및 의존성: 합성 GUI 실행 lifecycle 및 AppTest. run_metadata 준비 실패 또는 중단된 실행에서 이전 결과 재사용/KeyError 위험을 검사한다.
- 예정 검증: 수정 전 실패 재현 → 화면 회귀 → locked base/gui 전체 검사, GUI 진입점 mypy, manifest, build, 작업 기록, 실제 브라우저.
- 위험과 대응: 물리 결과를 GUI가 생성하지 않는다. 오류 유형/메시지, 현재 입력, 완료된 부분 기록을 보존한다. COMPLETE와 target_found를 구분한다. 중단 기록은 다음 rerun에서만 ERROR로 분류한다.

## 수행 내용

| 변경 파일 | 변경 내용 및 이유 |
|---|---|
| src/agent_hvac/app/analysis_screen_app.py | 준비 전에 새 RUNNING bundle 저장; 현재 입력 보존, 미생성 metadata는 null. 메타데이터 수집을 try 안으로 이동. report 직렬화 후 COMPLETE. 미완료/이전 버전 무상태 bundle은 다음 rerun에서 InterruptedRun ERROR로 표시. |
| tests/ws_e/test_analysis_screen.py | 완료 실행 후 metadata OSError 재실행, 상태 없는 legacy 부분 기록, RUNNING 부분 기록의 오류 표시·다운로드·부분 기록 보존 회귀 3건 추가. |
| docs/development/INTEGRATION_AUDIT_2026-09-29.md | 공개 SHA/PR 기준 담당별 현황, 사용자 흐름, 위험 우선순위와 후속 의존 작업을 새로 작성. |
| docs/validation/p00-source-manifest.json | 변경된 소스/테스트 2개 해시 재생성. |
| CURRENT_STATE.md 및 이 기록 | 현재 검증 근거 및 리뷰·통합 미완료 상태 기록. |

## 결정, 가정 및 출처

| 항목 | 결정 또는 가정 | 근거/출처 | 영향 및 후속 확인 |
|---|---|---|---|
| 실패 격리 | 새 실행은 이전 bundle을 준비 전에 대체 | 기존 main의 run_metadata가 try 밖에 위치; AppTest OSError 재현 | 실패 후 이전 완료 report를 표시하지 않음 |
| 중단 | 다음 rerun에서 None/RUNNING 상태를 ERROR로 표시 | 기존 status/report KeyError 두 사례 재현 | Streamlit 제어 예외를 삼키지 않으며 부분 기록 보존 |
| 데이터 경계 | 실패 준비 단계는 metadata null, 현재 검증 입력은 input 필드 | 실제 획득하지 못한 버전/hash는 생성하지 않음 | 내부 archive에 additive 필드; 공통 frozen schema 변경 없음 |
| 원격 근거 | 공개 #1/#2 병합, #3 미병합/변경요청 및 해당 head CI 성공을 구분 | GitHub API/gh read-only 조회 | 과거 CI를 기준 SHA/이번 head 결과로 재사용하지 않음 |

- 단위 / 물리식 / 상관식 / 제품 데이터 영향: 없음. 기존 수치/허용오차/출처를 변경하지 않음.
- public interface 영향 / ACR 링크: 없음. GUI 내부 실행 archive만 보완; frozen interface 변경/ACR 구현 없음.
- 코드·의존성·DB·지침 버전 및 재현 설정: 기준 SHA 위 참조, Python 3.12.14, uv 0.12.11, uv.lock 유지, CoolProp 8.0.0/Streamlit 1.63.0. DB 없는 합성 preset 유지.

## 검증 결과

모든 명령은 별도 공개 clone 루트에서 실행했다. 아래 `uv`는 `E:/Agent-HVAC/.tools/uv-package/bin/uv.exe`다. Base는 `$env:UV_PROJECT_ENVIRONMENT='.venv-base'`, GUI는 `$env:UV_PROJECT_ENVIRONMENT='.venv-gui'`로 분리했다.

| 검증 대상 | 정확한 명령 또는 검사 방법 | 환경 | PASS/FAIL/NOT_RUN/BLOCKED | 결과 요약 및 증거 |
|---|---|---|---|---|
| base 동기화 | `uv sync --locked` | Windows base | PASS | Python 3.12.14, 48 packages |
| GUI 동기화 | `uv sync --locked --extra gui` | Windows GUI | PASS | 75 packages |
| base 환경 분리 | `uv run --locked python -c "import importlib.util; assert importlib.util.find_spec('streamlit') is None; print('base: streamlit absent')"` | base | PASS | streamlit absent |
| 수정 전 재현 | `uv run --locked --extra gui pytest tests/ws_e/test_analysis_screen.py -q -k 'rerun_metadata or interrupted_run'` | GUI, 원래 production 코드 | FAIL | 의도한 3 failed: OSError, KeyError status, KeyError report |
| 수정 후 화면 회귀 | `uv run --locked --extra gui pytest tests/ws_e/test_analysis_screen.py -q` | GUI | PASS | 11 passed in 51.35s; 이후 현재 입력/부분 기록 보존 assertion 추가는 전체 GUI 회귀에서 재검증 |
| Ruff base | `uv run --locked ruff check .`; `uv run --locked ruff format --check .` | base | PASS | lint 성공, 151 files formatted |
| mypy base | `uv run --locked mypy` | base | PASS | 72 source files |
| Ruff GUI | `uv run --locked --extra gui ruff check .`; `uv run --locked --extra gui ruff format --check .` | GUI | PASS | lint 성공, 151 files formatted |
| mypy GUI | `uv run --locked --extra gui mypy`; `uv run --locked --extra gui mypy src/agent_hvac/app/streamlit_app.py src/agent_hvac/app/analysis_screen_app.py` | GUI | PASS | 72 source files 및 실제 진입점 2개 |
| manifest | `uv run --locked python scripts/source_manifest.py --write`; `uv run --locked python scripts/source_manifest.py --check`; `uv run --locked --extra gui python scripts/source_manifest.py --check` | base / GUI | PASS | 150 files; 변경 해시 2개만 확인 |
| build | `uv build --no-build-isolation` | base / GUI 각각 | PASS | sdist/wheel 생성; zipfile/tarfile 목록에서 GUI runtime 포함 및 venv/artifacts/Git 이력 제외 확인 |
| 전체 base | `uv run --locked pytest -q --junitxml=artifacts/base.xml` | base | PASS | 592 passed, 2 skipped (Streamlit 선택 의존성), 306.88s |
| 전체 GUI | `uv run --locked --extra gui pytest -q --junitxml=artifacts/gui.xml` | GUI | PASS | 620 passed, 349.96s; 추가된 모든 assertion 포함 |
| 실제 브라우저 | cua.createBrowserTab iab `http://127.0.0.1:8527` 2회 | Windows browser tool | BLOCKED | kernel exited: `windows sandbox failed: helper_unknown_error: setup refresh had errors`. AppTest/HTTP 응답과 구분 |
| 로컬 HTTP | `Invoke-WebRequest http://127.0.0.1:8527/_stcore/health` | hidden local Streamlit | PASS | `ok`; 실제 브라우저 시각 검증 아님 |
| diff | `git diff --check`; 소스/테스트/manifest diff 검토 | Git | PASS | 물리/허용오차/기존 테스트 삭제 없음 |
| 작업 기록 | `uv run --locked python scripts/check_work_record.py --base 041121cf7036409d160f462aab87a163a05a8cc6` | base | PASS | 코드 checkpoint 73b9b78에서 work record 및 CURRENT_STATE 검사 성공; 문서 갱신 commit 후 재확인 |
| 이번 PR 원격 CI | 제출 후 head별 Actions 확인 | GitHub | NOT_RUN | [PR #4](https://github.com/howos1234-stack/Agent-HVAC-Public/pull/4) 제출; 최신 head 완료 결과는 아직 확인하지 않음 |

- 수치 검증 기준값·단위·출처·허용오차·실제 오차(해당 시): 물리 변경 없음; 기존 물리 회귀 기준 유지. 중단 회귀는 session 부분 기록 주입으로 검증하며 실제 브라우저 Stop 버튼 검증은 BLOCKED.
- 실패 재현 및 조치 / 미실행 이유: 기본 exec 및 node 실행이 sandbox setup refresh 오류로 실패하여 승인된 escalated shell로 읽기/검증했다. 루트 private repo의 ownership 경고는 해당 조회에만 `git -c safe.directory=E:/Agent-HVAC` 사용; global Git 설정 변경 없음. 최초 HTTP 서버 시작은 artifacts 폴더 부재로 실패했으며 폴더 생성 후 시작/health 확인. private 변경 및 기존 공개 checkout 보존. 새 clone 작성자 미설정 확인 후 인증 계정의 공개 numeric ID/login에 따른 GitHub noreply 주소를 commit 명령에만 지정; global 설정 변경 없음.
- diff 검토 결과: 공개 코드 근거로 문서를 새로 작성. 비공개 자료·Git 이력·전체 PR 기록·제조사 수치·인증정보 추가 없음.

## 종료 및 인수인계

- 완료한 범위: 공개 현황 조사, 실패 3건 재현, 제한된 GUI lifecycle 수정 및 base/gui 전체 회귀·정적·build 검사.
- 남은 작업 / 알려진 한계 / blocker: PR #4 최신 head 원격 CI/리뷰; 승인 후 담당자가 통합 여부 결정. 실제 브라우저 도구 초기화 BLOCKED. 공통 Agent/제품 최적화/최종 보고서 연결은 후속 범위.
- 다음 담당자와 첫 실행 작업: 통합 담당은 이번 PR 최신 head CI/리뷰 확인; WS-E는 #3 리뷰 정리 및 두 GUI 흐름의 연결 검토; WS-C 공개 범위/계약 결정은 사용자 및 담당 세션이 수행.
- `CURRENT_STATE.md` 갱신 여부: 갱신; 공개 현황 감사와 이 기록 링크 포함.
- Phase checklist / Gate 상태와 증거: CV-1~CV-3, P06 전체, production/Gate 승인 변경 없음.
- PR / 리뷰 / 승인 / integration merge / CI 상태(없으면 미수행): [공개 PR #4](https://github.com/howos1234-stack/Agent-HVAC-Public/pull/4) 제출, base integration; 미리뷰/미승인/미병합. 원격 CI는 로컬 PASS와 별개이며 최신 head 완료 결과 미확인. 이번 요청에 merge 권한 없음.
