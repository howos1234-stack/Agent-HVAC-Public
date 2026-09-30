# 작업 기록: 공개 제품자료 경계 자동검사

## 식별 및 범위

- 시작 / 종료 시각 및 시간대: 2026-09-29 KST / 2026-09-29 KST
- 수행자 / human owner: WS-B `sangryul1208`
- Phase / Workstream: public repository / WS-B product database
- 작업 상태: REVIEW_PENDING
- 사용자 요청과 목표: PR #2 병합 후 최신 공개 integration에서 후속 WS-B 작업을 수행한다. 공개 저장소에 제한된 제조사 자료나 실제 제품 DB가 실수로 반입되는 것을 CI에서 차단한다.
- 허용 파일 / 제외 파일: 공개 검사 코드·합성 테스트·CI·상태 기록만 허용한다. 제조사 원본, 실제 제품 수치, private Git/PR 이력은 제외한다.
- branch / 시작 commit / 종료 checkpoint(확인된 경우): `codex/ws-b/public-data-boundary-guard` / `041121cf7036409d160f462aab87a163a05a8cc6` / PR #5 보완 head에서 확정.
- 시작 시 기존 변경: 없음.
- 읽은 문서 및 버전: `README.md`, `AGENTS.md`, `CURRENT_STATE.md`, `docs/development/WORK_PROTOCOL.md`, PR #2 감사 기록, `pyproject.toml`, `.github/workflows/ci.yml` at `041121c`.
- 의존 작업 / frozen interface: ProductRecord 0.2.0, Excel schema 0.2.0, loader 0.2.x와 WS-A adapter 계약을 변경하지 않는다.

## 수정 전 계획과 위험

- 대상 모듈 및 의존성: 공개 artifact 검사 script, contract test, Foundation CI.
- 예정 검증: 현재 저장소 통과, 제한 확장자·추가 workbook·채워진 template·component data 거부, Ruff, mypy, manifest, build 및 원격 matrix CI.
- 위험과 대응: 파일명이나 제조사명을 기준으로 허용하지 않고 Git 추적 파일의 구조적 경계를 검사한다. 추적된 `build`·artifact 경로도 검사하며, Git 비추적 로컬 산출물은 검사 범위 밖이다.

## 수행 내용

| 변경 파일 | 변경 내용 및 이유 |
|---|---|
| `scripts/check_public_data_boundary.py` | 공개 저장소에서 허용되지 않은 binary 자료와 component data를 차단하고 빈 15-sheet 양식을 검증한다. |
| `tests/contracts/test_public_data_boundary.py` | 정상 저장소와 제한 artifact, 추가 workbook, 채워진 template, component data, sheet 계약 오류를 합성 fixture로 검증한다. |
| `.github/workflows/ci.yml` | base/gui matrix마다 공개자료 경계 검사를 실행한다. |
| `CURRENT_STATE.md` | WS-B 후속 작업 범위와 상태를 기록한다. |
| `docs/validation/p00-source-manifest.json` | 새 script와 test 및 CI 변경의 source hash를 반영한다. |

## 결정, 가정 및 출처

| 항목 | 결정 또는 가정 | 근거/출처 | 영향 및 후속 확인 |
|---|---|---|---|
| 허용 workbook | `docs/product_data/templates/Agent-HVAC_ProductData_0.2.0_template.xlsx` 한 개만 허용한다. | PR #2 공개자료 감사와 관리자 승인 범위. | 합성 workbook은 pytest 임시경로에서 생성하며 repository에 commit하지 않는다. |
| template 조건 | 승인 SHA-256 `6043d7278a39a4ad5e482ddeb6df54f86fa0ac12e48bd3f5d654fa57d7aeb2cd`, 15개 sheet 순서, 모든 첫 행 header와 2행 이후 cell의 공백을 요구한다. | Excel schema 0.2.0 공개 빈 양식 계약과 PR #5 관리자 재현. | 첫 행, comment, embedded object를 포함한 binary 변조가 실패한다. 양식을 의도적으로 바꿀 때에는 공개 리뷰 후 hash와 구조 계약을 함께 갱신한다. |
| component data | `data/components`에는 `.gitkeep`만 허용한다. | 실제 제조사 데이터는 private 저장소에 유지한다는 공개 경계. | JSON이라도 실제 제품 DB로 오해될 파일은 공개 data 경로에서 차단된다. |
| 제한 artifact | Git 추적 파일 전체에서 PDF, Excel 변형, 이미지, ZIP을 검사한다. 빈 template과 WS-E 공개 GUI 검증 이미지 3개만 경로 기반으로 허용한다. | 제조사 원본·조사 workbook·스크린샷을 공개하지 않는 승인 정책과 PR #3 공개 증빙. | `docs/build` 등 디렉터리명으로 우회할 수 없다. 새 공개 binary는 코드 리뷰로 allowlist 변경 근거가 필요하다. |
| 공개 시점 한계 | CI는 공개 push 뒤 실행되며 최초 공개 자체를 사전에 차단하지 못한다. | PR #5 관리자 수정 요청. | push 전 로컬 검사 필수. 이미 공개된 민감 자료는 이 검사만으로 회수할 수 없고 별도 이력 정화가 필요하다. |
| 검사 보증 범위 | Git 추적 경로, 제한 확장자, 승인 template hash와 명시적 binary allowlist만 구조적으로 검사한다. | PR #5 WS-A 재검토. | 임의 이름·확장자의 텍스트 파일 내부에 민감 내용이 없음을 보증하지 않으며 human review를 대체하지 않는다. |

