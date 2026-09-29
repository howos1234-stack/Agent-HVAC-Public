# 작업 기록: 공개 저장소 WS-B 제품 DB 이관 감사

## 식별 및 범위

- 시작 / 종료 시각 및 시간대: 2026-09-29 KST / 2026-09-29 KST
- 수행자 / human owner: WS-B `sangryul1208`
- Phase / Workstream: public repository migration / WS-B product database
- 작업 상태: REVIEW_PENDING
- 사용자 요청과 목표: 비공개 저장소의 Git 이력과 제조사 자료를 반입하지 않고 공개 저장소에서 ProductRecord, 생성 Schema, Excel loader, 빈 양식 및 합성 검증 경로를 계속 개발할 수 있는지 확인한다.
- 허용 파일 / 제외 파일: 공개 코드·생성 Schema·빈 Excel 양식·직접 만든 합성 fixture·검증 코드만 허용한다. 제조사 PDF·선정 프로그램 출력·조사 Excel·스크린샷·성능표·이용권 미확인 수치와 private Git/PR 이력은 제외한다.
- branch / 시작 commit / 종료 checkpoint(확인된 경우): `codex/ws-b/public-product-db-audit` / 감사 기준 `f19f2fefc05c78bb050e024b9e15651b0fd4bef4` / 공개 PR #2 최초 head `0b88deddd0827df4b8aea28af92dcc7396492f9a` / 최신 integration `a200c7bec109cb475c8283e7a1f9a2d9733fb743` 반영 중.
- 시작 시 기존 변경: 새 공개 clone은 clean이었다. 별도 비공개 작업 폴더의 untracked `.artifact_work/`는 변경하거나 이관하지 않았다.
- 읽은 문서 및 버전: `README.md`, `AGENTS.md`, `CURRENT_STATE.md`, `docs/development/WORK_PROTOCOL.md`, `docs/development_log/SESSION_TEMPLATE.md`, `docs/development_log/2026-09-29_public-export.md` at `f19f2fe`.
- 의존 작업 / frozen interface: ProductRecord 0.2.0, Excel schema 0.2.0, loader 0.2.x 및 기존 WS-A adapter 경계를 유지한다. 계약 변경은 수행하지 않았다.

## 수정 전 계획과 위험

- 대상 모듈 및 의존성: `src/agent_hvac/schemas`, `src/agent_hvac/database`, 생성 `ProductRecord.schema.json`, 공개 빈 workbook, WS-B 및 WS-A 합성 Excel 통합 테스트.
- 예정 검증: 공개/비공개 관련 파일 비교, workbook 내용 감사, 생성 Schema 일치, WS-B·adapter 집중 테스트, 전체 회귀, Ruff, mypy, manifest, sdist/wheel build 및 산출물 목록 감사.
- 위험과 대응: private Git 이력 또는 제조사 자료의 공개 반입을 막기 위해 branch 병합·cherry-pick 없이 파일 내용과 tracked 목록만 감사했다. 실제 제품 검증 상태는 변경하지 않았다.

## 수행 내용

| 변경 파일 | 변경 내용 및 이유 |
|---|---|
| `docs/development_log/2026-09-29_2216_WS-B_sangryul1208_public-product-db-audit.md` | 공개 이관 범위, 제외 범위 및 독립 검증 결과를 기록한다. |
| `CURRENT_STATE.md` | 공개 저장소에서 확인된 WS-B 제품 DB 준비 상태와 후속 경계를 추가한다. |

## 결정, 가정 및 출처

