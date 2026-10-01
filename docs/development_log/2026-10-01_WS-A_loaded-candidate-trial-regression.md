# WS-A loaded synthetic candidate regression

## Scope and plan

- Human owner: daeyunekim; WS-A; 2026-10-01 KST.
- Status: REVIEW_PENDING.
- Base: public integration `0c735d0`; branch `codex/ws-a/loaded-candidate-trial-regression`.
- Initial tracked changes: none. Read AGENTS, README, CURRENT_STATE, WORK_PROTOCOL, trial and Excel integration source/tests.
- Test mixed compressor/valve/HX evaluation, reversed order, and freshly loaded records after workbook quarantine and restoration.
- Only synthetic tests, state, work record and generated manifest may change. No physical equations, tolerance, schema, loader, ranking or manufacturer data changes.
- Existing ProductRecord/adapter interfaces remain frozen. Expected failures must retain no calculation result.

## Validation and handoff

- Added `tests/ws_a/test_loaded_candidate_trials.py` (3 cases), state entry and generated source manifest. Production implementation unchanged. Helpers follow the existing in-repository test import convention.
- Mixed/reversed execution preserves complete result equality and mock/parent source identity. Missing map after reload has no result, retains only surviving selected envelope source, and independent valve/HX results are unchanged. Restoring original bytes restores version and outputs. No guarantee of invalidating caller-held old immutable ProductRecord snapshots is asserted.
- Local runtime: `D:/codex/HVAC agent/Agent-HVAC/.venv/Scripts/python.exe`, public `src` and repository first on PYTHONPATH. No private files/data/history imported. This environment is not freshly locked; remote CI must verify locked base/gui.
- `python -m pytest -p no:cacheprovider tests/ws_a/test_loaded_candidate_trials.py -q`: PASS, 3.
- `python -m pytest -p no:cacheprovider tests/ws_a -q`: PASS, 239.
- `python -m pytest -p no:cacheprovider tests/contracts/test_source_manifest.py -q`: PASS, 6 after manifest generation. Initial concurrent full-suite run began before manifest regeneration and reported one manifest failure; not described as PASS.
- `python -m ruff check .`, `python -m ruff format --check .`: PASS.
- `python -m mypy`: PASS, 77 source files; both GUI entries separate mypy: PASS.
- `python scripts/source_manifest.py --write` then `--check`: PASS, 163 files.
- `python scripts/check_public_data_boundary.py`: PASS.
- `python -m hatchling build`: PASS, sdist/wheel.
- Full existing-environment suite and contracts/WS-B/WS-A/system combined regression: completion pending; not PASS. Exact commands: `python -m pytest -p no:cacheprovider -q` and `python -m pytest -p no:cacheprovider tests/contracts tests/ws_b tests/ws_a tests/ws_a_system -q`.
- Work-record/diff checks, PR and final-head CI: pending; not approved or merged. No implementation policy decision needed; ordinary PR review remains required.
- CV/manufacturer/P06/production/Gate status unchanged.
