# 작업 기록: 합성 컴포넌트 후보별 평가 결과 격리

## 식별 및 범위

- 시작 / 종료 시각 및 시간대: 2026-09-29 23:57 KST / 2026-09-30 00:15 KST
- 수행자 / human owner: WS-A `daeyunekim`
- Phase / Workstream: 공개 저장소 이관 후 WS-A 합성 컴포넌트 검증
- 작업 상태: REVIEW_PENDING
- 사용자 요청과 목표: 최신 공개 `integration`에서 압축기·팽창밸브·HX 합성 후보의 계산 결과와 실패·출처·mock 표시를 후보별로 분리한다.
- 허용 파일 / 제외 파일: WS-A 계산 연결 함수·합성 테스트·검증 문서·상태 기록만 변경한다. 제조사 원본, 조사 수치, private 이력, 공통 계약·물리식은 제외한다.
- branch / 시작 commit / 종료 checkpoint(확인된 경우): `codex/ws-a/synthetic-component-trials` / `041121cf7036409d160f462aab87a163a05a8cc6` / 최초 공개 PR #6 head `b6a0173afd39f2ace6f8b2baabfd34f75b6bd336`.
- 시작 시 기존 변경: 공개 `integration`을 `041121c`로 fast-forward한 뒤 clean 상태에서 분기했다.
- 읽은 문서 및 버전: 공개 README, AGENTS, CURRENT_STATE, WORK_PROTOCOL, SESSION_TEMPLATE 및 WS-A 장비별 계산 코드·합성 테스트.
- 의존 작업 / frozen interface: ProductRecord 0.2.0, loader 0.2.x, P05 및 장비별 map evaluator의 물리·단위·출처 계약은 유지한다.

## 수정 전 계획과 위험

- 대상 모듈 및 의존성: WS-A 내부 합성 후보 평가 연결층과 장비별 합성 fixture 테스트.
- 예정 검증: 후보 성공·실패 격리, mock·record ID·source ID 보존, 기존 장비별 회귀, locked base/gui 테스트, Ruff, mypy, manifest, build, 작업 기록 검사.
- 위험과 대응: 후보 순위·목적함수·실제 제품 자동선정으로 확장하지 않는다. 알려진 계산 예외만 후보 실패로 변환하고 프로그래밍 오류는 숨기지 않는다.

## 수행 내용

| 변경 파일 | 변경 내용 및 이유 |
|---|---|
| `src/agent_hvac/components/candidate_trials.py` | 세 장비군의 기존 evaluator를 후보별로 독립 호출하며 도메인 실패와 결과를 분리한다. |
| `tests/ws_a/test_{compressor_map,expansion_valve_map,heat_exchanger_rated_point}.py` | 각 장비의 성공→실패→성공과 mock·record·출처·실패 결과 격리를 검증한다. |
| `docs/workstreams/ws_a/SYNTHETIC_COMPONENT_TRIALS.md` | 합성 전용·무순위·실제 제품 비추천 경계를 명시한다. |
| `docs/validation/p00-source-manifest.json` | 새 소스와 합성 테스트를 inventory에 반영한다. |
| `CURRENT_STATE.md`, 이 작업 기록 | 공개 integration 반영, 검증 근거 및 미승인 경계를 기록한다. |
| `docs/development_log/2026-09-29_2216_WS-B_sangryul1208_public-product-db-audit.md` | PR #2 관리자 리뷰의 비차단 manifest 표현을 정정한다. |

## 결정, 가정 및 출처

| 항목 | 결정 또는 가정 | 근거/출처 | 영향 및 후속 확인 |
|---|---|---|---|
| 후보 평가 범위 | 합성 후보별 계산·실패 식별만 수행하며 순위는 생성하지 않는다. | 사용자 지시와 WS-A/관리자 역할 경계 | 정책·목적함수는 관리자 검토 대상 |
| 실패 정책 | 알려진 `HVACError`만 후보 `REJECTED`로 기록하고 결과는 `None`으로 둔다. 기타 프로그래밍 오류는 전파한다. | 기존 장비별 evaluator의 명시적 실패 계약 | 실패 후보가 이전 계산값을 재사용하지 않음 |
| 환경 제한 | `uv`가 현재 호스트에서 없어 기존 base/gui 가상환경으로 로컬 회귀를 수행했다. | 실행 환경 확인 | locked 재생성은 BLOCKED, 원격 CI 확인 필요 |

