# 변경 이력 (Changelog)

이 프로젝트의 모든 주요 변경 사항은 본 문서에 기록됩니다.
본 문서는 [Keep a Changelog](https://keepachangelog.com/ko/1.0.0/) 원칙 및 [Semantic Versioning](https://semver.org/lang/ko/) 표준을 준수합니다.

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
  - 2016.04 ~ 2026.10 4대 모멘텀 전략 및 코스피/코스닥 비교 백테스트 완료.
  - **1위 전략 확정: 계절성 필터 (11-4월 주식, 5-10월 CD금리 ETF)**: 누적 +416.17%, CAGR 16.89%, MDD -40.08%, 샤프 0.83.
  - 고해상도 비교 차트(PNG) 및 인터랙티브 웹 대시보드(HTML) 생성.
- **대용량 데이터 수집 및 SQLite 스토리지 (`src/quant_ko/data/`)**:
  - DART 일괄 조회 API(`fnlttMultiAcnt.json`) 고속 수집 러너: 16,127건 재무제표 적재.
  - KRX/FDR 일별 시세 1,093,824건 적재 (2015-01-02 ~ 2026-10-08 전 기간).
- **테스트 & 품질 스위트**:
  - 단위 및 통합 테스트 84개 전원 통과 (All-Green).
  - Ruff 린터 및 포맷터 무경고 (0 warnings).
