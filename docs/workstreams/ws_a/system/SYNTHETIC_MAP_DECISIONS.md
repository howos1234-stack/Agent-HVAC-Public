# 사용자 위임에 따른 합성 회로 결정

2026-09-22: 사용자가 미해결 1–3을 자율적으로 정리하고 전체 작업을 계속하도록 지시했다.
이 지시를 DB 없는 합성 시스템 연결의 착수 근거로 기록한다. 과거 PR39 HOLD 의견은 삭제하지 않고,
제품 CL-1/압축기 map 토출상태 ACR·제조사 정확도·Gate 승인은 별도 유지한다.

## 확정 범위

P02 eta-is 압축기 + P05 합성 constant-UA 병류 HX + 등엔탈피 밸브 + P04 단상 배관 3개.
유량/흡입·토출 절대압은 지정 입력. 제품 exact-rated HX가 아니라 명시된 AGENT_ASSUMPTION UA와
지정 HX Δp를 사용한다. 실제 물성 CoolProp, DB/제품 map/출력 power 혼용 없음.
배관 점도와 U'는 입력으로 출처/가정을 보존한다. 밸브 직후 2상 배관은 모델링하지 않는다.

미지수 2개는 h_suction, p_valve_outlet. 독립 residual은 Rh=h_return-h_suction 및
Rp=p_return-p_suction. 고정 유량의 전체 에너지 검사는 Rh와 종속적이므로 세 번째 방정식으로 세지 않는다.
질량·에너지·온도·phase·부품 연속성은 검증 조건이다. 흡입/토출 온도는 추가 고정하지 않는다.

외부 엔탈피 scan/이분법 100회 한도를 유지한다. 각 h 평가마다 지정한 밸브 출구 압력 구간에서
압력 잔차를 bracket scan하고 safeguarded secant/주기적 bisection으로 푼다. 무효 점을 가로지르지 않는다.
압력 내부 기준은 <=0.01 Pa, 최대 60회; 외부 최종 p 기준 <=1 Pa, h<=0.01 J/kg,
T<=1e-4 K, 상대 energy<=1e-6, mass<=1e-12. bounds/반복/잔차는 모두 기록한다.
정체, 범위 밖, bracket 없음, 비유한 수, 반복한도는 실패이며 허용오차를 늘리지 않는다.
유한 샘플은 전체 구간 연속성/유일성 증명이 아니다. 샘플된 유효 경로의 수치적 root만 보고한다.

운전맵은 지정 p_high × sink inlet T의 cold-start 독립 격자 실행이다. 실패점을 삭제/보간하지 않고
JSON 전체 결과와 CSV 요약에 기록한다. 최대 점수 제한으로 실수로 과도한 계산을 방지한다.
S3/S4는 기존 A-System의 연속 작업 단위이며 이번 사용자 지시에 따라 함께 완성하되 다른 major phase나
GUI/optimizer/제품 데이터 개발로 확장하지 않는다. 로컬 검증·Git 게시·integration 병합은 구분한다.
