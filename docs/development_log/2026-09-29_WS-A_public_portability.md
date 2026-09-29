# WS-A 공개 저장소 이관과 배관 수치 검증

## 식별 및 범위

- 시작: 2026-09-29 KST; 수행자: daeyunekim / WS-A
- Phase / Workstream: 공개 저장소 이관 / WS-A
- 작업 상태: REVIEW_PENDING
- 목표: 공개 저장소 최초 Ubuntu CI의 배관 closure 테스트 차이를 분석하고, 비공개 PR #71의 공개 가능한 합성 계산 변경만 파일별로 이관한다.
- 브랜치: `codex/ws-a/public-pipe-closure`; 시작 integration: `f19f2fefc05c78bb050e024b9e15651b0fd4bef4`.
- 시작 시 공개 작업 폴더 미커밋 변경 없음. 기존 비공개 작업 폴더는 분리 보존.
- 기준 문서: README.md, AGENTS.md, CURRENT_STATE.md, docs/development/WORK_PROTOCOL.md.

## 수정 전 계획과 위험

- Ubuntu base/gui에서 같은 테스트가 `evaluated`, Windows에서는 `suction_pipe` closure 실패를 반환한다. 두 플랫폼 결과를 물리 정책 변경의 근거로 삼지 않고 잔차 및 실패 판정 코드를 대조한다.
- `1e-12` 배관 보존 잔차 한계, 물리식, 공통 계약은 변경하지 않는다. 오차가 한계에 인접한 실제 CoolProp 입력은 결과별 안전 불변식을 확인하고, 별도 결정론적 테스트로 실패 보존을 확인한다.
- 비공개 PR #71의 파일별 차이를 검토해 공개 가능한 mock 표시·합성 회귀만 옮긴다. Git 이력 병합·cherry-pick은 하지 않는다.
- 제조사 원본, 이용권 미확인 수치, 비밀정보, 비공개 작업 기록은 제외한다.

## 진단 근거

- 공개 최초 CI run `36565346488`: Windows base/gui 성공, Ubuntu base/gui는 해당 테스트 1건만 실패. Ubuntu Python 3.12.3, CoolProp 8.0.0.
- Windows에서 원래 판정은 `suction_pipe` 상대 에너지 잔차 `2.211585374248226e-12`로 `1e-12` 한계 초과다. 진단 목적의 프로세스 내부 한계 교체로 얻은 각 pipe 잔차는 discharge `1.2260774912136635e-14`, high-side `5.926568654912798e-13`, suction `2.211585374248226e-12`다. 소스 한계는 수정하지 않았다.
- 엔탈피 약 450000 J/kg에서 binary64 ULP는 `5.820766091346741e-11 J/kg`이다. 작은 열전달 결과의 closure 잔차가 속성 라이브러리/플랫폼의 반올림에 민감한 입력이다. 의도적으로 편향된 상태를 주입한 기존 `test_energy_closure_above_existing_limit_is_rejected`는 진짜 한계 초과를 별도로 검증한다.

## 수행 내용

| 변경 파일 | 변경 내용 및 이유 |
|---|---|
| `tests/ws_a_system/test_network_map.py` | 작은 열량의 실제 CoolProp 결과를 잔차 기준으로 검증하고, 결정론적 closure 예외가 동일 배관 단계에서 누락되지 않음을 별도 검증한다. |
| `src/agent_hvac/components/{compressor,expansion_valve}_map.py` | 공개 가능한 합성 평가 결과의 `is_mock` 상태를 원본 ProductRecord에서 보존한다. |
| `tests/ws_a/test_{compressor,expansion_valve}_map.py` | mock 전파 및 실패한 후보가 이전 성공 결과·출처를 재사용하지 않는 회귀를 이관한다. |
| `CURRENT_STATE.md`, 이 작업 기록, source manifest | 공개 저장소의 새 작업 근거와 변경 파일을 기록한다. |

## 결정, 가정 및 출처

