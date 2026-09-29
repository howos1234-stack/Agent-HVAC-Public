# Agent-HVAC Public

Python 3.12 기반 HVAC 물리 계산·제품 데이터 계약·합성 검증용 공개 개발 저장소입니다.
압축기/밸브/배관/1D 열교환기, CoolProp baseline, TESPy 비교, synthetic system cycle,
Excel loader, 합성 최적화 및 Streamlit 결과 화면을 포함합니다.

## 범위

2026-09-29 integration snapshot `0ea4828467d71cbc9ae8da71a548c43976ee6491`에서 코드 중심으로 추출했습니다.
새 Git 이력으로 시작하며 원래 저장소의 커밋·PR·댓글·실행 로그는 복제하지 않았습니다.
제조사 원본, 후보 조사표, 선정 출력의 수치 요약, 내부 작업 로그와 승인 기록은 제외했습니다.
`docs/product_data/templates/`에는 테스트가 사용하는 빈 schema 양식만 있습니다.
합성 제품의 ELIGIBLE은 실제 제품 승인이나 제조사 검증 PASS가 아닙니다.
이 공개본은 미병합 WS-C Agent/WS-E 워크벤치 PR을 포함하지 않습니다.

## 실행

```powershell
uv sync --locked
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked python scripts/source_manifest.py --check
uv build --no-build-isolation

uv sync --locked --extra gui
uv run --locked --extra gui streamlit run src/agent_hvac/app/streamlit_app.py
```

기본 실행·합성 테스트에는 API 키가 필요하지 않습니다.
[시스템 예제](examples/system_cycle/README.md), [의존성](docs/architecture/DEPENDENCIES.md),
[공개 개발 절차](docs/development/WORK_PROTOCOL.md)를 참조하세요.
보존된 synthetic 검증 문서의 과거 실행·승인 표기는 원래 개발 당시 기록이며,
공개 저장소에서 새로 검증한 결과는 Actions 및 CURRENT_STATE에 별도로 기록합니다.
문서의 과거 내부 PR/개발 로그 링크는 공개본에서 제공되지 않을 수 있습니다.

## 협업과 CI

새 작업은 이 저장소의 integration에서 분기하여 이 저장소에 PR을 생성합니다.
private 저장소 전체를 merge/push/mirror하지 마세요. 필요한 코드만 검토 후 옮기고 공개 가능성을 재점검하세요.
Windows/Ubuntu × base/gui 표준 GitHub-hosted runner 4개로 검증합니다.
공개 저장소의 표준 runner 실행은 GitHub의 무료 사용 정책 대상이며 실행시간/동시성 제한은 적용됩니다.
기존 private PR의 CI 결과가 자동으로 바뀌는 것은 아닙니다.

## 라이선스 및 데이터

공개 가시성과 별도의 재배포 라이선스 부여는 다릅니다. 프로젝트 자체 라이선스는 아직 정하지 않았습니다.
기존 코드의 저작자·출처 표시는 유지하며 제3자 의존성은 각 라이선스를 따릅니다.
제조사 자료나 개인 정보·키를 추가하지 마세요. 실제 설비 설계/제품 자동선정/제조사 정확도 또는 Gate 승인을 주장하지 않습니다.
