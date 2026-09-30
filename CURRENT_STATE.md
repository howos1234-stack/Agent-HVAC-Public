# Public snapshot status

- Date: 2026-09-29 KST
- Source code snapshot: 0ea4828467d71cbc9ae8da71a548c43976ee6491
- Public initial code commit: b954c9de58e290439e8ff90211d7705e559e3ae1
- Repository preparation: complete; main and integration published with independent history.
- Validation: REVIEW_PENDING. Local GUI 614 passed; remote Windows base/gui PASS, Ubuntu base/gui FAIL.
- [Actual public CI](https://github.com/howos1234-stack/Agent-HVAC-Public/actions/runs/36565346488) ran without the private repository billing block.
- Ubuntu failure: tests/ws_a_system/test_network_map.py::test_small_heat_pipe_failure_is_retained_not_relaxed expects component-numerical-failure but receives evaluated. Base: 588 passed, 1 failed, 2 skipped; GUI: 613 passed, 1 failed. Root cause is not yet established. Do not loosen tolerance or hide the failure.
- No private Git history, research workbooks, manufacturer selection reports or internal PR records are included.
- Unmerged private work is excluded. No CV/P06/Gate or production approval is implied.
- Next: independently investigate the cross-platform failure in a separate PR; transfer only reviewed public-safe changes.
- Initial export record: [record](docs/development_log/2026-09-29_public-export.md).

## Pending public WS-E workbench PR

- Branch: `codex/ws-e/ljh67340/design-workbench-migration`; base `f19f2fefc05c78bb050e024b9e15651b0fd4bef4`.
- Scope: public-safe P12 schematic workbench, direct six-condition baseline execution, component inlet/outlet state display, project-fingerprint result invalidation and synthetic-only regressions.
- Existing public WS-D P09 implementation and tests match the reviewed private source snapshot; they are not duplicated in this GUI change. WS-C/Agent integration remains a separate PR.
- Local Windows validation after merging latest integration: WS-E 121 passed; base-command 672 passed in the existing GUI-capable `.venv`; GUI 672 passed; Ruff, format, mypy, both GUI entry-point mypy checks, 155-file manifest and package build passed. The local base command was not a clean base-only environment.
- Actual Chromium 153 pointer validation passed for blank-canvas component creation, node drag, port drag closed loop, direct inputs, convergence/state display, result invalidation and unsupported connected-component blocking. Evidence: [record](docs/development_log/2026-09-29_WS-E_ljh67340_public-workbench-migration.md).
- Public PR [#3](https://github.com/howos1234-stack/Agent-HVAC-Public/pull/3) is `REVIEW_PENDING`. [Remote CI run 36579413223](https://github.com/howos1234-stack/Agent-HVAC-Public/actions/runs/36579413223) passed Windows/Ubuntu × base/gui 4/4 at head `9d5bcbd`; the clean remote base jobs passed 634 tests with 14 skips, while GUI jobs passed 672 tests. Integration merge remains pending.
- This work does not imply manufacturer validation, production use, CV/P06 completion or Gate approval.

## WS-B public product-database audit

- Public PR: [#2](https://github.com/howos1234-stack/Agent-HVAC-Public/pull/2), branch `codex/ws-b/public-product-db-audit`; original audit basis `f19f2fefc05c78bb050e024b9e15651b0fd4bef4`, latest integration merge basis `a200c7bec109cb475c8283e7a1f9a2d9733fb743`.
- Public-ready scope confirmed: ProductRecord 0.2.0 typed models, generated Schema, Excel schema 0.2.0 loader, blank 15-sheet workbook template, synthetic WS-B fixtures and loader-to-WS-A compressor/valve/HX adapter tests.
- No additional private code migration is currently required: the relevant tracked public files match the private worktree snapshot. Private Git history was not merged, mirrored, pushed or cherry-picked.
- Public exclusion confirmed: no manufacturer PDF, selection-program export, research workbook, screenshot, performance table, private PR history or identified manufacturer/model value is tracked. The only tracked workbook is the empty public template.
- Original audit at `f19f2fe`: WS-B and Excel adapter focus 90 passed; full GUI environment 614 passed; generated ProductRecord Schema match, Ruff, format, mypy, 150-file manifest and sdist/wheel build passed. These results are not presented as latest-head verification.
- Locked base/gui environment recreation is BLOCKED locally because `uv` is not installed on this host. Public PR CI must provide the final separated base/gui result.
- The historical Ubuntu `network_map` failure was fixed by WS-A PR #1 and merged as `a200c7b`; the post-merge CI result remains separate from the original audit result.
- CV-1~CV-3, actual manufacturer validation, P06 completion, production approval and Gate status remain unchanged.
- PR #2 changes are documentation-only relative to latest integration. Checks 0 is `NOT_RUN` under the Markdown-only policy, not a billing failure.
- Audit record: [record](docs/development_log/2026-09-29_2216_WS-B_sangryul1208_public-product-db-audit.md).

## Pending public WS-D candidate-identity regression

- Branch `codex/ws-d/ljh67340/synthetic-search-audit` starts from public integration `041121cf7036409d160f462aab87a163a05a8cc6` and is independent of pending WS-E PR #3.
- P09 now rejects duplicate candidate `product_id` values before assignment/product-combination generation or solver invocation, preserving deterministic candidate identity without changing frozen schemas.
- Local Windows validation: WS-D 10 passed; base-command 618 passed in the existing environment; GUI 618 passed; Ruff, format, mypy, 150-file manifest and package build passed.
- This is mock synthetic input validation only. It does not add HVAC physics, manufacturer products, production selection or Gate approval.
- Evidence: [record](docs/development_log/2026-09-30_WS-D_ljh67340_synthetic-candidate-identity.md).

## WS-A 공개 이관 작업 (2026-09-29, 검토 대기)

- 공개 `integration` `f19f2fe`에서 별도 브랜치 `codex/ws-a/public-pipe-closure`를 시작했다. 이전 비공개 작업 폴더와 Git 이력은 합치지 않았다.
- Ubuntu 최초 CI의 배관 실패 기대값은 작은 열전달에서 상대 에너지 잔차가 기존 `1e-12` 판정 경계의 양쪽으로 반올림되는 환경 의존적 사례로 분석됐다. 물리식·수치 한계는 유지하고, 통과 시 실제 잔차가 한계 이내인지 확인하며 결정론적 실패 전파 회귀를 추가했다. 승인 전에는 해결 완료로 간주하지 않는다.
- 비공개 PR #71 head `b033f9e`에서 공개 가능한 합성 압축기·밸브 `is_mock` 전달 및 실패 후 결과 비재사용 테스트만 파일별 검토 후 이관했다. 제조사 자료·비공개 작업 기록은 제외했다.
- 검증·공개 PR·최신 Windows/Ubuntu × base/gui CI는 작업 기록에서 개별 확인한다. CV-1~CV-3, P06 전체, production 및 Gate 승인은 이번 작업 범위가 아니다.
