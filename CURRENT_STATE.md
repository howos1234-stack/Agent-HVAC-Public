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

## WS-A 공개 이관 작업 (2026-09-29, integration 반영 완료)

- 공개 `integration` `f19f2fe`에서 별도 브랜치 `codex/ws-a/public-pipe-closure`를 시작했다. 이전 비공개 작업 폴더와 Git 이력은 합치지 않았다.
- Ubuntu 최초 CI의 배관 실패 기대값은 작은 열전달에서 상대 에너지 잔차가 기존 `1e-12` 판정 경계의 양쪽으로 반올림되는 환경 의존적 사례로 분석됐다. 물리식·수치 한계는 유지하고, 통과 시 실제 잔차가 한계 이내인지 확인하며 결정론적 실패 전파 회귀를 추가했다. 공개 PR #1은 `a200c7b`로 integration에 병합됐다.
- 비공개 PR #71 head `b033f9e`에서 공개 가능한 합성 압축기·밸브 `is_mock` 전달 및 실패 후 결과 비재사용 테스트만 파일별 검토 후 이관했다. 제조사 자료·비공개 작업 기록은 제외했다.
- 검증·공개 PR·최신 Windows/Ubuntu × base/gui CI는 작업 기록에서 개별 확인한다. 병합 후 run 36577425396은 Success, 4/4 jobs다. CV-1~CV-3, P06 전체, production 및 Gate 승인은 이번 작업 범위가 아니다.

## WS-A 합성 컴포넌트 후보별 평가 연결 (2026-09-30, 검토 대기)

- 공개 `integration` `041121cf7036409d160f462aab87a163a05a8cc6`에서 분기했다. 별도 private 이력이나 제조사 자료는 반입하지 않았다.
- mock ProductRecord만 대상으로 압축기 map, 팽창밸브 map, HX rated point→P05 계산을 후보별로 독립 실행한다. 성공 결과에는 기존 상세 출처가 남고 실패 후보는 출력 없이 오류·선택 ID만 보존한다. 순위·목적함수·실제 제품 자동선정은 포함하지 않는다.
- 로컬 기존 가상환경에서 집중 4개, 기본 전체 596 passed/2 skipped, GUI 전체 621 passed. Ruff, mypy, manifest 151 files, build를 확인했다. `uv`가 이 호스트에서 없어 locked 환경 재생성은 BLOCKED이며 원격 CI는 아직 NOT_RUN이다.
- PR #2 관리자 승인 때 남긴 비차단 문구 정정 세 건을 이 작업에 포함했다. 세부 검증은 [작업 기록](docs/development_log/2026-09-29_2357_WS-A_synthetic-component-trials.md)을 따른다.
- 실제 제조사 검증·CV-1~CV-3·P06 전체·production·Gate 상태는 변경하지 않는다.
