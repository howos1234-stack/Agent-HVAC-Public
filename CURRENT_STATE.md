# Public snapshot status

- Date: 2026-09-29 KST
- Source code snapshot: 0ea4828467d71cbc9ae8da71a548c43976ee6491
- Public initial code commit: b954c9de58e290439e8ff90211d7705e559e3ae1
- Repository preparation: complete; main and integration published with independent history.
- Initial snapshot validation: local GUI 614 passed; the first public CI had Windows base/gui PASS and Ubuntu base/gui FAIL.
- [Initial public CI](https://github.com/howos1234-stack/Agent-HVAC-Public/actions/runs/36565346488) ran without the private repository billing block.
- Historical Ubuntu failure: `tests/ws_a_system/test_network_map.py::test_small_heat_pipe_failure_is_retained_not_relaxed` expected `component-numerical-failure` but received `evaluated`. Base: 588 passed, 1 failed, 2 skipped; GUI: 613 passed, 1 failed. This historical failure was addressed by public PR #1 and merged as `a200c7bec109cb475c8283e7a1f9a2d9733fb743` without loosening the physical tolerance.
- No private Git history, research workbooks, manufacturer selection reports or internal PR records are included.
- Unmerged private work is excluded. No CV/P06/Gate or production approval is implied.
- PR #1 post-merge CI: [run 36577425396](https://github.com/howos1234-stack/Agent-HVAC-Public/actions/runs/36577425396), Success, Windows/Ubuntu × base/gui 4/4 jobs completed for `a200c7b`.
- Initial export record: [record](docs/development_log/2026-09-29_public-export.md).

## Integrated public WS-E workbench

- Branch: `codex/ws-e/ljh67340/design-workbench-migration`; base `f19f2fefc05c78bb050e024b9e15651b0fd4bef4`.
- Scope: public-safe P12 schematic workbench, direct six-condition baseline execution, component inlet/outlet state display, project-fingerprint result invalidation and synthetic-only regressions.
- Existing public WS-D P09 implementation and tests match the reviewed private source snapshot; they are not duplicated in this GUI change. WS-C/Agent integration remains a separate PR.
- Local Windows validation after merging latest integration: WS-E 121 passed; base-command 672 passed in the existing GUI-capable `.venv`; GUI 672 passed; Ruff, format, mypy, both GUI entry-point mypy checks, 155-file manifest and package build passed. The local base command was not a clean base-only environment.
- Actual Chromium 153 pointer validation passed for blank-canvas component creation, node drag, port drag closed loop, direct inputs, convergence/state display, result invalidation and unsupported connected-component blocking. Evidence: [record](docs/development_log/2026-09-29_WS-E_ljh67340_public-workbench-migration.md).
- Public PR [#3](https://github.com/howos1234-stack/Agent-HVAC-Public/pull/3) was approved and merged to integration as `49dcfbc522f798b1567e61aeabe198c7502bbf27`. Its latest-head Windows/Ubuntu × base/gui CI passed 4/4; post-merge CI is tracked separately.
- This work does not imply manufacturer validation, production use, CV/P06 completion or Gate approval.

## WS-B public product-database audit

- Public PR: [#2](https://github.com/howos1234-stack/Agent-HVAC-Public/pull/2), branch `codex/ws-b/public-product-db-audit`; original audit basis `f19f2fefc05c78bb050e024b9e15651b0fd4bef4`, latest integration merge basis `a200c7bec109cb475c8283e7a1f9a2d9733fb743`.
- Public-ready scope confirmed: ProductRecord 0.2.0 typed models, generated Schema, Excel schema 0.2.0 loader, blank 15-sheet workbook template, synthetic WS-B fixtures and loader-to-WS-A compressor/valve/HX adapter tests.
- No additional private code migration is currently required: the relevant tracked public files match the private worktree snapshot. Private Git history was not merged, mirrored, pushed or cherry-picked.
- Public exclusion confirmed: no manufacturer PDF, selection-program export, research workbook, screenshot, performance table, private PR history or identified manufacturer/model value is tracked. The only tracked workbook is the empty public template.
- Original audit at `f19f2fe`: WS-B and Excel adapter focus 90 passed; full GUI environment 614 passed; generated ProductRecord Schema match, Ruff, format, mypy, 150-file manifest and sdist/wheel build passed. These results are not presented as latest-head verification.
- Locked base/gui environment recreation was BLOCKED on the WS-B audit host because `uv` was unavailable. The code-level base/gui evidence is PR #1's verified post-merge run 36577425396; Markdown-only PR #2 itself did not trigger CI.
- The historical Ubuntu `network_map` failure was fixed by WS-A PR #1 and merged as `a200c7b`; the post-merge CI result remains separate from the original audit result.
- CV-1~CV-3, actual manufacturer validation, P06 completion, production approval and Gate status remain unchanged.
- PR #2 changes are documentation-only relative to latest integration. Checks 0 is `NOT_RUN` under the Markdown-only policy, not a billing failure.
- Audit record: [record](docs/development_log/2026-09-29_2216_WS-B_sangryul1208_public-product-db-audit.md).

## WS-D 공개 합성 후보 ID 검증 (integration 반영 완료)

- Public PR [#7](https://github.com/howos1234-stack/Agent-HVAC-Public/pull/7) started from integration `041121cf7036409d160f462aab87a163a05a8cc6`, reflected the WS-E merge `49dcfbc522f798b1567e61aeabe198c7502bbf27`, and was integrated as `d97edf1`.
- P09 now rejects duplicate candidate `product_id` values before assignment/product-combination generation or solver invocation, preserving deterministic candidate identity without changing frozen schemas.
- Local Windows validation: WS-D 10 passed; base-command 618 passed in the existing environment; GUI 618 passed; Ruff, format, mypy, 150-file manifest and package build passed.
- This is mock synthetic input validation only. It does not add HVAC physics, manufacturer products, production selection or Gate approval.
- Evidence: [record](docs/development_log/2026-09-30_WS-D_ljh67340_synthetic-candidate-identity.md).

## WS-A 공개 이관 작업 (2026-09-29, integration 반영 완료)

- 공개 `integration` `f19f2fe`에서 별도 브랜치 `codex/ws-a/public-pipe-closure`를 시작했다. 이전 비공개 작업 폴더와 Git 이력은 합치지 않았다.
- Ubuntu 최초 CI의 배관 실패 기대값은 작은 열전달에서 상대 에너지 잔차가 기존 `1e-12` 판정 경계의 양쪽으로 반올림되는 환경 의존적 사례로 분석됐다. 물리식·수치 한계는 유지하고, 통과 시 실제 잔차가 한계 이내인지 확인하며 결정론적 실패 전파 회귀를 추가했다. 공개 PR #1은 `a200c7b`로 integration에 병합됐다.
- 비공개 PR #71 head `b033f9e`에서 공개 가능한 합성 압축기·밸브 `is_mock` 전달 및 실패 후 결과 비재사용 테스트만 파일별 검토 후 이관했다. 제조사 자료·비공개 작업 기록은 제외했다.
- 검증·공개 PR·최신 Windows/Ubuntu × base/gui CI는 작업 기록에서 개별 확인한다. 병합 후 run 36577425396은 Success, 4/4 jobs다. CV-1~CV-3, P06 전체, production 및 Gate 승인은 이번 작업 범위가 아니다.

## WS-A 합성 컴포넌트 후보별 평가 연결 (2026-09-30, 검토 대기)

- 공개 `integration` `041121cf7036409d160f462aab87a163a05a8cc6`에서 분기했다. 별도 private 이력이나 제조사 자료는 반입하지 않았다.
- mock ProductRecord만 대상으로 압축기 map, 팽창밸브 map, HX rated point→P05 계산을 후보별로 독립 실행한다. 성공 결과에는 기존 상세 출처가 남고 실패 후보는 출력 없이 오류·선택 ID만 보존한다. 순위·목적함수·실제 제품 자동선정은 포함하지 않는다.
- 로컬 기존 가상환경에서 집중 4개, 기본 전체 596 passed/2 skipped, GUI 전체 621 passed. Ruff, mypy, manifest 151 files, build를 확인했다. `uv`가 이 호스트에서 없어 locked 환경 재생성은 BLOCKED다. 공개 [PR #6](https://github.com/howos1234-stack/Agent-HVAC-Public/pull/6)의 locked 원격 CI 결과는 별도 확인한다.
- PR #2 관리자 승인 때 남긴 비차단 문구 정정 세 건을 이 작업에 포함했다. 세부 검증은 [작업 기록](docs/development_log/2026-09-29_2357_WS-A_synthetic-component-trials.md)을 따른다.
- 실제 제조사 검증·CV-1~CV-3·P06 전체·production·Gate 상태는 변경하지 않는다.

## WS-B 공개 제품자료 경계 검사 (2026-09-29, integration 반영 완료)

- Branch: `codex/ws-b/public-data-boundary-guard`, start `041121cf7036409d160f462aab87a163a05a8cc6`.
- 공개 저장소의 Git 추적 파일을 기준으로 binary allowlist를 검사한다. 제품자료는 승인된 15-sheet Excel schema 0.2.0 template 한 개만 허용하고, WS-E 공개 GUI 검증 이미지 3개는 경로를 명시해 별도 허용한다.
- 빈 template은 승인 SHA-256 `6043d727...aeb2cd`, sheet 순서, 모든 첫 행 header와 2행 이후 공백을 모두 검증한다. 따라서 cell 밖 comment·embedded payload를 포함한 binary 변조도 거부한다. 제조사 PDF·추가 Excel·승인되지 않은 이미지·ZIP과 `data/components`의 실제 record는 CI에서 거부한다. pytest가 임시 생성하는 합성 workbook은 repository에 저장하지 않는다.
- ProductRecord, schema, loader, 단위 변환, WS-A adapter 및 실제 제품 데이터는 변경하지 않는다.
- 관리자 재현 3건(`docs/build` 우회, template 첫 행·비셀 payload 변조, 공개 GUI 이미지 오탐)을 보완했다. 집중 합성 회귀 10 passed, contracts·WS-B 회귀 116 passed, Ruff·mypy·manifest 152개·build PASS다. head `c1a29eb1faa7e17479217f0c2fc2a50bdb357d8b`의 [Foundation CI run 36667231659](https://github.com/howos1234-stack/Agent-HVAC-Public/actions/runs/36667231659)은 Windows/Ubuntu × base/gui 4/4 PASS였고 공개 PR #5는 `0d6f886`으로 integration에 병합됐다.
- 이 검사는 로컬 실행과 공개 push 뒤 CI에서 동작한다. GitHub에 최초 push되는 순간의 공개를 사전에 막지 못하므로, contributor는 push 전에 로컬 검사를 실행해야 하며 민감 자료가 이미 공개됐다면 별도 이력 정화·자격 증명 폐기 절차가 필요하다.
- 이 결과는 Git 추적 경로, 제한 확장자, 승인 template과 명시적 binary allowlist에 대한 제한적 검사다. 임의 이름·확장자의 텍스트에 포함된 민감 내용까지 없음을 보증하지 않는다. WS-A는 PR #5의 제품 소비 계약 무영향 범위를 최신 head에서 수용했다.
- CV-1~CV-3, 실제 제조사 검증, P06 전체, production 및 Gate 상태는 변경하지 않는다.
- Work record: [record](docs/development_log/2026-09-29_2334_WS-B_sangryul1208_public-data-boundary-guard.md).

## WS-B 공개 합성 제품 bundle 전달 검증 (2026-09-30, integration 반영 완료)

- Branch: `codex/ws-b/public-loader-adapter-audit`, start `0d6f886046a1b8730ee6bf992d8dbac7ccec1d44`.
- pytest 임시경로에서 compressor·expansion valve·gas cooler Excel schema 0.2.0 workbook을 각각 생성하고 모든 제품·source·record ID를 결정론적으로 분리한다.
- 세 workbook을 한 `ExcelComponentRepository`에서 동시에 적재한 뒤 `is_mock=true`, 제품 간 product/map/rated-point/point/value ID 비충돌, source ID와 원단위 보존, compressor/valve map adapter 및 HX rated-point adapter 전달을 확인한다.
- 공개 PR [#10](https://github.com/howos1234-stack/Agent-HVAC-Public/pull/10), 최초 head `30f87573434b1a81e4c2b01f75a15dea7c849776`, 최종 보완 head `3cc4db2bf09cd2b3b5625632e9a99ee5f7f97eb2`, integration 병합 `7277b75`. 새 bundle 및 기존 장비별 Excel 통합 집중 회귀 7 passed, contracts·WS-B·WS-A 관련 회귀 344 passed다. Ruff·mypy 75 source files와 GUI entry·manifest 158개·공개자료 경계·build는 PASS다. 최초 [CI run 36694757988](https://github.com/howos1234-stack/Agent-HVAC-Public/actions/runs/36694757988)과 보완 head의 [CI run 36704290398](https://github.com/howos1234-stack/Agent-HVAC-Public/actions/runs/36704290398)은 모두 Windows/Ubuntu × base/gui 4/4 PASS다. 로컬 전체 GUI AppTest 중단은 원격 전체 GUI PASS와 구분해 BLOCKED 이력으로 유지한다.
- 실제 제조사 자료·제품 수치·production DB를 사용하지 않으며 CV-1~CV-3, P06 전체, production 및 Gate 상태는 변경하지 않는다.
- Work record: [record](docs/development_log/2026-09-30_WS-B_sangryul1208_public-loader-adapter-bundle.md).

## WS-A PR #6 최신 integration 동기화 (2026-09-30, 진행 중)

- 최신 공개 integration `7277b75`를 반영하고 WS-D #7, WS-E #3, WS-B #5·#10과 WS-A #1·#6의 기록을 함께 보존한다.
- 충돌은 이 상태 문서에만 있었고, 합성 후보 평가의 물리식·계약·제품 DB는 변경하지 않는다. 검증과 새 head 원격 CI는 [작업 기록](docs/development_log/2026-09-30_2003_WS-A_public-pr6-integration-reconcile.md)에서 확인한다.
- 실제 제조사 검증·CV-1~CV-3·P06 전체·production·Gate 상태는 변경하지 않는다.
