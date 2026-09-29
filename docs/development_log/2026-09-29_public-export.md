# 작업 기록: 코드 중심 공개 snapshot

## 식별 및 범위
- Phase / Workstream: Public repository preparation / Integration
- 작업 상태: REVIEW_PENDING
- 수행자 / human owner: Codex / repository owner
- 날짜: 2026-09-29 KST
- 목적: 기존 비공개 보존, 허용한 코드/합성테스트만 새 이력으로 공개
- 범위: source/tests/scripts/examples, generated schema, blank workbook, selected synthetic documentation

## 수행 내용
- Source snapshot 0ea4828467d71cbc9ae8da71a548c43976ee6491에서 allowlist로 추출했다.
- 기존 Git history/PR/comments/logs와 manufacturer research workbook/point summaries는 복제하지 않았다.
- 공개본 README, AGENTS, workflow 안내와 현재 상태를 새로 작성했다.

## 결정, 가정 및 출처
- 수치 코드/테스트/lockfile은 기준 snapshot에서 보존한다. 공개본 manifest는 실제 inventory로 다시 생성한다.
- 자체 라이선스를 임의 부여하지 않는다. 표준 Windows/Ubuntu runner만 사용한다.
- 사용자 요청에 따라 별도 공개 저장소를 준비하며 기존 저장소는 비공개 유지한다.

## 검증 결과
- 파일 allowlist와 알려진 키 패턴/제조사 자료 제외 점검 완료. 제한적 점검이며 완전한 보안감사 보증 아님.
- 로컬/원격 검증은 실제 실행 후 추가 기록한다. 미실행은 NOT_RUN.

## 종료 및 인수인계
- integration에서 분기해 공개 가능한 변경만 PR로 제출한다. private repo 전체 merge/mirror 금지.
- 제조사 검증·실제 제품 자동선정·P06전체·Gate 승인 없음.

### Completed validation and publication
- Public URL: https://github.com/howos1234-stack/Agent-HVAC-Public ; original Agent-HVAC remains PRIVATE.
- Initial code commit: b954c9de58e290439e8ff90211d7705e559e3ae1; main and integration created independently of private history.
- `uv sync --locked --offline --extra gui`: PASS, Python 3.12.14.
- `.venv/Scripts/python.exe -m pytest -q --junitxml=artifacts/public-gui.xml`: PASS, 614 passed in 330.82 seconds.
- `.venv/Scripts/ruff.exe check .` and `ruff format --check .`: PASS, 148 files.
- `.venv/Scripts/mypy.exe`: PASS, 72 files; `mypy src/agent_hvac/app/streamlit_app.py`: PASS, 1 file.
- `.venv/Scripts/python.exe scripts/source_manifest.py --write` and `--check`: PASS, 150 files.
- `uv build --offline --no-build-isolation`: PASS, wheel and sdist; excluded material absent from inspected archives.
- Source/tests/scripts compared with source SHA (line endings normalized): unchanged. Blank workbook has 15 sheets and no data rows.
- Remote run 36565346488 at initial code commit: Windows base/gui PASS; Ubuntu base/gui FAIL. All four runners executed; this is not a billing block.
- Ubuntu base: 588 passed, 1 failed, 2 skipped. Ubuntu GUI: 613 passed, 1 failed.
- Both Ubuntu failures: test_small_heat_pipe_failure_is_retained_not_relaxed in tests/ws_a_system/test_network_map.py:98. Expected component-numerical-failure; actual evaluated. Physical root cause not established; no numerical assumptions, tolerance, assertions or solver were changed to suppress it.
- This final update changes documentation only. It does not assert full CI PASS or approve private outstanding PRs.
- Repository preparation is complete; overall code validation remains REVIEW_PENDING until this cross-platform difference is reviewed in a separate PR.
