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

## WS-B public product-database audit

- Branch: `codex/ws-b/public-product-db-audit`, based on public `integration` `f19f2fefc05c78bb050e024b9e15651b0fd4bef4`.
- Public-ready scope confirmed: ProductRecord 0.2.0 typed models, generated Schema, Excel schema 0.2.0 loader, blank 15-sheet workbook template, synthetic WS-B fixtures and loader-to-WS-A compressor/valve/HX adapter tests.
- No additional private code migration is currently required: the relevant tracked public files match the private worktree snapshot. Private Git history was not merged, mirrored, pushed or cherry-picked.
- Public exclusion confirmed: no manufacturer PDF, selection-program export, research workbook, screenshot, performance table, private PR history or identified manufacturer/model value is tracked. The only tracked workbook is the empty public template.
- Local verification: WS-B and Excel adapter focus 90 passed; full GUI environment 614 passed; generated ProductRecord Schema match, Ruff, format, mypy, 150-file pre-change manifest and sdist/wheel build passed.
- Locked base/gui environment recreation is BLOCKED locally because `uv` is not installed on this host. Public PR CI must provide the final separated base/gui result.
- Known Ubuntu `network_map` failure remains assigned to WS-A and was not relaxed or hidden.
- CV-1~CV-3, actual manufacturer validation, P06 completion, production approval and Gate status remain unchanged.
- Audit record: [record](docs/development_log/2026-09-29_2216_WS-B_sangryul1208_public-product-db-audit.md).
