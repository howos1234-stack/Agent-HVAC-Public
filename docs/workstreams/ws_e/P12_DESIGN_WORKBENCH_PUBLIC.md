# P12 공개 설계 워크벤치

이 화면은 제품 데이터 없이 일반 부품 모델과 사용자가 직접 입력한 조건으로 `BaselineCycleSolver`를 실행하는 WS-E 편집기입니다. 제조사 제품 선정, 성능 검증, production 적용 또는 Gate 승인을 의미하지 않습니다.

## 실행

```powershell
uv sync --locked --extra gui
uv run --locked --extra gui streamlit run src/agent_hvac/app/design_workbench_app.py
```

브라우저에서 다음 순서로 사용할 수 있습니다.

1. `새 빈 캔버스`에서 냉매를 선택하고 빈 캔버스를 시작합니다.
2. 압축기, gas cooler 또는 응축기, 팽창밸브, 증발기를 추가합니다.
3. 부품을 드래그해 배치하고 포트를 끌어 폐회로를 만듭니다.
4. 설계조건 6개를 원 단위와 함께 입력하고 적용합니다.
5. `캔버스 구성으로 baseline 계산 실행`을 눌러 상태점, 컴포넌트 입·출구 온도·절대압력, COP 및 열량을 확인합니다.

## 보존되는 검증 규칙

- 계산 결과는 전체 프로젝트 지문과 연결됩니다. 조건, 연결, 부품 또는 속성이 바뀌면 이전 결과를 숨깁니다.
- 압력 입력은 절대압 단위 `Pa`, `kPa`, `MPa`, `bar`, `bar(a)`, `bara`를 지원하며 내부에서 `bar(a)`로 정규화합니다.
- 효율 입력은 `dimensionless`, `1`, `%`, `percent`를 지원하며 내부에서 무차원 값으로 정규화합니다. 음수 효율의 부호는 보존한 뒤 유효 범위 검사에서 거부합니다.
- `bar(g)`와 `barg`는 근거 없이 절대압으로 변환하지 않고 명시적으로 거부합니다.
- 네 핵심 부품은 임의 ID를 사용해도 부품 종류와 연결 순서로 인식합니다.
- 현재 baseline solver가 지원하지 않는 부품이 폐회로에 연결되면 실행을 차단합니다.
- 일반 baseline 결과와 P09 합성 제품 mock 결과를 서로 다른 흐름으로 표시합니다.

## 실제 브라우저 검증 근거

- [폐회로 캔버스](../../validation/ws_e/workbench_canvas_closed_loop.png)
- [수렴 결과와 컴포넌트 상태](../../validation/ws_e/workbench_converged_states.png)
- [미지원 부품 연결 차단](../../validation/ws_e/workbench_unsupported_component.png)

검증 절차와 브라우저 버전은 공개 작업 기록에 남깁니다. AppTest의 프로젝트 주입 검사는 이 실제 Chromium 포인터 검증과 구분합니다.
