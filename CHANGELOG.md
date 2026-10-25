# 변경 이력 (Changelog)

이 프로젝트의 모든 주요 변경 사항은 본 문서에 기록됩니다.
본 문서는 [Keep a Changelog](https://keepachangelog.com/ko/1.0.0/) 원칙 및 [Semantic Versioning](https://semver.org/lang/ko/) 표준을 준수합니다.

---

## [1.4.0] - 2026-10-25

### 추가 및 개선 (Added & Changed)
- **Streamlit + Plotly 올인원 실시간 모니터링 대시보드 구축 (`src/quant_ko/dashboard/`)**:
  - **전체 자산 변화 추이 & 보유 포트폴리오**: KIS API 실시간 연동 및 SQLite 오프라인 자동 복원 지원, 일별 총자산/예수금/주식평가액 시계열 차트 및 자산 배분 도넛/막대 차트 구현.
  - **10.5개년 단독 전략 시계열 & 벤치마크 상관관계 분석**: 2016.04~2026.10 2,579영업일 누적 자산 궤적(`1,000만` ➔ `5,161만 원`, `+416.17%`, CAGR `17.25%`), 언더워터 낙폭(MDD `-40.08%`), KOSPI(상관계수 `0.3375`) 및 KOSDAQ(상관계수 `0.4168`) 비교, 11개년 연도별 수익률 테이블 완비.
  - **실제 거래기록 (Orders 원장)**: 환경(`MOCK/REAL`), 매매구분(`BUY/SELL`), 체결상태(`ORDERED/FILLED/FAILED/DRY_RUN`) 3중 필터링 및 원클릭 UTF-8-SIG CSV 다운로드 제공.
  - **전략 명세 (Strategy Spec)**: Order B 후절삭 유니버스, 9대 팩터 공식, 실전 계절성(5~10월 `357870` 파킹) vs 모의 상시보유 및 08:30 비상 손절 감시 규칙 집대성.
  - **고도화 편의 기능**: 차기 리밸런싱 카운트다운 타이머(D-Day/시간/분), 보유 종목 긴급 리스크 진단 카드(관리/환기/자본잠식/고부채), Top 20 팩터 밸런스 산점도, 프라이버시 금액 마스킹 모드 탑재.
- **소형주 유니버스 정합성 및 백테스트 알고리즘 개선 (`src/quant_ko/strategy/universe.py`)**:
  - **Order B 후절삭 확립**: 재무 건전성 및 TTM 흑자 필터를 선적용 후 시가총액 하위 20%를 후절삭하여 퀀터스 추출 기준과 정합성 확보.
  - **필터 파라미터 유연화**: `max_debt_ratio`(부채비율 200% 상한) 및 `require_quarter_profit`(단일분기 흑자) 기본값 해제(`None`/`False`).
  - **소형주 시총 이중절삭 버그 수정**: 사전 절삭된 시세 데이터와 원시 시세를 구분하여 시총 하위 20% 이중 필터링 결함 원천 차단.
- **데이터 적재 파이프라인 완성 (`data/quant_ko.db`)**:
  - 소형주 과거 일봉 시세 55만 건 및 DART 재무제표 6,128건, `fnlttSinglAcntAll` 매출총이익 774건 누락 없이 전건 적재 완료.
- **테스트 스위트 확장**: 총 116개 테스트 전원 통과 (All-Green, 100%).

---

## [1.3.2] - 2026-10-20

### 추가 및 개선 (Added & Changed)
- **KIS OAuth 토큰 만료 자동 복구 (`src/quant_ko/broker/kis.py`, `tests/test_kis.py`)**:
  - API 호출 도중 HTTP 401 또는 토큰 만료 에러 코드(`EGW00121`, `EGW00122`, `EGW00123`) 감지 시 캐시를 즉시 파기하고 신규 토큰을 강제 재발급(`force_refresh=True`)받아 1회 투명하게 자동 재시도하는 회복탄력성 구축.
- **로드맵 정비 (`TODO.md`, `PRD.md`)**:
  - 별도 레포지토리로 분리된 미국장 항목 제거 및 심플 모니터링 대시보드 과제 등록.

---

## [1.3.1] - 2026-10-19

### 수정 및 개선 (Fixed & Changed)
- **일일 감시 봇 안정화 (`src/quant_ko/main.py`, `src/quant_ko/live/monitor.py`)**:
  - `main.py` 감시 모드 실행 시 `KrxClient` 인자 불일치(TypeError) 수정.
  - `monitor.py` KRX 실시간 공시 동기화 데이터프레임/리스트 호환성 보완.
- **Git 브랜치 보호 정책 및 훅 체계 정립 (`.githooks/`, `rules/git-workflow.md`, `GEMINI.md`)**:
  - `dev` 브랜치 원격(`origin/dev`) 푸시 물리적 원천 차단.
  - `main` 브랜치 머지 및 원격 푸시 명시적 사용자 채팅 승인제 확립.
  - 복잡한 로컬 토큰 파일 검사 방식 전면 폐지.
- **문서 정비 (`PRD.md`, `TODO.md`)**:
  - 불필요한 배포 가이드 문서 제거 및 크론탭 동기화 타깃 `main` 브랜치로 통일.

---

## [1.3.0] - 2026-10-17

### 추가 및 개선 (Added & Changed)
- **실전 리밸런싱 직전 영업일 PIT 자동 연동 (`src/quant_ko/live/rebalancer.py`)**:
  - `pit_date` 미전달 시 `store.get_trading_days()` 기반 직전 영업일(`prior_trading_day`) 자동 산출 주입으로 미래참조 결함 원천 차단.
- **08:30 일일 감시 봇 모닝 생존 확인(Heartbeat) 및 실시간 공시 선제 동기화 (`src/quant_ko/live/monitor.py`)**:
  - 평일 08:30 정상 가동 확인 모닝 브리핑 전송 (`--no-heartbeat` 플래그 지원).
  - KRX OpenAPI 실시간 관리/환기종목 공시 선제 동기화 및 시장가(`01`) 긴급 청산 지원.
- **리밸런싱 전일(D-1) 18:00 사전 브리핑 도입 (`src/quant_ko/live/rebalancer.py`)**:
  - 리밸런싱 D-1일 18:00 예정 타깃 20종목, 현재 잔고, 교체 예정 내역 사전 예고 알림 (`--mode preview` 연동).
- **계절성 파킹 판정 단일 소스화 (`src/quant_ko/strategy/universe.py`)**:
  - `PARKING_MONTHS` 및 `is_seasonality_parking_period()` 공통 유틸리티 모듈화 및 전역 적용.
- **오라클 VM 3대 무인 크론탭 스케줄 반영 (`.github/workflows/deploy.yml`, `docs/oci_deployment_guide.md`)**:
  - 08:30 감시, 15:20 매매, 18:00 D-1 브리핑 자동 최신화 파이프라인 정립.
- **테스트 스위트 확장**: 총 100개 테스트 전원 통과 (All-Green, 100%).

---

## [1.2.0] - 2026-10-16

### 추가 및 변경 (Added & Changed)
- **운용 환경별 전략 모드 명세 영구 반영 (`PRD.md`)**:
  - 모의투자(`MOCK`): 계절성 파킹 없이 365일 연중 소형주 20종목 표준 모드(`--strategy standard`)로 상시 검증.
  - 실전투자(`REAL`): 계절성 모드(`--strategy seasonality`, 11\~4월 소형주 20종목 동일비중 / 5\~10월 CD금리 ETF `357870` 100% 파킹).
  - 공통 규칙: 매월 마지막 영업일 리밸런싱, 거래대금 필터 제외 (0원).
- **무인 자동 배포 및 CI 파이프라인 구축**:
  - GitHub Actions CI 워크플로우 추가 (`.github/workflows/ci.yml`): 푸시 시 자동 테스트 및 린트 검증.
  - 오라클 서버 크론탭 실행 직전 `git pull origin dev` 자동 최신화 파이프라인 구축.
- **버그 수정 (Fixed)**:
  - 한국거래소(KRX) 단축 지정종목 명칭(`관리`, `투자주의환기`) 긴급 청산 정상 매칭 지원 (`src/quant_ko/live/monitor.py`).
  - 첫 거래일이 월말일 경우 캘린더 인덱스 누락 방지 (`src/quant_ko/backtest/calendar.py`).
- **테스트 스위트**: 94개 테스트 전원 통과 (All-Green, 100%).

---

## [1.1.1] - 2026-10-16

### 추가 및 개선 (Added & Changed)
- **디스코드 리밸런싱 종합 상세 리포트 도입 (`src/quant_ko/live/rebalancer.py`)**:
  - 타깃 포트폴리오 선정 종목명(티커) 및 목표 비중(%) 표시.
  - 매도/매수 체결 상세(종목명, 티커, 수량, 단가, 총액) 및 주문 실패/거절 사유(`[매수]`/`[매도]` 라벨, 예수금 부족 스킵 포함) 상세 출력.
  - Discord Embed 필드당 1,024자 초과 방지 자동 분할(`_chunk_field_lines`) 및 저수준 시스템 예외 정제 적용.
- **오라클 클라우드(OCI) 무인 자동매매 배포 가이드 작성 (`docs/oci_deployment_guide.md`)**:
  - 서버 접속, 초기 세팅, DB/환경변수 전송 및 크론탭 등록 단계별 매뉴얼 추가.
- **테스트 스위트 확장**:
  - 상세 리포트, 예수금 부족 스킵, 예외 정제 및 청킹 단위 테스트 5건 추가 (총 93개 테스트 All-Green).

---

## [1.1.0] - 2026-10-14

### 추가 (Added)
- **KIS API 일시적 오류 대비 Exponential Backoff (최대 3회 지연 재시도) 구축**:
  - 네트워크 단절 및 5xx 서버 오류 발생 시 1초·2초·4초 지수 백오프로 안정성 확보.
- **오라클 클라우드 프리티어(OCI Always Free) 24/365 무인 배포 가이드 ([`TODO.md`](TODO.md))**:
  - 로컬 PC 전원 의존 탈피 및 리눅스 크론탭(`crontab`) 기반 무인 자동화 절차 수립.
- **모의투자 실시간 체결 검증**:
  - 9대 팩터 소형주 실시간 시장가 매수 주문 전송 및 체결 완료 (에스앤더블류, 케이피티유).

### 수정 및 개선 (Changed & Fixed)
- **KIS 증권사 API 파라미터 및 응답 파싱 정밀화**:
  - 잔고 조회 시간외 단일가 파라미터 수정 (`AFHR_FLG` ➔ `AFHR_FLPR_YN`).
  - 보유 종목 수량 필드명 정정 (`hld_qty` ➔ `hldg_qty`).
  - 일별 주문체결 조회 파라미터 추가 (`INQR_DVSN_3="00"`, `INQR_DVSN_1=""`).
- **증권사 Rate Limit 보호**:
  - 실전/모의 주문 전송 간 0.5초 안전 지연(`time.sleep(0.5)`) 적용.
- **소액 시드 단주 최소화**:
  - 파킹 ETF를 고가(107만 원) 대신 1주 약 53,000원인 TIGER CD금리(`357870`)로 기본값 교체.
- **디스코드 알림 고도화**:
  - 성공 주문(매수/매도)과 실패 주문(거절 종목명 표기)을 분리 집계하여 투명성 강화.
- **테스트 스위트 확장**:
  - KIS 재시도 및 계절성 파킹 검증 테스트 추가 (총 88개 전원 통과 All-Green).

---

## [1.0.0] - 2026-10-10

### 추가 (Added)
- **통합 운영 CLI 및 실행기 (`src/quant_ko/main.py`)**:
  - `python -m quant_ko.main --mode status`: 계좌 잔고, 보유 종목, 현재 계절성 운용 상태(주식 투자기 vs CD금리 파킹기) 원클릭 조회.
  - `python -m quant_ko.main --mode rebalance [--dry-run]`: 월별 리밸런싱 실행 및 가상 20종목 수량 계산 Dry-Run 모드.
  - `python -m quant_ko.main --mode monitor`: 보유 종목 관리종목/환기종목 비상 손절 감시 봇.
- **Windows 작업 스케줄러 자동 등록 스크립트 (`scripts/setup_windows_scheduler.ps1`)**:
  - 매월 말일 15:20 리밸런싱(`QuantKo-MonthlyRebalance`) 및 평일 08:30 모니터링(`QuantKo-DailyMonitor`) 자동 등록.
- **한국투자증권(KIS) 브로커 연동 (`src/quant_ko/broker/kis.py`)**:
  - 실전/모의 듀얼 API 키 및 계좌 분리 지원 (`KIS_MODE=MOCK` / `REAL`).
  - OAuth 토큰 디스크 영구 캐싱 및 자동 갱신.
  - 잔고 조회, 실시간 시세, 지정가 차이분 주문, 체결 내역 조회.
- **디스코드 웹훅 알림 (`src/quant_ko/notify/discord.py`)**:
  - 리밸런싱 체결 내역 및 비상 모니터링 알림 전송.
- **Point-in-Time(PIT) 및 9대 팩터 엔진 (`src/quant_ko/pit/`, `src/quant_ko/strategy/`)**:
  - 공시접수일(`rcept_dt <= as_of_date`) 기반 미래참조 편향 0% 스냅샷 빌더.
  - 시총 하위 20%, 부채비율 ≤ 200%, 자본잠식률 ≤ 0%, 연속 흑자 필터링.
  - 시가총액 + 4대 밸류(PER, PSR, POR, PGPR) + 4대 성장률(매출, 총익, 영업익, 순익 YoY) 순위 합산 모델.
- **10.5개년 장기 백테스트 엔진 및 비교 분석 리포트 (`docs/`, `scripts/`)**:
  - 2016.04 \~ 2026.10 4대 모멘텀 전략 및 코스피/코스닥 비교 백테스트 완료.
  - **1위 전략 확정: 계절성 필터 (11-4월 주식, 5-10월 CD금리 ETF)**: 누적 +416.17%, CAGR 16.89%, MDD -40.08%, 샤프 0.83.
  - 고해상도 비교 차트(PNG) 및 인터랙티브 웹 대시보드(HTML) 생성.
- **대용량 데이터 수집 및 SQLite 스토리지 (`src/quant_ko/data/`)**:
  - DART 일괄 조회 API(`fnlttMultiAcnt.json`) 고속 수집 러너: 16,127건 재무제표 적재.
  - KRX/FDR 일별 시세 1,093,824건 적재 (2015-01-02 \~ 2026-10-08 전 기간).
- **테스트 & 품질 스위트**:
  - 단위 및 통합 테스트 84개 전원 통과 (All-Green).
  - Ruff 린터 및 포맷터 무경고 (0 warnings).
