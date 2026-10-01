# WS-E beginner baseline input guidance

## 작업 정보

- 담당: LJH / WS-E
- Phase / Workstream: P12 / WS-E
- 작업 상태: REVIEW_PENDING
- 브랜치: `codex/ws-e/ljh67340/baseline-input-guidance`
- 시작 integration: `eb2c5c3a82ec47b81cecedc40f9dd1017643d2f3`

## 수행 내용

- 설계조건 편집기에 처음 사용자를 위한 baseline 입력 가이드를 추가했다.
- R134a, R410A, R744별 실행 예시를 제공하되 제품 허용범위나 설계 권장값이 아님을 명시했다.
- 현재 입력으로 절대압, 고압·저압 관계, 양의 질량유량, 효율 범위와 절대온도를 검사한다. 명백한 오류가 있으면 baseline 실행 버튼을 차단한다.
- CoolProp 포화 상태를 이용해 흡입 과열도, 응축기 출구 과냉도 또는 임계압력 이상 gas-cooling 조건을 설명한다. 경고값을 자동 수정하거나 제조사 운전영역으로 해석하지 않는다.

## 결정, 가정 및 출처

- 물성 기준은 기존 baseline solver와 같은 CoolProp 냉매 식별자를 사용한다.
- 압축기 흡입 기체·과열 상태와 아임계 응축기 액체·과냉 출구는 단일단 baseline 해석을 돕는 안내 기준이다.
- 냉매별 예시는 기존 프로젝트와 공개 합성 검증 입력이며 허용범위 또는 최적값이 아니다.

## 검증 결과

- 집중 회귀: `70 passed`.
- Ruff check/format, mypy 및 GUI 진입점 2개 strict mypy: PASS.
- 실제 in-app Chromium `http://127.0.0.1:8523`에서 R744 예시, 필수값 안내와 입력 가이드 노출을 확인했다.

## 남은 제한

- 제조사 envelope, 제품별 압력·온도 한계와 안전 규정은 포함하지 않는다.
- 포화 기준을 계산할 수 없으면 이유를 경고하며 값을 추정하지 않는다.

## 종료 및 인수인계

- 관리자에게 GUI 안내 문구, 명백한 오류 실행 차단과 경고·오류 구분을 검토 요청한다.
- 실제 제품 자동선정, 제조사 검증, production, CV/P06 전체 및 Gate 상태는 변경하지 않는다.
