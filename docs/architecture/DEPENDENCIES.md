# P00 의존성 및 라이선스 기록

검증 환경: Windows, Python 3.12.14, uv 0.12.11. 정확한 전이 의존성/해시는 uv.lock에 저장한다. 설치된 배포 metadata를 조회하여 다음 항목을 확인했다.

| 직접 의존성 | 잠긴 버전 | metadata 라이선스 | 용도 |
|---|---|---|---|
| pydantic | 2.13.5 | MIT | 공통 데이터 검증 |
| pint | 0.25.3 | BSD | 단위 정규화 |
| hatchling | 1.32.0 | MIT | 빌드 |
| pytest | 9.1.1 | MIT | 테스트 |
| ruff | 0.16.6 | MIT | 정적 검사·서식 |
| mypy | 1.20.2 | MIT | 타입 검사 |

hatchling도 dev group에 넣어 lock에 포함하고 `uv build --no-build-isolation`으로 잠긴 개발 환경에서 빌드한다. runtime 설치에는 검사/빌드 도구가 필요 없다. Python 지원 범위는 검증한 3.12로 제한하며 새 minor 버전은 호환성 검증 후 확장한다.

이 목록은 전체 법적 검토를 의미하지 않는다. 실제 재배포 시 설치 artifact의 원문 LICENSE/NOTICE를 보존하고 전이 의존성도 확인한다. 프로젝트 자체 배포 라이선스와 실제 제조사 자료 배포 권한은 아직 결정되지 않았다.

CoolProp/TESPy/ACHP/OpenAI SDK 및 GUI/최적화/Excel 라이브러리는 P00에서 설치하지 않았다. 해당 단계에서 license와 compatibility 증거를 남기고 lockfile을 갱신한다.

## P01 WS-A 추가

| 구분 | 잠긴 버전 | 배포 metadata 라이선스 | Python | 용도와 위험 |
|---|---:|---|---|---|
| CoolProp (직접) | 8.0.0 | MIT | >=3.9 | PropertyBackend 구현. compiled wheel과 EOS/reference-state 재현성을 관리한다. |
| NumPy (전이) | 2.5.3 | 복합 SPDX: BSD-3-Clause 등 | >=3.12 | CoolProp 8의 필수 전이 의존성. 수치 stack 충돌과 wheel 지원을 CI에서 확인한다. |

Windows CPython 3.12에서 공식 uv lock, 설치, 리뷰 보완 후 전체 100개 테스트와
build를 검증했다.
CoolProp 8.0.0 lock에는 CPython 3.12 abi3 Windows와 manylinux x86_64/aarch64
wheel 및 hash가 포함된다. GitHub Actions run 34550350191에서 Ubuntu와 Windows
설치·테스트가 모두 통과했다. P01은 CoolProp 버전과 기본 reference state를
고정하며 실행 중 전역 reference state를 변경하지 않는다. 이 기록은 라이선스
법률 검토를 대신하지 않는다.

## P03 WS-A 추가

| 구분 | 잠긴 버전 | 배포 metadata 라이선스 | Python | 용도와 위험 |
|---|---:|---|---|---|
| TESPy (직접) | 0.11.2 | MIT | >=3.11 | P02 R744 cycle을 별도 network equation 경로로 교차검증한다. TESPy도 CoolProp을 사용하므로 독립 물성 정확도 검증은 아니다. |
| SciPy (전이) | 1.18.1 | BSD-3-Clause 계열, binary bundle 별도 고지 포함 | >=3.12 | TESPy 비선형 방정식 풀이. 플랫폼별 수치 차이를 고정 tolerance와 양쪽 CI로 관리한다. |
| Matplotlib (전이) | 3.11.2 | PSF 기반 | >=3.11 | TESPy 필수 전이 의존성. P03 실행 경로에서 직접 plotting은 하지 않는다. |
| pandas (전이) | 3.0.5 | BSD-3-Clause | >=3.11 | TESPy 결과 자료 구조 지원. |
| fluprodia (전이) | 4.3 | MIT | >=3.9 | TESPy diagram 관련 전이 의존성. P03에서 직접 사용하지 않는다. |
| tabulate (전이) | 0.10.0 | MIT | >=3.9 | TESPy 표 출력 지원. |
| Jinja2 (전이) | 3.1.6 | BSD-3-Clause | >=3.7 | TESPy 템플릿 지원. |

TESPy 도입으로 기존 허용 범위 안에서 Pint가 0.25.3에서 0.26.1로 재해결되었으며,
CoolProp 8.0.0과 NumPy 2.5.3은 유지되었다. 정확한 artifact URL과 hash를 포함한 전체
전이 의존성은 `uv.lock`에 고정한다. Windows Python 3.12에서 TESPy 0.11.2 설치와 P03
수치 비교를 확인하고, Windows/Ubuntu CI를 PR에서 다시 확인한다. 이 표는 재현성 기록이며
전체 법적 검토를 대신하지 않는다.