- 단위 / 물리식 / 상관식 / 제품 데이터 영향: 없음. 제품 수치, SI 변환, validator 및 loader 동작을 변경하지 않는다.
- public interface 영향 / ACR 링크: 없음. 개발·CI 검사만 추가한다.
- 코드·의존성·DB·지침 버전 및 재현 설정: 새 의존성 없음. 기존 `openpyxl`을 read-only 검증 용도로 사용한다.

## 검증 결과

| 검증 대상 | 정확한 명령 또는 검사 방법 | 환경 | PASS/FAIL/NOT_RUN/BLOCKED | 결과 요약 및 증거 |
|---|---|---|---|---|
| 공개 저장소 경계 | `python scripts/check_public_data_boundary.py` | Windows | PASS | 빈 template 1개, 제한 artifact와 component data 없음. |
| 집중 회귀 | `python -m pytest -q -p no:cacheprovider --basetemp=.artifact_work/pytest-boundary-final tests/contracts/test_public_data_boundary.py` | Windows | PASS | 10 passed. Git 추적 `docs/build` PDF 거부, 첫 행·comment 변조 거부, GUI 증빙 allowlist 포함. |
| Ruff | `ruff check ...`, `ruff format --check ...` | Windows | PASS | 새 script/test 통과. |
| mypy | `mypy scripts/check_public_data_boundary.py` | Windows | PASS | 1 source file 통과. |
| WS-B·contract 회귀 | `python -m pytest -q --tb=short -p no:cacheprovider --basetemp=.artifact_work/pytest-wsb-boundary-final2 tests/contracts tests/ws_b` | Windows | PASS | 116 passed. 최초 보완 실행의 manifest 차이는 `source_manifest.py --write` 후 해소했고 최종 재실행에서 모두 통과했다. |
| 전체 Ruff | `ruff check .`, `ruff format --check .` | Windows | PASS | 153 files formatted. |
| 전체 mypy | `mypy`, `mypy src\\agent_hvac\\app\\streamlit_app.py` | Windows | PASS | 72 source files와 GUI entry 통과. |
| source manifest | `python scripts\\source_manifest.py --write`, `--check` | Windows | PASS | 152 source files. |
| build | `python -m build --no-isolation` | Windows | PASS | sdist와 wheel 생성. |
| 최초 원격 CI | PR #5 최초 head `d7dc54c854eb890e9926ffa69a56fbce80748872` | GitHub Actions | PASS | 관리자 확인 기준 Windows/Ubuntu × base/gui 4개 통과. 보완 head CI와 구분한다. |
| 보완 원격 CI | PR #5 head `c1a29eb1faa7e17479217f0c2fc2a50bdb357d8b`, [run 36667231659](https://github.com/howos1234-stack/Agent-HVAC-Public/actions/runs/36667231659) | GitHub Actions | PASS | Windows/Ubuntu × base/gui 4/4 PASS. 각 job에서 공개자료 경계 검사 통과. |
| WS-A 독립 검증 | 공개자료 경계, WS-A product adapter 및 performance-map 집중 실행 | WS-A | PASS | 34 passed. ProductRecord·Schema·loader·SI 변환·map/envelope evaluator·장비 adapter 무변경과 소비 계약 무영향을 확인하고 수용했다. |

- 수치 검증 기준값·단위·출처·허용오차·실제 오차(해당 시): 제품 수치를 사용하지 않아 해당 없음.
- 실패 재현 및 조치 / 미실행 이유: 첫 집중 실행에서 test directory 생성의 `exist_ok` 누락과 `.artifact_work` 미제외를 확인해 수정했다. 남은 권한 제한 pytest 임시 폴더 때문에 첫 전체 Ruff format 검사가 중단됐으며 해당 임시 폴더만 제거한 뒤 153개 파일 검사가 통과했다.
- diff 검토 결과: 제조사 자료·제품 DB·계약·loader production 코드는 변경하지 않는다.

## 종료 및 인수인계

- 완료한 범위: 경계 검사, 합성 회귀, CI 연결, 작업 기록 및 로컬 품질·build 검증.
- 남은 작업 / 알려진 한계 / blocker: 관리자 최종 검토와 integration 병합 판단. 공개 push 뒤 CI이므로 최초 공개 전 차단은 별도 로컬 실행과 contributor 절차에 의존하며, 임의 이름의 텍스트 내용은 자동 보증하지 않는다.
- 다음 담당자와 첫 실행 작업: WS-A는 제품 소비 계약 변경이 없음을 확인하고 관리자는 공개자료 경계 정책을 검토한다.
- `CURRENT_STATE.md` 갱신 여부: 갱신.
- Phase checklist / Gate 상태와 증거: CV-1~CV-3, P06 전체, production 및 Gate 상태 변경 없음.
- PR / 리뷰 / 승인 / integration merge / CI 상태(없으면 미수행): 공개 PR #5, WS-A 소비 계약 범위 수용, 관리자 최종 판단 대기, 미병합. 최초·보완 head CI 모두 4/4 PASS.
