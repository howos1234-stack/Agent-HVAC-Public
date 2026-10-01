# WS-E P-h/T-s vapor-dome visualization

## 작업 정보

- 담당: LJH / WS-E
- Phase / Workstream: P12-P13 / WS-E
- 작업 상태: REVIEW_PENDING
- 브랜치: `codex/ws-e/ljh67340/vapor-dome-charts`
- 시작 integration: `eb2c5c3a82ec47b81cecedc40f9dd1017643d2f3`
- 범위: 결과 화면의 P-h/T-s 포화 경계와 차트 가독성

## 수행 내용

- 단일 냉매 상태점에 대해 CoolProp 포화액·포화증기 상태를 계산해 P-h와 T-s에 표시한다.
- 두 경계를 임계점에서 이어지는 한 개의 베이퍼돔 경로로 그린다. 임계점은 CoolProp의 임계온도 바로 아래에서 계산하며, 실패한 개별 점은 임의 보간하지 않는다.
- 사이클 최저압의 1/3 미만인 포화점은 차트 표시에서 제외해 실제 사이클이 과도하게 축소되지 않도록 한다. solver 상태점과 물성 계산값은 변경하지 않는다.
- 그래프 높이, 폭과 베이퍼돔 대비를 키웠다. 계산 불가 냉매 또는 혼합 냉매 상태점은 돔을 생략한다.
- 이는 일반 baseline 결과의 시각화이며 제조사 map, 실제 제품 성능 검증, 목표 달성, production 또는 Gate 승인이 아니다.

## 결정, 가정 및 출처

- 포화 상태는 프로젝트 냉매명과 설치된 CoolProp API를 사용한다.
- 차트 범위 필터는 표시 전용이며 solver 결과와 원본 상태점을 수정하지 않는다.
- 임계점 연결은 임계온도 바로 아래의 CoolProp 양쪽 포화 상태를 순서대로 연결한다.

## 검증 결과

- `uv run --locked --extra gui pytest tests/ws_e/test_streamlit_app.py tests/ws_e/test_design_workbench.py -q`: 87 passed.
- Ruff check/format, mypy, GUI 진입점 2개 strict mypy, source manifest 162개와 package build: PASS.
- 실제 in-app Chromium의 R744 baseline에서 P-h 압력축이 약 1–10 MPa로 집중되고 P-h/T-s 모두 단일 베이퍼돔 경로와 사이클 상태점이 함께 표시됨을 확인했다.
- R134a 회귀에서 저압 필터, 단일 경로, 임계점 양쪽의 동일 압력과 근접 엔탈피를 확인한다.

## 남은 제한

- 포화 경계는 CoolProp 가용 범위에 의존한다. 지원하지 않는 냉매와 부분 물성 실패를 데이터 추정으로 보완하지 않는다.
- 상태점 자체의 물리 타당성 및 제조사 적용영역은 이 차트가 판정하지 않는다.

## 종료 및 인수인계

- 새 시각화는 공개 PR #14에서 분리한 별도 브랜치와 PR로 검토받는다.
- 다음 담당자는 CoolProp 경계, 단위, 부분 물성 실패, 차트 회귀와 최신 원격 CI를 확인한다.
- Gate 경계: GUI 시각화 보완이며 실제 HVAC 검증, production 또는 Gate 승인 아님.
