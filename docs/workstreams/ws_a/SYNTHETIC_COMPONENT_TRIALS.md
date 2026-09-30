# 합성 컴포넌트 후보별 평가 연결

이 WS-A 연결층은 여러 **mock ProductRecord**의 계산을 입력 순서대로 독립 실행한다. 압축기는 기존 performance map, 팽창밸브는 기존 map과 입구 물성 검사, HX는 명시적으로 선택한 rated point와 P05 constant-UA를 그대로 호출한다. 물리식·보간·envelope·SI·출처 계약을 바꾸지 않는다.

`ComponentCandidateTrial`에는 호출자가 고유한 `candidate_id`와 장비별 입력을 넣는다. `evaluate_synthetic_component_trials()`는 같은 순서로 `ComponentTrialOutcome`을 반환한다. 성공한 후보의 `result`에는 기존 장비별 계산값과 상세 source ID가 남는다. 실패한 후보는 `REJECTED`와 오류 종류·메시지, 요청한 제품·record·parent source ID를 남기되 **result는 `None`**이다. 실패한 계산이 앞선 후보의 출력이나 상세 출처를 물려받지 않는다. 예상된 HVAC 도메인 오류만 후보 실패로 분리하고 프로그래밍 오류는 그대로 전파한다.

이 함수는 점수, 순위, 최적 후보, 부하 적합성 또는 전체 시스템 제약 판정을 만들지 않는다. `is_mock=False` 제품은 이 합성 시험 경로에서 거부한다. 화면·보고서에 표시할 때에도 `HYBRID_VALIDATION`/합성 데이터임을 유지하고 실제 제품 추천이나 제조사 정확도 검증으로 표시해서는 안 된다. 제품 선정 정책·목적함수·시스템 폐회로 연결은 별도 관리자 범위이며, 실제 ProductRecord의 CV-1~CV-3 검증도 별도로 진행한다.