| 항목 | 결정 또는 가정 | 근거/출처 | 영향 및 후속 확인 |
|---|---|---|---|
| 코드 이관 | 별도 코드 이관은 현재 필요하지 않다. | 공개와 비공개 작업 폴더의 `src/agent_hvac/schemas`, `src/agent_hvac/database`, `tests/ws_b`, `docs/product_data/templates` tracked 내용이 동일했다. private 쪽 차이는 생성된 `__pycache__`뿐이었다. | private branch 전체 병합이나 일괄 cherry-pick을 하지 않는다. 이후 변경도 파일별 공개 가능성을 검토한다. |
| 빈 workbook | 공개 양식은 15개 계약 sheet, header와 49개 빈 입력 행만 포함한다. 데이터 행은 0개다. | openpyxl read-only/normal load로 모든 sheet의 nonblank data row를 검사했다. | 실제 제조사 자료 없이 loader 개발과 합성 테스트에 사용한다. |
| 공개 자료 경계 | tracked binary는 빈 `.xlsx` 1개뿐이며 제조사명·모델명 검색 결과가 없다. | `git ls-files` 확장자 감사 및 Dorin/Danfoss/Kelvion/AlfaBlue/CCMT/model 문자열 검색. | 제조사 원본과 조사 결과는 private 저장소에 유지한다. |
| 배포 산출물 | sdist에는 공개 문서·빈 workbook·합성 fixture가 포함되고 wheel에는 Python package만 포함된다. 제조사 원본은 없다. | `python -m build --no-isolation` 후 tar/zip member 목록 감사. | 향후 build에서도 동일 검사를 유지한다. |
| Ubuntu 실패 | 공개 초기 CI의 Ubuntu `network_map` 실패는 감사 기준 `f19f2fe`의 과거 결과다. WS-A 공개 PR #1이 물리 tolerance를 유지한 회귀 보강을 제출했고 `a200c7b`로 병합됐다. | 초기 run 36565346488, PR #1 merge `a200c7b`, post-merge run 36577425396. | 병합 후 run은 Success, Windows/Ubuntu × base/gui 4/4 jobs다. |

- 단위 / 물리식 / 상관식 / 제품 데이터 영향: 원단위→canonical SI, 차원 검증, source/value 참조, 격리 및 상태 처리의 기존 계약을 변경하지 않았다. 실제 제품 수치도 추가하지 않았다.
- public interface 영향 / ACR 링크: 없음. 새로운 ACR이 필요한 계약 변경 없음.
- 코드·의존성·DB·지침 버전 및 재현 설정: 공개 `integration` `f19f2fe`; 기존 검증 환경의 Python venv를 실행기에만 사용하고 import 및 working tree는 공개 clone으로 고정했다.

## 검증 결과

