# 냉매 별칭표 0.1.0 — 검토 초안

> 상태: **PENDING / REVIEW ONLY**  
> ACR-0002 승인 전에는 이 표를 loader의 승인 목록으로 사용하지 않는다.

## 파일·버전·담당

- 검토 중 기준 파일: `docs/workstreams/ws_a/REFRIGERANT_ALIASES_0.1.0.md`
- 별칭표 버전: `0.1.0`
- 승인 뒤 runtime 후보 경로: `src/agent_hvac/database/refrigerant_aliases.json`
- 의미·canonical mapping 담당: WS-A
- Excel 검증·loader release 반영 담당: WS-B
- 최종 승인·버전 release 담당: @howos1234-stack

승인 뒤 별칭표 수정은 별도 리뷰와 버전 증가가 필요하다. loader와 database metadata에는
사용한 `alias_table_version`을 기록해 같은 workbook이 어떤 규칙으로 해석됐는지 재현한다.

## 0.1.0 제안 목록

| canonical identifier | 허용하는 원문 label | 첫 자동 선정 |
|---|---|---|
| `R744` | `R744`, `CO2`, `CarbonDioxide` | R744 transcritical cooling만 |

## 정규화와 원문 보존

1. 비교 전에 앞뒤 공백을 제거하고 Unicode case-fold만 적용한다.
2. 중간 공백·하이픈·구두점을 지우거나 fuzzy matching하지 않는다.
3. 어떤 별칭이 매칭돼도 제조사 원문은 `original_refrigerant_label`에 그대로 보존한다.
4. canonical 값 `R744`와 원문 label을 둘 다 ProductRecord 상세 record에 저장한다.

예를 들어 ` co2 `는 trim/case-fold로 `R744`에 연결할 수 있지만, `R-744`나
`carbon dioxide`는 이 버전 표에 없으므로 사람이 명시적으로 추가 승인하기 전에는 추정하지 않는다.

## 알 수 없거나 모호한 label

- **UNKNOWN**: 표에 없는 label은 `UNAPPROVED_ALIAS` 진단과 함께 그 냉매를 참조하는
  상세 rated point/map/envelope를 격리한다. 원 workbook은 수정하지 않는다.
- **AMBIGUOUS**: 하나의 정규화 label이 둘 이상의 canonical 냉매를 가리키면 별칭표 자체가
  잘못된 것이다. loader build/configuration을 실패시키며 임의의 하나를 선택하지 않는다.
- 제품 기본 행의 `supported_refrigerants`가 해석되지 않으면 제품 정체성과 검색 조건이
  불명확하므로 workbook fatal로 처리한다.
- 상세 record의 원문 label만 잘못된 경우에는 해당 상세 record만 격리하고 다른 유효 제품·record는 유지한다.

## 변경 절차

1. WS-A가 canonical 의미와 물성 backend 식별 가능 여부를 검토한다.
2. WS-B가 제조사 원문 사례와 충돌·중복을 검증한다.
3. 합성 workbook으로 known/unknown/ambiguous 및 원문 보존을 시험한다.
4. 관리자가 ACR/별칭 버전을 승인한다.
5. 별도 구현 PR에서 runtime JSON, loader, schema와 manifest를 함께 갱신한다.
