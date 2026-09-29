# 공개본 작업 절차

1. 최신 integration에서 별도 브랜치를 만들고 git 상태를 확인한다.
2. 목적·변경 범위·검증 계획을 세션 기록에 남긴다.
3. 코드와 합성 fixture만 변경한다. 제조사 조사 데이터·내부 작업 기록은 올리지 않는다.
4. uv sync --locked로 base, uv sync --locked --extra gui로 GUI 환경을 검증한다.
5. pytest, Ruff check/format, mypy, GUI streamlit_app.py 별도 mypy, source_manifest.py --check, uv build --no-build-isolation을 수행한다.
6. 소스가 바뀌면 source_manifest.py --write로 재생성하고 diff를 검토한다.
7. CURRENT_STATE와 세션 기록을 commit한 뒤 python scripts/check_work_record.py --base <실제기준SHA>를 실행한다.
8. 이 공개 저장소의 integration 대상으로 PR을 제출한다. CI와 코드 리뷰 후 병합한다.

각 검사는 PASS/FAIL/NOT_RUN/BLOCKED로 구분한다. 실제 실행한 환경만 PASS로 기록한다.
민감 자료가 발견되면 공개 업로드 전에 중단하고 알린다. private Git 이력·PR 댓글을 가져오지 않는다.
