# R410A 설계 조사: 요구조건·운전범위·부하·안정성·제어

상태: 1–5 조사 수행 완료 / 지정 범위3kW 설계점 미발견 / 로컬 검증 및 검토 기록. 사용자의 1–5 자율 수행 요청에 따른 별도 합성 개발이며 제품/Gate 승인 아님.

## 1. 고정조건과 사전 탐색 범위

- USER 고정: R410A, 냉매 연속 유량0.05kg/s, 완전혼합 실내 경계21°C.
- 합성 기준: 외기35°C, 현열부하3000W, cp1006J/(kg K), eta_is0.75.
- 제어범위를 몰래 늘리지 않음: 압력 p_low0.8..1.2MPa(a), p_high2.8..4.5MPa(a).
  p_high는 약4.9012MPa 임계압보다 낮은 구간으로 제한. 제조사 envelope를 의미하지 않는다.
- 실내 공기0.5..1.5kg/s, 실외 공기0.5..1.2kg/s, 응축UA220..1200W/K,
  증발UA200..800W/K를 명시적인 유한 표본으로 조사. 전체 연속영역 탐색/유일성 증명 아님.
- 주요 12점: p_high[2.8,3.5,4.5]MPa × indoor_air[0.5,1.5]kg/s × evaporator_UA[200,800]W/K.
  기준 p_low1MPa, outdoor_air0.8kg/s, condenser_UA800W/K.
- 보완 표본: p_low0.8/1.2MPa, condenser_UA400/1200W/K, outdoor_air0.5/1.2kg/s;
  그 외 기준값은 p_high3.5MPa, indoor_air1.5kg/s, evapUA800.
- 저용량 표본: p_high4.5MPa, condenserUA220/260/320, evapUA400/800, indoor_air1.5.
- 처음에는 zero-loss 3개 배관, HX80cells. 실제 배관손실 비교는 기존 비영 배관 예제를 사용한다.
  내부 h/p/에너지/질량 수렴 기준은 변경하지 않는다.

## 2–3. 실행과 물리적 검토

기존 결정론적 solver로 모든 표본을 cold-start 평가하며 실패를 삭제하지 않는다.
고정유량·단열배관·등엔탈피 밸브에서는 Qev=m(h_suction-h_condenser_out).
증발기/흡입은 건증기, 응축기 출구는 액체인 일반 냉방 경로를 별도 적합성 조건으로 검사한다.
CoolProp의 포화 경계 표본을 이용해 h_g(p_low), h_f(p_high)를 계산하여3kW 요구와 대조한다.
이 진단은 고정 의사순수 EOS 내부 일관성 검사이며 새로운 공통 PQ/TQ API나 독립 EOS 검증이 아니다.
표본 기반 bound를 연속범위 수학적 증명으로 과장하지 않는다.

## 4. 강건성 검토

수렴한 기준점과 유효한 최저용량 후보에 대해 외기30/35/40°C,
부하2500/3000/3500W, h 초기 구간 변경, HX40/80/160cells 및 비영 배관 비교.
초기구간 반복의 Q/COP 상대차<=1e-5, 80→160cells Q/COP 상대차<=2%를
사전 수치 민감도 기준으로 사용한다. 부하 일치1W는 별도 기준이며 물리 정확도 주장이 아니다.
불만족이면 그 차이를 보고하고 허용오차를 늘리지 않는다.

## 5. 제어 방식 결정

현재 모델은 압축기 속도/밸브 개도로 유량을 계산하지 않고 압력·유량을 지정한다.
따라서 팬/설계조건 변경은 현 solver로 비교 가능하나 실제 속도·밸브 제어 안정성은 미구현이다.
고정 연속 유량에서 부하 일치점을 찾지 못하면 제어 성공을 선언하지 않는다.
On/off duty는 m_on=0.05와 평균유량을 구분한 참고 에너지 산술만 제시하며
연속0.05kg/s 제약을 만족하는 해나 실제 온도 응답 시뮬레이션으로 사용하지 않는다.


## 실제 결과

전체39표본: 수렴20 / 미수렴19 / 3kW 일치0. 주 설계24표본은 수렴7 / 미수렴17이다.
나머지는 기준점9개 및 최저용량 후보6개의 수치·주변조건 비교다.
실패 표본의 냉방열/COP는 빈 값으로 유지한다. 미수렴을0W로 간주하지 않는다.

| 항목 | 기준점 | 주 설계표의 저용량 후보 |
|---|---:|---:|
| 냉매 유량 |0.05kg/s|0.05kg/s|
| 흡입/토출 압력 |1.0/3.5MPa(a)|1.0/4.5MPa(a)|
| 실내/실외 공기 |1.5/0.8kg/s|1.5/0.8kg/s|
| 응축/증발UA |800/800W/K|260/800W/K|
| 냉방능력 |7608.861254W|5391.132086W|
| 압축기 전달동력 |2407.335061W|2945.711806W|
| COP |3.160698889|1.830162773|
| 공급공기 |15.957680°C|17.427348°C|
| 3kW 부하 잔차 |+4608.861254W|+2391.132086W|

