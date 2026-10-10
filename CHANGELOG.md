# 변경 이력 (Changelog)

이 프로젝트의 모든 주요 변경 사항은 본 문서에 기록됩니다.
본 문서는 [Keep a Changelog](https://keepachangelog.com/ko/1.0.0/) 원칙 및 [Semantic Versioning](https://semver.org/lang/ko/) 표준을 준수합니다.

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
