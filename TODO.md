# 작업 큐 & 진행 상황 (TODO.md)

## 🏃 진행 중 (In Progress)
- [ ] 실계좌 투입 전 최종 모의투자 가동 및 스케줄러 등록 모니터링

## 📋 다음 할 일 (Next Up)

### [Phase 5] 20년 장기 과거 데이터 확보 및 과거 금융위기 국면 검증
- [ ] 2005-2014 상용 데이터(FnGuide/KIS-Value 등) 및 코스닥 지수 20개년 데이터 확보 (DART API는 2015년 이후만 정형 재무제표 제공)
- [ ] 2008 금융위기, 2020 코로나 등 국면별 MDD 방어력 장기 검증

---

## ✅ 완료됨 (Done)
- [x] 투자 전략 인터뷰 (/grill-me Q1~Q12) 완료
- [x] [PRD.md](PRD.md) 명세서 작성 및 요구사항 확정
- [x] 프로젝트 문서 구조 초기화 (TODO, README, CHANGELOG, .gitignore)
- [x] **Phase 1: 기반 설정 & 데이터 파이프라인**
  - [x] OpenDART API 클라이언트 및 재무제표 수집 (16,127건 적재)
  - [x] KRX 가격, 시가총액, 거래대금, 상폐 종목 및 제외 필터 태깅 모듈 (109만 건 적재)
  - [x] SQLite 로컬 DB 스키마 생성 및 데이터 증분 적재 파이프라인 (`src/quant_ko/data/store.py`)
- [x] **Phase 2: Point-in-Time (PIT) & 팩터 스코어링 엔진**
  - [x] 공시접수일 기준 PIT 재무 스냅샷 빌더 (TTM 및 분기 YoY, 4분기 역산) (`src/quant_ko/pit/builder.py`)
  - [x] 유니버스 필터 (제외 필터 ➔ 시총 하위 20% ➔ 유동성/재무 흑자 필터) (`src/quant_ko/strategy/universe.py`)
  - [x] 9대 팩터 스코어링 및 랭킹 정렬 모듈 (흑자전환 최상위 처리) (`src/quant_ko/strategy/scoring.py`)
- [x] **Phase 3: 백테스트 시뮬레이터 & 성과 검증**
  - [x] 분기/월별 리밸런싱 백테스트 엔진 (차이분 매매, 비용 0.3%, 비상 청산) (`src/quant_ko/backtest/engine.py`)
  - [x] 10.5개년(2016.04~2026.10) 백테스트 및 4대 전략 비교 검증 (계절성 1위: 수익률 +416.17%, CAGR 16.89%, 샤프 0.83)
  - [x] 백테스트 시각화 대시보드 및 인터랙티브 차트 생성 (`scripts/generate_charts.py`)
- [x] **Phase 4: 한국투자증권(KIS) 연동 & 자동매매 실전화**
  - [x] KIS Open API 클라이언트 (OAuth 토큰 자동 갱신, 잔고/주문/체결 조회, 모의/실전 모드)
  - [x] 15:20 장마감 시장가(`01`) 100% 즉시 체결 주문 연동 (`ORD_DVSN="01"`, `ORD_UNPR="0"`)
  - [x] 소액 시드(200만~1,000만 원) 단주 최소화를 위한 파킹 ETF를 TIGER CD금리(`357870`)로 확정
  - [x] 매수 수량 산출 시 0.3% 수수료 버퍼(`cost_rate`) 반영으로 주문 거부 방지
  - [x] 일일 관리종목/환기종목 감시 및 익일 시초가 비상 청산 봇 (`src/quant_ko/live/monitor.py`)
  - [x] 디스코드 웹훅 알림 연동 (`src/quant_ko/notify/discord.py`)
  - [x] 통합 운영 CLI (`quant_ko.main`: status, rebalance, monitor)
  - [x] 윈도우 작업 스케줄러 자동 등록 스크립트 (`scripts/setup_windows_scheduler.ps1`)
- [x] **품질 검증 & 코드리뷰**
  - [x] 단위/통합 테스트 85개 전원 통과 (All-Green)
  - [x] Ruff 린트/포맷터 0 errors / 0 warnings 완벽 준수
  - [x] Standards & Spec 2축 코드리뷰 및 리팩터링 완료
