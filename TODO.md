# 작업 큐 & 진행 상황 (TODO.md)

## 🏃 진행 중 (In Progress)
- [ ] 실계좌 투입 전 KIS 모의투자 가동 및 윈도우 스케줄러 정상 동작 모니터링

## 📋 다음 할 일 (Next Up)

### 🚀 실전 운영 안정화 & 고도화 과제
- [ ] **리밸런싱 전일 사전 알림**: 리밸런싱 D-1일 18:00에 예정 타깃 20종목 및 예상 주문 수량을 디스코드로 사전 브리핑
- [ ] **KIS 토큰 만료 자동 복구**: 장중 실행 직전 토큰 유효성 선제 검증 및 강제 갱신 옵션
- [ ] **일일 스케줄러 생존 확인(Heartbeat)**: 장 시작 전(08:30) 봇 상태 정상 동작 여부를 디스코드로 1줄 핑 전송

### ☁️ 오라클 클라우드 프리티어(OCI Always Free) 무인 배포 가이드
> **목적**: 로컬 PC 전원 의존(15:20 PC 켜두기)을 완전히 없애고, 24시간 365일 무인 자동매매/모니터링 구현.  
> **특징**: 상시 구동 웹서버가 아니라 평일 08:30과 15:20에 1초씩만 실행되는 초경량 배치(RAM 50MB 미만)이므로 기존 OCI 서비스에 부하 0.

- [ ] **1. 서버 기본 환경 셋업**:
  - 한국 시간대(KST) 동기화: `sudo timedatectl set-timezone Asia/Seoul`
  - 리포지토리 클론: `git clone -b dev https://github.com/haksoo0918/quant-ko.git`
  - 가상환경 및 의존성 설치:
    ```bash
    cd quant-ko
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -e .
    ```
- [ ] **2. 환경변수 및 데이터베이스 파일 복사**:
  - `.env` 파일 복사: 모의투자 키(`KIS_MOCK_*`), 디스코드 웹훅(`DISCORD_WEBHOOK_URL`) 포함
  - DB 파일 복사: 로컬의 `data/quant_ko.db`를 서버 `quant-ko/data/quant_ko.db`로 전송 (`scp data/quant_ko.db ubuntu@<OCI_IP>:~/quant-ko/data/`)
- [ ] **3. 계좌 연동 수동 1회 검증**:
  - `python -m quant_ko.main --mode status --env mock` 실행하여 예수금 1,000만 원 및 KIS API 정상 응답 확인
- [ ] **4. 리눅스 크론탭(`crontab -e`) 2줄 스케줄 등록**:
  ```cron
  # [quant-ko] 평일 08:30 일일 관리종목/환기종목 비상 모니터링
  30 08 * * 1-5 cd /home/ubuntu/quant-ko && .venv/bin/python -m quant_ko.main --mode monitor --env mock >> /home/ubuntu/quant-ko/monitor.log 2>&1

  # [quant-ko] 평일 15:20 장마감 시장가 리밸런싱 자동 주문
  20 15 * * 1-5 cd /home/ubuntu/quant-ko && .venv/bin/python -m quant_ko.main --mode rebalance --env mock >> /home/ubuntu/quant-ko/rebalance.log 2>&1
  ```

### [Phase 5] 20년 장기 과거 데이터 확보 및 과거 금융위기 국면 검증
- [ ] 2005-2014 상용 데이터(FnGuide/KIS-Value 등) 및 코스닥 지수 20개년 데이터 확보 (DART API는 2015년 이후만 정형 재무제표 제공)
- [ ] 2008 금융위기, 2020 코로나 등 국면별 MDD 방어력 장기 검증

### [Phase 6] 미국장(US) 소형주 성장 가치 퀀트 전략 확장 (로드맵 & 아키텍처 설계)
> **사용자 요구**: 운용 자산 규모 확대 시 동일 전략(소형주 성장 가치 팩터 + 계절성/모멘텀 필터)을 미국 주식 시장으로 확장 적용.  
> **아키텍처 결정**: **독립 프로젝트 분리 (`quant-us`) 또는 모노레포 하위 패키지 분리 강력 권장**

- **프로젝트 분리 권장 사유 (한국장 vs 미국장 이질성 분석)**:
  1. **데이터 소스 체계가 다름**:
     - 한국: OpenDART (XML/정형 XBRL 12월 결산 중심) + KRX 일별 시세.
     - 미국: SEC EDGAR (10-K 연간, 10-Q 분기 보고서, 기업별 결산월 분산) + FMP / Polygon / Tiingo API.
  2. **거래 인프라 및 운영 시간 이질성**:
     - 한국: 원화 계좌, 평일 15:20 장마감 시장가, 윈도우 스케줄러 주간 가동.
     - 미국: 달러 환전/외화 예수금, 한국 시간 야간(23:30~06:00, 서머타임 22:30~05:00), KIS 해외주식 또는 Alpaca/Interactive Brokers(IBKR) API 사용.
  3. **세제 및 결제 주기**:
     - 한국: 국내 주식 매매차익 비과세(거래세 중심).
     - 미국: 연 250만 원 공제 후 양도소득세 22% 분리과세 (연말 절세 리밸런싱 로직 별도 필요), T+1 결제.
  4. **재사용 가능한 공통 자산**:
     - 9대 팩터 모델(시총 하위 20%, PER/PSR/POR/PGPR + YoY 성장 순위 모델)의 수학적 알고리즘과 백테스트 엔진 구조는 100% 동일하게 이식 가능.
- **향후 구현 체크리스트 (미국장 진입 시)**:
  - [ ] 신규 프로젝트 `quant-us` 생성 (또는 `packages/quant-us` 분리)
  - [ ] SEC EDGAR / Financial Modeling Prep (FMP) 재무 파이프라인 구축
  - [ ] Russell 2000 소형주 유니버스 필터 및 9대 팩터 스코어링 모듈 구현
  - [ ] 11~4월 소형주 20종목 / 5~10월 미국 초단기 국채 ETF(SGOV, BIL 등) 파킹 백테스트 검증
  - [ ] KIS 해외주식 또는 Alpaca API 야간 자동매매 스케줄러 구축

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
  - [x] KIS API 일시적 통신 오류 대비 Exponential Backoff (최대 3회 지연 재시도) 로직 구축
  - [x] 15:20 장마감 시장가(`01`) 100% 즉시 체결 주문 연동 (`ORD_DVSN="01"`, `ORD_UNPR="0"`)
  - [x] 소액 시드(200만~1,000만 원) 단주 최소화를 위한 파킹 ETF를 TIGER CD금리(`357870`)로 확정
  - [x] 매수 수량 산출 시 0.3% 수수료 버퍼(`cost_rate`) 반영으로 주문 거부 방지
  - [x] 일일 관리종목/환기종목 감시 및 익일 시초가 비상 청산 봇 (`src/quant_ko/live/monitor.py`)
  - [x] 디스코드 웹훅 알림 연동 (`src/quant_ko/notify/discord.py`)
  - [x] 통합 운영 CLI (`quant_ko.main`: status, rebalance, monitor)
  - [x] 윈도우 작업 스케줄러 자동 등록 스크립트 (`scripts/setup_windows_scheduler.ps1`)
- [x] **품질 검증 & 코드리뷰**
  - [x] 단위/통합 테스트 88개 전원 통과 (All-Green)
  - [x] Ruff 린트/포맷터 0 errors / 0 warnings 완벽 준수
  - [x] Standards & Spec 2축 코드리뷰 및 권장사항(지연 재시도 로직) 구현 완료
