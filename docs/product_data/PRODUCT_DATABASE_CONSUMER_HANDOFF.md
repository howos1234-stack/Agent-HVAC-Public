# Product database consumer handoff

이 문서는 WS-B의 공개 제품 DB를 사용하는 WS-C·WS-E가 기존 API만으로 적재 상태를
판단하는 방법을 설명한다. 예시는 공개 저장소의 합성 workbook에만 적용되며 실제
제조사 성능 검증이나 제품 사용 승인을 뜻하지 않는다.

## 읽기 순서

1. `ExcelComponentRepository(root).reload()`를 호출한다.
2. 반환된 `ReloadSummary`의 `database_version`, 파일 수, 제품 수와 `errors`를 저장한다.
3. `repository.records` 또는 `repository.search(ComponentQuery(...))`로 후보 제품을 찾는다.
4. 계산에 필요한 `rated_point_id`, `map_id` 또는 `envelope_id`가 제품 안에 실제로
   존재하고 그 record의 `use_status.automatic_selection`이 `ELIGIBLE`인지 확인한다.
5. record가 확인된 뒤에만 WS-A adapter 또는 계산기로 전달한다.

`loaded_products > 0` 또는 검색 결과에 제품이 있다는 사실만으로 계산 가능하다고
판단하면 안 된다. 제품 기본 행은 유효하지만 잘못된 참조가 있는 특정 rated point,
map 또는 envelope만 격리될 수 있기 때문이다.

## 상태 해석

| 관찰 결과 | 의미 | 소비 측 조치 |
|---|---|---|
| workbook fatal 오류, 제품이 `records`에 없음 | 파일 단위로 제품 전체 제외 | 기존 선택을 사용하지 말고 오류를 표시한다. |
| 제품은 있으나 필요한 record ID가 없음 | 해당 상세 parent가 격리됐거나 자료가 없음 | 제품을 계산 가능한 후보로 표시하지 않는다. |
| record는 있으나 `INELIGIBLE` | 원본은 보존됐지만 자동선정 제한 사유가 있음 | `reasons`를 표시하고 자동 계산에 사용하지 않는다. |
| 필요한 record가 `ELIGIBLE` | 구조·사용 상태 검사를 통과함 | 냉매·운전조건 등 adapter의 추가 검사를 거친다. |
| `ReloadSummary.errors`가 비어 있지 않음 | 일부 파일 또는 상세 record에 진단이 있음 | 전체 DB 실패로 단정하지 말고 제품/record별 영향을 확인한다. |

진단 문자열은 사람과 로그를 위한 정보다. 소비 코드가 문자열 문구를 파싱해 상태를
추정해서는 안 된다. 현재 공통 상태 모델에 없는 구조화 진단이 필요하면 WS-C·WS-E와
요구사항을 정리해 ACR 변경안으로 제안한다.

## `database_version`과 reload

`database_version`은 loader/schema 버전과 발견된 workbook 경로·내용 fingerprint에서
결정된다. 다음 규칙을 적용한다.

- reload 전 선택 결과에는 당시 `database_version`을 함께 보관한다.
- reload 후 버전이 달라지면 저장해 둔 `ProductRecord` 객체와 계산 결과를 재사용하지
  않는다.
- 새 `records`에서 제품과 필요한 record ID를 다시 찾고 ELIGIBLE 상태와 입력 조건을
  다시 검사한 뒤 계산한다.
- 버전이 같아도 실행 중인 repository의 현재 `records`를 기준으로 사용한다.

WS-E는 화면에 현재 버전과 최근 적재 오류를 표시하고, 버전 변경 시 이전 제품 선택을
무효화하는 동작을 WS-B·WS-C와 협의해야 한다. WS-C는 계산 요청에 사용한 DB 버전을
결과 provenance에 남기고, 실행 도중 버전이 바뀌면 재선택 또는 재실행을 요구해야 한다.
이 문서는 GUI나 Agent 구현을 직접 변경하지 않는다.

## 공개 합성 흐름 재현

기존 회귀는 pytest 임시 디렉터리에서 합성 compressor, expansion valve, gas cooler
workbook을 만든다. 다음 명령은 정상 적재, 일부 오류 격리, 복구 및 adapter 재사용을
검증한다.

```powershell
python -m pytest -p no:cacheprovider tests/ws_a/test_excel_component_bundle_reload.py -q
```

일반 API 조회 예제는 `examples/product_database/repository_handoff.py`에 있다.

```powershell
python examples/product_database/repository_handoff.py <synthetic-workbook-directory>
```

출력에는 DB 버전, 적재 요약, 진단과 제품별 rated point/map/envelope의 ELIGIBLE 여부가
포함된다. workbook을 수정한 뒤 같은 명령을 다시 실행해 버전과 record 상태의 변화를
비교할 수 있다. 공개 저장소에는 실행 과정에서 생성된 workbook을 커밋하지 않는다.

## 인계 경계

- WS-B: loader 결과, 출처 참조, 격리 및 DB 버전 계약을 제공한다.
- WS-C: 필요한 상세 record의 존재·ELIGIBLE 상태와 DB 버전을 계산 입구에서 검증한다.
- WS-E: 제품 존재와 계산 가능 상태를 구분해 표시하고 reload 후 선택을 재검증한다.
- 새 공통 상태 모델, schema, GUI 또는 Agent 변경은 담당자 협의와 필요 시 ACR 이후에
  진행한다.

실제 제조사 원본·성능표·비공개 조사 기록은 이 공개 흐름의 입력이나 예제로 사용하지
않는다. CV-1~CV-3, 실제 제조사 검증, P06 전체, production 및 Gate 상태는 별도다.
