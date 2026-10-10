# Quant-KO: 소형주 성장 가치 퀀트 자동매매 시스템

국내 코스피·코스닥 시가총액 하위 20% 소형주 중, 재무 건전성과 이익 성장률, 저평가 지표가 우수한 20개 종목을 발굴하여 운용하는 퀀트 투자 및 한국투자증권(KIS) 자동매매 시스템입니다.

---

## 📌 주요 특징

1. **철저한 편향 제거 (Point-in-Time)**
   - OpenDART 실제 공시접수일(`rcept_dt`) 기준 데이터 반영 (미래참조 편향 0%)
   - 상장폐지 종목 및 관리/환기 종목 이력 반영 (생존 편향 제거)
2. **소형주 성장 가치 9대 팩터 모델**
   - **유니버스 필터**: 코스피/코스닥 보통주, 12월 결산법인 대상 (금융/지주/스팩/우선주/관리/중국계 제외)
   - **시총 필터**: 제외 필터 통과 종목 중 시가총액 하위 20%
   - **건전성 & 유동성**: 부채비율 ≤ 200%, 자본잠식률 ≤ 0%
   - **이익 기준**: 최근 분기 및 TTM 영업이익/지배주주순이익 > 0
   - **스코어링**: 시가총액(1) + 밸류 4종(PER, PSR, POR, PGPR) + 성장률 4종(순이익, 영업익, 총이익, 매출액 YoY)
3. **10.5개년 검증 1위: 계절성 필터 (11-4월 주식, 5-10월 CD금리 ETF)**
   - **누적 수익률**: **+416.17%** (원금 1,000만 원 → **5,161만 원**, 5.1배 달성)
   - **연복리 수익률(CAGR)**: **16.89%** (코스피 12.36%, 코스닥 1.66% 압도)
   - **최대 낙폭(MDD)**: **-40.08%** (코스피 -43.90%, 코스닥 -53.79% 대비 우수한 하락장 방어)
   - **샤프 지수**: **0.83** (코스피 0.38의 2.2배)
   - **연간 승률**: **81.8%** (11개년 중 9개년 플러스 마감)
4. **한국투자증권 KIS Open API 연동 및 자동화**
   - 모의투자/실전투자 듀얼 분리 지원 (`KIS_MODE=MOCK` / `REAL`)
   - 장마감 동시호가(15:20) 지정가 차이분 매매 및 Dry-Run 모의 실행 지원
   - 디스코드 실시간 체결 및 일일 안전 감시 알림
   - Windows 작업 스케줄러 원클릭 자동 등록

---

## 🏗️ 시스템 아키텍처

```text
src/quant_ko/
  ├── data/        # OpenDART, KRX 수집기 및 SQLite 저장소 (109만 건 주가, 1.6만 건 재무)
  ├── pit/         # 공시접수일 기준 Point-in-Time 재무 스냅샷 빌더
  ├── strategy/    # 유니버스 필터, 9대 팩터 스코어링 및 포트폴리오 산출
  ├── backtest/    # 10.5개년 백테스트 엔진, 거래비용 및 성과 리포터
  ├── broker/      # 한국투자증권 KIS Open API 연동 모듈 (모의/실전)
  ├── live/        # 월별 리밸런서, 일일 모니터링 봇, Dry-Run 실행기
  ├── notify/      # 디스코드 웹훅 알림 모듈
  └── main.py      # 통합 운영 CLI 엔트리포인트
```

---

## 🚀 빠른 시작

### 1. 환경 설정
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

### 2. 환경 변수 설정
`.env.example`을 복사하여 `.env`를 생성하고 API 키를 입력합니다.
```env
OPENDART_API_KEY=your_dart_api_key

# 한국투자증권 실전/모의 계좌 설정
KIS_MODE=MOCK  # MOCK(모의투자) 또는 REAL(실전)

# 모의투자 설정
KIS_MOCK_APP_KEY=your_mock_app_key
KIS_MOCK_APP_SECRET=your_mock_app_secret
KIS_MOCK_CANO=your_mock_account_number
KIS_MOCK_ACNT_PRDT_CD=01

# 실전투자 설정
KIS_REAL_APP_KEY=your_real_app_key
KIS_REAL_APP_SECRET=your_real_app_secret
KIS_REAL_CANO=your_real_account_number
KIS_REAL_ACNT_PRDT_CD=01

DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

### 3. 실전 / 모의 운영 CLI 명령어
```powershell
# 1. 현재 계좌 잔고 및 전략 상태 확인
python -m quant_ko.main --mode status --env mock

# 2. 리밸런싱 가상 모의 실행 (주문 전송 없이 20종목 수량 계산 검증)
python -m quant_ko.main --mode rebalance --dry-run

# 3. 실전 리밸런싱 실행 (매월 말일 15:20)
python -m quant_ko.main --mode rebalance

# 4. 일일 관리종목/환기종목 비상 감시 (평일 08:30)
python -m quant_ko.main --mode monitor
```

### 4. Windows 작업 스케줄러 자동 등록
PowerShell(관리자 권한 권장)에서 다음 스크립트를 1회 실행하면 자동 등록됩니다:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_windows_scheduler.ps1
```

---

## 📖 문서 및 백테스트 리포트 링크
- [PRD (제품 요구사항 정의서)](PRD.md)
- [10.5개년 모멘텀 필터 전략 비교 리포트](docs/momentum_filters_10year_backtest_result.md)
- [전략 1 vs 코스피/코스닥 비교 리포트](docs/seasonality_vs_kospi_backtest_result.md)
- [성과 비교 차트 이미지](docs/charts/backtest_comparison_chart.png)
- [인터랙티브 웹 대시보드 (HTML)](docs/charts/backtest_dashboard.html)
- [변경 이력](CHANGELOG.md)
