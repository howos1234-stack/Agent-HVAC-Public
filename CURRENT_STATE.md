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