- 단위 / 물리식 / 상관식 / 제품 데이터 영향: 변경하지 않는다.
- public interface 영향 / ACR 링크: 공통 계약 변경 없음. WS-A 내부 계산 연결만 추가한다.
- 코드·의존성·DB·지침 버전 및 재현 설정: 공개 integration `041121c`, Python 3.12 기존 base/gui 가상환경, `PYTHONPATH`를 공개 저장소 `src`로 설정. 의존성 파일은 변경하지 않았다.

## 검증 결과

| 검증 대상 | 정확한 명령 또는 검사 방법 | 환경 | PASS/FAIL/NOT_RUN/BLOCKED | 결과 요약 및 증거 |
|---|---|---|---|---|
| 새 후보 격리 집중 | `python -m pytest -q --tb=short -p no:cacheprovider`와 새 테스트 4개 node ID | 기존 GUI 가상환경 | PASS | 4 passed |
| 전체 기본 | `python -m pytest -q --tb=short -p no:cacheprovider --basetemp='.artifact_work\pytest-component-trials-base'` | 기존 base 가상환경 | PASS | 596 passed, 2 skipped. 첫 시도는 상위 임시 폴더 누락과 manifest 갱신 전 상태로 실패했고, 둘을 해결한 뒤 재실행했다. |
| 전체 GUI | `python -m pytest -q --tb=short -p no:cacheprovider --basetemp='.artifact_work\pytest-component-trials-gui'` | 기존 GUI 가상환경 | PASS | 621 passed |
| Ruff | `ruff check .`, `ruff format --check .` | 기존 GUI 가상환경 | PASS | 전체 소스·테스트 검사 통과 |
| mypy | `mypy src`, `mypy src/agent_hvac/app/streamlit_app.py` | 기존 GUI 가상환경 | PASS | 73 source files 및 GUI entry 통과 |
| manifest | `python scripts/source_manifest.py --write`, `python scripts/source_manifest.py --check` | 기존 GUI 가상환경 | PASS | 151 files verified |
| sdist/wheel | `python -m build --no-isolation --outdir '.artifact_work\dist-component-trials'` | 기존 GUI 가상환경 | PASS | sdist 및 wheel 생성. 최종 문서 반영 후 재실행 예정 |
| locked base/gui 환경 재생성 | `uv sync --locked`, `uv sync --locked --extra gui` | 현재 호스트 | BLOCKED | `uv` 실행 파일을 찾지 못함. 기존 가상환경 결과를 locked 결과로 위장하지 않는다. |
| 공개 원격 CI | [PR #6](https://github.com/howos1234-stack/Agent-HVAC-Public/pull/6) 최신 head | GitHub Actions | NOT_RUN | 최초 head의 run 36589237467이 실행 중이며 완료 결과는 아직 확인하지 않았다. 실행 중은 PASS로 기록하지 않는다. |

- 수치 검증 기준값·단위·출처·허용오차·실제 오차(해당 시): 합성 fixture의 기존 기준을 사용한다.
- 실패 재현 및 조치 / 미실행 이유: 첫 기본 전체 실행은 임시 폴더 상위 경로 누락에 따른 97개 setup 오류와 변경된 source manifest의 미갱신으로 실패했다. 상위 폴더 생성 및 manifest 재생성 후 전체를 재실행해 통과했다. `uv` 부재는 남은 환경 제한이다.
- diff 검토 결과: 제조사 원본·실제 제품값·공통 schema·loader·물리 계산식·lockfile 변경 없음. 코드·합성 테스트·검증 문서와 PR #2의 비차단 문구만 변경.

## 종료 및 인수인계

- 완료한 범위: 공개 최신 integration 동기화, 합성 후보별 독립 평가 연결, 세 장비군 회귀 및 로컬 검증.
- 남은 작업 / 알려진 한계 / blocker: PR #6 최신 head의 locked 원격 CI 및 리뷰. 실제 후보 비교 정책은 관리자 범위.
- 다음 담당자와 첫 실행 작업: 관리자에게 합성 전용 경계와 실패 격리, CI를 검토 요청한다.
- `CURRENT_STATE.md` 갱신 여부: 갱신.
- Phase checklist / Gate 상태와 증거: CV-1~CV-3, P06 전체, production, Gate 미승인 유지.
- PR / 리뷰 / 승인 / integration merge / CI 상태(없으면 미수행): 공개 [PR #6](https://github.com/howos1234-stack/Agent-HVAC-Public/pull/6), REVIEW_PENDING, 미병합, 원격 CI run 36589237467 실행 중/결과 미확인.