| 항목 | 결정 또는 가정 | 근거/출처 | 영향 및 후속 확인 |
|---|---|---|---|
| 배관 보존 한계 | 기존 `1e-12`와 물리식 유지 | `pipe.py`, 공개 CI run 36565346488, Windows 수치 진단 | Ubuntu 통과를 위해 tolerance를 완화하지 않음; 새 head의 CI 필요 |
| private 변경 이관 | 합성 코드·테스트 4개 파일의 관련 hunk만 수작업 적용 | 비공개 PR #71 실제 head `b033f9ece7f157373c9f34dd133b72751c5f53b3`와 공개 integration의 파일별 diff | 비공개 이력·작업 기록·제조사 파일·이용권 미확인 자료 미이관 |
| 상태 | 새로운 승인 아님 | 공개 저장소 AGENTS.md와 WORK_PROTOCOL.md | CV-1~CV-3/P06/Gate 유지 |

- 단위·물리식·상관식·공통 계약·DB 변경 없음. 공개 계산 결과에 기존 `is_mock` 정보를 추가 보존한다.
- 비공개 PR #71의 파일별 이관: `src/agent_hvac/components/compressor_map.py`, `src/agent_hvac/components/expansion_valve_map.py`, `tests/ws_a/test_compressor_map.py`, `tests/ws_a/test_expansion_valve_map.py`의 합성 코드·회귀 hunk만 새 공개 커밋으로 재작성했다.
- 비공개 PR #71에서 제외: `CURRENT_STATE.md`, `docs/development_log/2026-09-29_1750_WS-A_daeyunekim_synthetic-component-evidence.md`, `docs/validation/p00-source-manifest.json`은 공개 저장소의 상태·기록·해시로 새로 생성했다. `docs/workstreams/ws_a/SYNTHETIC_COMPONENT_EVIDENCE_HANDOFF.md`는 비공개 저장소의 작업 이력·상태 인계를 포함하므로 그대로 복사하지 않았다. 제조사 원본·선정 출력·이용권 미확인 수치·개인정보·비밀키는 애초에 이관 대상에 포함하지 않았다.

## 검증 결과

| 검증 대상 | 정확한 명령 또는 검사 방법 | 환경 | 상태 | 결과 |
|---|---|---|---|---|
| 집중 | `python -m pytest tests/ws_a/test_compressor_map.py tests/ws_a/test_expansion_valve_map.py tests/ws_a_system/test_network_map.py -q` | Windows, 기존 base venv, 공개 `src` PYTHONPATH | PASS | 62 passed |
| 전체 base | `python -m pytest -q --junitxml=artifacts/pytest.xml` | Windows, 기존 base venv, 공개 `src` PYTHONPATH | PASS | 592 passed, 2 skipped (GUI optional dependency) |
| 전체 GUI | `python -m pytest -q --junitxml=artifacts/pytest-gui.xml` | Windows, 기존 GUI venv, 공개 `src` PYTHONPATH | PASS | 617 passed |
| Ruff | `ruff check .`, `ruff format --check .` | 기존 base venv | PASS | 검사 통과 |
| mypy | `mypy` | 기존 base venv | PASS | 72 source files |
| GUI 진입점 mypy | `mypy src/agent_hvac/app/streamlit_app.py` | 기존 GUI venv | PASS | 1 source file |
| manifest | `python scripts/source_manifest.py --write`, `--check` | 기존 base venv | PASS | 150 files |
| build | `python -m build --no-isolation` | 기존 base venv | PASS | sdist 및 wheel 생성 |
| 원격 locked base/gui | 공개 PR의 Windows/Ubuntu × base/gui | GitHub Actions | NOT_RUN | 제출 후 결과 확인 |

- 로컬 `uv` 실행 파일은 현재 셸 PATH에서 찾지 못해 기존 venv로 사전 검증했다. 원격 CI는 workflow의 `uv sync --locked` 및 `uv run --locked`로 별도 확인한다.

## 종료 및 인수인계

- 완료 범위: 공개 Ubuntu 이슈 원인 분석과 물리 기준을 유지한 회귀 보강, PR #71의 공개 안전 합성 변경 선별 이관.
- 잔여: 공개 PR의 locked CI 결과를 확인하고 관리자의 재검토를 받는다.
- 비공개 PR #71은 공개 PR의 동등성·수용이 확인되기 전 닫거나 삭제하지 않는다.
- `CURRENT_STATE.md`: 갱신. CV-1~CV-3, P06 전체, production 및 Gate 승인은 부여하지 않는다.