저용량 후보는 finite sample 중 부하에 가장 가까운 점이며 최적 설계·목표 충족점이 아니다.
용량을 줄인 후보의 COP가 더 낮아졌으므로 용량 감소를 효율 향상으로 해석하지 않는다.
기존 component 수식·허용오차·물성 모델·reference state는 변경하지 않았다.

### 상조건 진단

p_low0.8..1.2MPa와 p_high2.8..4.5MPa를 각101개씩 표본화한 동일 CoolProp EOS에서
최소 h_g=421410.700857J/kg, 최대 h_f=330589.081729J/kg이었다.
액체 응축기 출구·건증기 흡입, 단열 배관과 등엔탈피 밸브라는 지정 모델에서는
Qev=m(h_suction-h_cond_out)이므로 표본 경계의 느슨한 하한은4541.080956W다.
3kW를 얻으려면 최소 흡입 h 기준에서도 응축기 출구 h=361410.700857J/kg가 필요하여,
위 표본의 액체 출구 범위를 넘는다. 실패를 숨기기 위해2상 배관 guard를 제거하지 않았다.
이는 선언된 유체·상·압력 표본·모델 조건의 진단이며 연속 전역 불가능 증명이나
다른 토폴로지·압력 범위·실제 제조사 장치에 대한 불가능 판정은 아니다.

### 주변조건 및 수치 민감도

- 초기 h 구간 변경: 기준점 Q 상대차8.255e-9, COP5.214e-8;
  후보 Q1.009e-7, COP2.043e-7. 사전 기준1e-5 이내 PASS.
- HX80→160cells: 기준 Q0.14138%, COP0.10431%; 후보 Q0.42015%, COP0.43004%.
  사전2% 기준 PASS. 이것은 격자 독립성 완전 증명/실측 정확도 보증이 아니다.
- 외기30°C: 기준8.054531kW, 후보6.286594kW. 외기40°C: 두 경우 모두 미수렴.
  고온 운전 범위가 확보됐다고 주장하지 않는다.
- 비영 단열 배관·HX dp: 기준7.604570kW, 후보5.379442kW 수렴.
  배관 점도는 합성 상수이며 실제 냉매의 운전별 점도 검증이 아니다.
- ±1% 토출압력 비교와 실내 공기1.0kg/s도 별도 입력·결과로 보존했다.
- 부하2.5/3/3.5kW 변경은 실내21°C 경계를 유지한 부하 잔차 후처리다.
  방의 열용량을 포함한 시간응답을 계산한 것이 아니다.

### 제어 결정

동일 압력·UA·장치·외기 조건의 유효 팬 유량 표본만 선택하도록 구현했다.
다른 응축기 UA나 압력의 설계점을 팬 제어 해로 바꾸어 쓰지 않는다.
두 기준 설계 모두2.5/3/3.5kW에 맞는 팬 설정 표본은 없었다.
압축기 속도/밸브 개도/질량유량 연성을 현재 solver가 제공하지 않으므로 이를
구현된 폐루프 제어기로 위장하지 않는다.

참고로 기준점의 3kW 평균 용량에 해당하는 단순 on/off 비율은39.4277%이고
냉매 평균유량은0.0197139kg/s다. 이는 연속0.05kg/s와 다르므로 요청의 해로 채택하지 않았다.
실제 온도 유지·short cycling·습도·기동 손실·전기효율은 계산하지 않았다.
다음 설계 변경은 연속 유량 고정 요구 또는 시스템 구성/운전 범위를 명시적으로 재검토하는 것이다.
이번 수행에서는 요청 고정값을 임의로 바꾸지 않았다.

## 사용 및 재현

```powershell
uv sync --locked
uv run --locked python scripts/run_design_study.py --input examples/system_cycle/r410a_design_study.json --output-dir artifacts/design-study/main
uv run --locked python scripts/run_design_study.py --input examples/system_cycle/r410a_stability_study.json --output-dir artifacts/design-study/stability
uv run --locked python scripts/run_design_study.py --input examples/system_cycle/r410a_candidate_stability.json --output-dir artifacts/design-study/candidate
uv run --locked python scripts/analyze_design_study.py --main artifacts/design-study/main/result.json --stability artifacts/design-study/stability/result.json --candidate artifacts/design-study/candidate/result.json --output artifacts/design-study/analysis.json
```

세 실행은 모든 표본을 저장한 뒤 목표 일치0개이므로 exit1을 반환한다. 입력·I/O 오류는 exit2다.
exit1만 보고 결과 파일을 버리지 않는다. 각 디렉터리에 metadata/input/source hash,
case별 전체 수렴 이력, result.json과 summary.csv를 보존한다. 예제 case 목록은 단위형이며
refrigerant/연속유량/실내경계를 바꾸는 표본, 중복ID, 결과 누락·결과 지표 변조를 거부한다.

[추적 가능한 수치 요약](../../../validation/r410a-design-study-results.json).
[세션 검증 기록](../../../development_log/2026-09-23_WS-A-r410a-design-study.md).
물성 출처는 [CoolProp R410A](https://coolprop.org/fluid_properties/fluids/R410A.html)의
Lemmon2003 의사순수 EOS이며 별도의 제조사/실측 교차검증은 아니다.
