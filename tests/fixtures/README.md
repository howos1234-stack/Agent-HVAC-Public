# P00 Mock 데이터

모든 JSON은 공통 production schema로 검증되지만 모든 제품/계산/최적화는 가상이다. 숫자는 구조 예제이며 보존식이나 제조사 실측값과 일치한다고 주장하지 않는다. `is_mock=true`, 가상 출처, 경고, `release_ready=false`를 유지한다.

재생성: `uv run --locked python scripts/generate_mock_fixtures.py`

`final_design_package.json`을 GUI/report 개발 입력으로 사용할 수 있다. 실제 제품 Excel 및 검증 benchmark로 사용하지 않는다.
