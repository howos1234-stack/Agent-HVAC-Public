# WS-A P04 1D 배관 모델 구현·검증 계획

- 상태: LOCAL_COMPLETE
- baseline: integration merge `07c72eeb36abbd11ef0c80a09d5300a0dd1bdc89`
- 담당: @daeyunekim / WS-A Physics

## 무엇을 만드는가

배관을 길이 방향의 작은 cell로 나누고 각 cell에서 열유입과 마찰 압력손실을 계산한 뒤,
동결된 `PropertyBackend.state_ph()`를 통해 다음 상태로 이동한다. 이 모델은 사용자가 지정한
0.5 m 같은 실제 길이가 냉매 상태와 압력에 미치는 영향을 결정론적으로 계산하기 위한 P05
열교환기 이전의 최소 기반이다.

## P04 최소 범위

- 정상상태, 일정 내경의 직선 원형관
- 고정 질량유량, 축방향 1D cell marching
- 단상 Darcy-Weisbach 마찰 압력손실
- 층류 `64/Re`와 난류 Haaland Darcy 마찰계수
- 주변온도와 선형 열관류율로 표현한 열유입/열손실
- 상관식 이름·원문·적용범위·phase·검증 case metadata registry
- 전체 압력손실, 전체 열전달, cell별 상태와 보존 잔차 출력
- 에너지·압력 상대 closure 잔차 `1e-12` 이하를 성공 조건으로 검사

2상 압력손실/열전달, 고도차, 국부손실, 관벽 축방향 전도, 복사, 오일, transient,
비원형관과 제품 DB 연결은 이번 단계에서 계산하지 않는다. 특히 2상 입력을 단상 식으로
몰래 계산하지 않고 명시적으로 거부한다.

## 방정식과 출처

단면적과 평균속도:

```text
A = pi D^2 / 4
v = m_dot / (rho A)
Re = rho v D / mu = 4 m_dot / (pi D mu)
```

cell 마찰손실(Darcy-Weisbach):

```text
dp = f_D (dx / D) rho v^2 / 2
```

- Darcy-Weisbach 참고: U.S. Bureau of Reclamation, Water Measurement Manual,
  Chapter 2 §16, <https://www.usbr.gov/tsc/techreferences/mands/wmm/chap02_16.html>
- 층류 완전 발달 원형관: `f_D=64/Re`, `Re<2300`.
- 난류: S. E. Haaland, “Simple and Explicit Formulas for the Friction Factor in
  Turbulent Pipe Flow,” Journal of Fluids Engineering 105(1), 89–90 (1983),
  <https://doi.org/10.1115/1.3240948>.

```text
1/sqrt(f_D) = -1.8 log10[(epsilon/(3.7 D))^1.11 + 6.9/Re]
```

Haaland는 `4000 <= Re <= 1e8`, `0 <= epsilon/D <= 0.05`로 제한한다. `2300 <= Re < 4000`
전이영역은 승인된 전이 정책이 없으므로 보간하지 않고 거부한다. 여기의 `f_D`는 Darcy
마찰계수이며 Fanning 마찰계수가 아니다.

열유입(냉매 쪽이 양수):

```text
q_cell = U' dx (T_ambient - T_fluid,in)
h_out = h_in + q_cell / m_dot
```

`U'`는 관 길이당 전체 열관류율 W/(m·K)이다. 관벽/단열/외부 대류를 조합하는 상세식은
이번 단계가 임의 상수를 만들지 않도록 입력 경계 밖에 둔다. 한 cell의 explicit 열전달
갱신이 주변온도를 통과했는지는 같은 출구 압력에서 `h_in`을 유지한 압력-only 기준 상태와
`h_out` 상태를 비교해 판정한다. 따라서 압력강하 자체가 만든 온도 변화는 열전달 overshoot로
오인하지 않는다. 실제 열전달 갱신이 주변온도를 통과하면 상태를 clamp하지 않고 수치 해상도
부족으로 실패시키며, 호출자가 `cell_count`를 늘려 다시 계산한다.

## 구현 전에 고정한 검증 기준

1. 0 길이 극한: 상태 불변, 압력손실·열전달 0을 절대오차 `1e-12` 이내로 확인.
2. 단열·상수 밀도 Darcy 해석해: 계산 압력손실을 닫힌식과 상대오차 `1e-10` 이내 비교.
3. 상수 `cp` 열유입 해석해:
   `T_out=T_amb-(T_amb-T_in) exp[-U'L/(m_dot cp)]`와 비교.
4. 격자 수렴: 10/20/40/80 cell에서 출구온도 오차가 단조 감소하고, 연속 두 격자의
   오차비가 1차 explicit marching에 맞게 `1.8~2.2`, 80-cell 상대오차 `5e-4` 이하.
5. 보존: `m_dot(h_out-h_in)-sum(q_cell)`과 누적 압력손실 closure의 상대 잔차 `1e-12`
   이하를 성공 조건으로 검사하고, 모든 cell에서 같은 질량유량을 확인.
6. 상관식 경계: 층류/난류 정상값, 전이영역·Haaland 범위 밖·음수 거칠기/비물리 입력 거부.
7. R744 0.5 m: CoolProp 8.0.0의 단상 상태를 사용해 결정론, 비음수 압력손실,
   단조 압력감소, 단열 엔탈피 보존과 phase 유지를 확인. 이는 물성 정확도의 독립 검증이 아니다.

허용오차는 결과를 본 뒤 완화하지 않는다. 구현식 또는 검증 가정이 잘못되면 실패 원인을
고치거나 제한으로 기록한다.

## 계약 및 후속 단계

공통 계약 0.2.0의 `ThermoState`, `PropertyBackend`, units와 solver service 서명은 바꾸지
않는다. 점도와 `U'`는 P04 내부 typed 입력으로 명시하며 출처 없는 기본값을 두지 않는다.
이 입력 모델은 값과 단위만 전달하고 provenance 필드는 갖지 않으므로, 원 자료·선정 근거의
보존은 호출자와 실행 기록의 책임이다. 현재 상관식 registry는 Reynolds 수·상·상대거칠기만
검사한다. 음속 입력이 없어 Mach 수를 검증하지 않으므로 저속 조건 확인도 호출자 책임이며,
registry가 고 Mach 유효성까지 보장한다고 해석하지 않는다.
ACR-0001의 P-Q/T-Q·혼합물은 PENDING이고 범위 밖이다. P04가 완료돼도 Integration Gate 1을
자동 승인하지 않으며, P05는 별도 branch/PR에서 시작한다.
