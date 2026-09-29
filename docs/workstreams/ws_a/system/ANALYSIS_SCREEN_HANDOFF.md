# 합성 HVAC 화면 사용 및 팀 연결

## 사용

저장소에서 실행한다.

    uv sync --locked --extra gui
    uv run --locked --extra gui streamlit run src/agent_hvac/app/analysis_screen_app.py --server.address 127.0.0.1 --server.port 8510

브라우저에서 http://127.0.0.1:8510 을 연다. 기존 LJH의 design_workbench/streamlit_app 진입점은 변경하지 않았다.

1. 냉매·연속유량·실내 경계온도를 입력한다.
2. 외기·현열부하와 그 출처(합성/사용자/확인값)를 입력한다.
3. 기준 압력·공기유량·UA를 지정한다.
4. 변경을 허용한 축만 체크하고 범위·표본 수·최대 계산 수를 지정한다.
5. 수치 탐색구간과 preset 가정을 확인한다. 냉매/운전범위를 바꾸면 적절한 bracket도 명시해야 한다.
6. 후보 미리보기에서 개수와 조건을 확인하고 확장 입력을 다운로드할 수 있다.
7. 해석 실행 후 모든 후보의 수렴·설계적합·부하일치·실패 원인을 확인한다.
8. 전체 실행 기록 JSON으로 조건·출처·확장후보·물성/패키지 버전·source hash·trace·결과를 보존한다.

입력이 바뀌면 이전 결과와 미리보기를 숨긴다. 이전 실행 기록이 필요하면 변경 전에 다운로드한다.
새 실행은 과거 실행의 목표를 바꿔 성공 처리하지 않는다.
예상 밖 오류는 ERROR로 표시하며 이미 완료한 후보와 오류 메시지를 다운로드할 수 있다.
미수렴 성능은 빈 값이며 0W/COP0으로 표시하지 않는다. 가까운 유효 후보와 목표부하 일치를 구분한다.

초기 예제는 R410A·연속0.05kg/s·실내21°C, 합성 외기35°C·부하3000W다.
2.8/3.5MPa 토출압력2후보 중1회로가 수렴하지만3kW 일치는 없다.
21°C는 방의 열용량·온도 응답을 푼 결과가 아니라 지정 경계조건이다.

## 협업 범위

| 담당 | 사용할 것 | 다음 검토 |
|---|---|---|
| 관리자 / A-System | compact 입력·축·예산·run archive | 요구조건/허용변경 범위를 확정하고 원본실행 보존 |
| WS-A @daeyunekim | case별 전체 trace, failed_stage/pressure_history, source hash | 부품 모델 적용범위·수치 검토; 단상 배관 guard를 단순 제거하지 않음 |
| WS-B @sangryul1208 | 조건/단위/출처 표기 방식 참고 | 기존 R744 공식자료 확보·권한·Excel/loader 업무 지속. 합성 R410A preset을 제품 DB에 넣지 않음 |
| WS-D/E @ljh67340 | 신규 analysis_screen_app.py 진입점, analysis_screen.py 표시 helper | 원하면 기존 메뉴에서 별도 화면 연결. 기존 PR36 파일을 이 작업이 수정하지 않음 |
| 향후 WS-C Agent 담당 | CompactAnalysisInput → expand_analysis → run_analysis | 승인된 입력의 신뢰경계를 유지하고 결과를 그대로 설명 |

PR을 통한 공유 문서를 작성했으며 담당자에게 별도 댓글/메시지를 발송하지 않았다.
각 담당자의 검토·수용·승인 사실은 실제 응답이 있기 전 추정하지 않는다.

## 향후 Agent의 호출 예제

아래는 신뢰할 수 있는 애플리케이션이 이미 승인된 입력을 로드하는 호출 예다.
파일 경로나 승인범위를 LLM이 임의로 고르게 하지 않는다.
자연어 parsing, LLM SDK 등록, 인증/HITL 승인 상태기계는 이번 구현에 포함하지 않는다.

    from agent_hvac.properties.coolprop_backend import CoolPropBackend
    from agent_hvac.solvers.system_cycle.analysis_input import CompactAnalysisInput, expand_analysis
    from agent_hvac.solvers.system_cycle.analysis_manager import run_analysis

    # approved_bytes는 애플리케이션이 보관한 승인 입력이며 LLM 제안값으로 덮어쓰지 않는다.
    approved = CompactAnalysisInput.model_validate_json(approved_bytes)
    authorized_cases = expand_analysis(approved)

    def simulate_approved_request():
        return run_analysis(CoolPropBackend(), authorized_cases).model_dump(mode="json")

Agent에 이처럼 입력 변경 인자가 없는 실행 도구를 제공할 수 있다.
새 요구/범위는 별도 승인과 입력 저장 후 새로운 도구 인스턴스 또는 실행으로 연결한다.
authorization_ref 텍스트만으로 사용자 인증이나 승인 검증이 완료되는 것은 아니다.

공통 frozen SimulationTool은 DesignSpecification→SimulationResult 계약이다.
이번 내부 합성 AnalysisReport를 그 결과로 위장하거나 FinalDesignPackage의 release_ready로
변환하지 않는다. 정식 공통 Agent 도구 연결에 계약 확장이 필요하면 별도 ACR로 검토한다.

## 검증과 제한

집중 AppTest로 후보 미리보기·실제 계산·부하 일치/불일치·실패 빈값·입력변경 무효화·오류 다운로드를 검증했다.
로컬 HTTP health 응답도 확인했다. 브라우저 도구 자체의 sandbox 시작 실패로 육안 시각 QA는 BLOCKED다.
원격CI는 결제/사용 한도 문제로 job 시작 전 BLOCKED이며 로컬 PASS/병합과 구분한다.

[간소화 입력](COMPACT_ANALYSIS.md) · [해석 관리](ANALYSIS_MANAGER.md) ·
[화면 작업 기록](../../../development_log/2026-09-24_WS-E-analysis-screen.md).
제조사 검증/P06 전체/Gate/실제 실내 제어의 완료를 의미하지 않는다.