| 검증 대상 | 정확한 명령 또는 검사 방법 | 환경 | PASS/FAIL/NOT_RUN/BLOCKED | 결과 요약 및 증거 |
|---|---|---|---|---|
| WS-B + WS-A Excel adapter 집중 회귀 | `..\Agent-HVAC-repo\.venv\Scripts\python.exe -m pytest -q --tb=short -p no:cacheprovider --basetemp='.artifact_work\pytest-public-escalated' tests\ws_b tests\ws_a\test_excel_compressor_integration.py tests\ws_a\test_excel_valve_integration.py tests\ws_a\test_excel_hx_integration.py` | Windows, GUI 의존성 설치 환경, 감사 기준 `f19f2fe` | PASS | 90 passed. loader→ProductRecord→compressor/valve/HX 합성 소비 경로 포함. 최신 head 결과로 간주하지 않는다. |
| 전체 회귀 | `..\Agent-HVAC-repo\.venv\Scripts\python.exe -m pytest -q --tb=short -p no:cacheprovider --basetemp='.artifact_work\pytest-full'` | Windows, GUI 의존성 설치 환경, 감사 기준 `f19f2fe` | PASS | 614 passed. 최신 head 결과로 간주하지 않는다. |
| 생성 Schema 일치 | `test_deployed_schema_is_generated_from_product_record` | Windows | PASS | production 모델 생성 결과와 배포 `ProductRecord.schema.json` 동일. |
| 빈 Excel 양식 | openpyxl로 15개 sheet의 header와 nonblank data row 검사 | Windows | PASS | 15 sheets, 모든 sheet의 nonblank data row 0개. |
| 비공개 자료 혼입 | tracked 확장자 및 제조사·모델 문자열 검색 | Git worktree | PASS | tracked binary는 빈 template `.xlsx` 1개; 대상 제조사·모델 검색 결과 없음. |
| Ruff | `ruff check .`, `ruff format --check .` | Windows | PASS | lint 통과, 148 files formatted. |
| mypy | `mypy src`, `mypy src/agent_hvac/app/streamlit_app.py` | Windows | PASS | 72 source files 및 GUI entry 통과. |
| source manifest | `..\Agent-HVAC-repo\.venv\Scripts\python.exe scripts\source_manifest.py --write`, `..\Agent-HVAC-repo\.venv\Scripts\python.exe scripts\source_manifest.py --check` | Windows, 감사 기준 `f19f2fe` | PASS | 150 files 일치. 감사 문서 기록은 source inventory 대상이 아니어서 당시 manifest 내용은 변경되지 않았다. 최신 integration의 manifest 변경은 WS-A PR #1의 source/test 변경을 반영한 것이다. |
| build | `python -m build --no-isolation` | Windows | PASS | sdist와 wheel 생성 성공, member 목록 감사 완료. |
| locked base/gui 분리 실행 | `uv sync --locked ...` | Windows | BLOCKED | 이 호스트에서 `uv` 실행 파일을 찾지 못해 환경별 재생성은 미실행. 설치된 GUI 환경 전체 614개와 집중 90개는 통과했다. 원격 CI에서 base/gui를 다시 확인한다. |
| PR #2 원격 CI | 최초 head `0b88ded`, documentation-only diff | GitHub Actions | NOT_RUN | Checks 0. Markdown-only 정책에 따른 미실행이며 결제 차단이 아니다. |
| PR #1 병합 후 CI | merge `a200c7b`, [run 36577425396](https://github.com/howos1234-stack/Agent-HVAC-Public/actions/runs/36577425396) | GitHub Actions | PASS | Success, Windows/Ubuntu × base/gui 4/4 jobs completed, total duration 11m 34s. |

- 수치 검증 기준값·단위·출처·허용오차·실제 오차(해당 시): 실제 제조사 수치를 사용하지 않았으므로 해당 없음.
- 실패 재현 및 조치 / 미실행 이유: 최초 pytest/build는 Windows temp ACL로 실패하여 명시적 임시 경로와 승인된 실행으로 재실행했다. 코드 실패가 아니며 재실행은 통과했다.
- diff 검토 결과: 제품 DB production 코드 변경 없음. 공개 상태 문서·작업 기록·manifest만 변경한다.

## 종료 및 인수인계

- 완료한 범위: 공개 저장소 분리 clone, push 경로 확인, 관련 문서 검토, 공개/비공개 범위 분류, WS-B 코드·Schema·blank template·합성 adapter 경로·build 산출물 감사.
- 남은 작업 / 알려진 한계 / blocker: PR #2 최신 head의 Checks 상태 확인이 남았다. 실제 제조사 자료와 CV-1~CV-3는 공개 저장소에 반입하지 않는다.
- 다음 담당자와 첫 실행 작업: WS-B는 PR #2 정정 head를 제출한다. WS-A는 공개 합성 adapter 경계를 재검토한다.
- `CURRENT_STATE.md` 갱신 여부: 갱신.
- Phase checklist / Gate 상태와 증거: CV-1~CV-3, 실제 제조사 검증, P06 전체 및 Gate 상태 변경 없음.
- PR / 리뷰 / 승인 / integration merge / CI 상태(없으면 미수행): 공개 PR #2, 관리자 `CHANGES_REQUESTED`, REVIEW_PENDING, 미병합. 최초 head의 Checks 0은 Markdown-only 정책에 따른 NOT_RUN이다.
