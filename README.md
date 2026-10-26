# Quant-KO: 소형주 성장·가치 퀀트 자동매매 시스템

국내 코스피·코스닥 상장사 중 재무 건전성 및 흑자 필터를 통과한 우량 모수에서 **시가총액 하위 20% 소형주(`Order B` 후절삭)**를 선별하고, 밸류(4종)와 성장성(4종) 및 시가총액을 결합한 **9대 멀티팩터 모델**로 상위 20개 종목을 매월 자동 매매하는 한국투자증권(KIS) 퀀트 트레이딩 시스템입니다.

---

## 📌 주요 특징

1. **철저한 편향 제거 (Point-in-Time & Survival Bias-Free)**
   - OpenDART 실제 공시접수일(`rcept_dt`) 기준 데이터 반영 (미래참조 편향 0%)
   - 상장폐지 종목 및 관리/환기 종목 이력 반영 (생존 편향 제거)
2. **Order B 후절삭 소형주 성장·가치 9대 팩터 모델**
   - **유니버스 대상**: 코스피·코스닥 보통주, 12월 결산법인 (코넥스/금융/지주/스팩/우선주/관리/중국계 제외)
   - **2차 재무 건전성 & 흑자 선필터**: TTM 영업이익 > 0, TTM 지배주주순이익 > 0, 자본잠식률 ≤ 0% (부채비율 상한 제한 없음, 분기흑자 강제 없음)
   - **3차 시총 후절삭 (Order B)**: 재무/흑자 필터를 통과한 우량 기업 모수 중에서 **시가총액 하위 20%** 소형주만 최종 유니버스로 절삭
   - **9대 팩터 스코어링**: 시가총액(1) + 밸류 4종(PER, PSR, POR, PGPR) + 성장 4종(매출액, 매출총이익, 영업이익, 지배주주순이익 YoY, 흑자전환 최우선) 합산 순위 상위 20종목 동일비중(각 5%) 편입
3. **10.5개년 검증: 계절성 필터 (11\~4월 주식 적극 투자, 5\~10월 CD금리 ETF 파킹)**
   - **누적 수익률**: **+416.17%** (원금 1,000만 원 → **5,161만 원**, 5.1배 달성)
   - **연복리 수익률(CAGR)**: **16.89%** (코스피 12.36%, 코스닥 1.66% 압도)
   - **최대 낙폭(MDD)**: **-40.08%** (코스피 -43.90%, 코스닥 -53.79% 대비 우수한 하락장 방어)
   - **KOSPI 상관계수**: **0.3375** (대형주/지수 하락장에 휩쓸리지 않는 강력한 시장 독립성 확보)
   - **연간 승률**: **81.8%** (11개년 중 9개년 플러스 마감)
4. **한국투자증권 KIS Open API 연동 및 24시간 무인 자동화**
   - 모의투자/실전투자 듀얼 분리 지원 (`KIS_MODE=MOCK` / `REAL`)
   - 장마감 동시호가(15:20) 시장가 차이분 매매 및 Dry-Run 모의 실행 지원
   - 평일 08:30 일일 관리/환기종목 비상 손절 감시 및 모닝 생존 확인(Heartbeat)
   - 리밸런싱 D-1일 18:00 예정 타깃 20종목 사전 브리핑 및 실시간 주문 체결 디스코드 상세 알림
   - 오라클 클라우드(OCI) Linux VM 24시간 크론탭 무인 자동화 가동
5. **Streamlit + Plotly 올인원 실시간 모니터링 대시보드**
   - 전체 자산 변화 추이 & 보유 포트폴리오 비중 실시간 시각화 (KIS API 연동)
   - 10.5개년 일별 누적 자산 궤적, 언더워터 낙폭(MDD), KOSPI/KOSDAQ 상관관계 및 연도별 수익률 비교
   - 실제 주문/체결 원장 3중 필터링 조회 및 CSV 내보내기
   - 차기 리밸런싱 카운트다운 타이머(D-Day/시간/분) 및 보유 종목 긴급 리스크 진단 카드
   - 실전 계좌 금액 마스킹 프라이버시 모드 지원

---

## 🏗️ 시스템 아키텍처

```text
src/quant_ko/
  ├── data/        # OpenDART, KRX 수집기 및 SQLite 저장소 (165만 건 주가, 2.5만 건 재무)
  ├── pit/         # 공시접수일 기준 Point-in-Time 재무 스냅샷 빌더
  ├── strategy/    # Order B 유니버스 필터, 9대 팩터 스코어링 및 포트폴리오 산출
  ├── backtest/    # 10.5개년 백테스트 엔진, 거래비용 및 성과 리포터
  ├── broker/      # 한국투자증권 KIS Open API 연동 모듈 (모의/실전, 토큰 자동갱신)
  ├── live/        # 월별 리밸런서, 일일 모니터링 봇, Dry-Run 실행기
  ├── dashboard/   # Streamlit + Plotly 올인원 실시간 모니터링 대시보드
  ├── notify/      # 디스코드 웹훅 알림 모듈
  └── main.py      # 통합 운영 CLI 엔트리포인트
```

---

## 🚀 빠른 시작

### 1. 가상환경 구성 및 패키지 설치
`uv`를 통해 최신 의존성을 초고속으로 동기화합니다:
```powershell
uv sync
```

### 2. 환경 변수 설정
`.env.example`을 복사하여 `.env`를 생성하고 API 키를 입력합니다.
```env
OPENDART_API_KEY=your_dart_api_key

# 한국투자증권 실전/모의 계좌 설정 (MOCK 또는 REAL)
KIS_MODE=MOCK

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

### 3. 모니터링 대시보드 실행
웹 브라우저(`http://localhost:8501`)에서 자산 변화 추이, 실시간 보유 잔고, 거래기록, 전략 명세를 확인합니다:
```powershell
uv run streamlit run src/quant_ko/dashboard/app.py
```

### 4. 실전 / 모의 운영 CLI 명령어
```powershell
# 1. 현재 계좌 잔고 및 전략 상태 확인
uv run python -m quant_ko.main --mode status

# 2. 리밸런싱 가상 모의 실행 (주문 전송 없이 20종목 수량 계산 및 로그 검증)
uv run python -m quant_ko.main --mode rebalance --dry-run

# 3. 실전 리밸런싱 실행 (매월 마지막 영업일 15:20)
uv run python -m quant_ko.main --mode rebalance

# 4. 일일 관리종목/환기종목 비상 감시 (평일 08:30)
uv run python -m quant_ko.main --mode monitor
```

---

## ⏰ 무인 자동화 스케줄 (OCI Linux VM 크론탭)

오라클 클라우드 프리티어(OCI) 리눅스 서버에서 다음과 같이 24시간 무인 가동 중입니다:

| 실행 시각 | 실행 모드 | 주요 동작 |
| :--- | :--- | :--- |
| **평일 08:30** | `monitor` | 보유 종목 관리/환기종목 지정 여부 감시 (적발 시 시장가 즉시 전량 청산) 및 모닝 생존 확인 브리핑 전송 |
| **매월 마지막 평일 D-1 18:00** | `rebalance --mode preview` | 차일 리밸런싱 예정 타깃 20종목 및 예수금 상태 사전 브리핑 |
| **매월 마지막 평일 15:20** | `rebalance` | 장마감 동시호가 시장가 차이분 주문 실행 및 결과 리포트 전송 (5\~10월 파킹기엔 `357870` ETF 매매) |

---

## 📖 문서 및 백테스트 리포트 링크

- [PRD (제품 요구사항 정의서)](PRD.md)
- [변경 이력 (CHANGELOG.md)](CHANGELOG.md)
- [대시보드 UI 감사 보고서](docs/dashboard_ui_audit.md)
- [소형주 유니버스 Order A vs B 백테스트 비교 리포트](docs/debt_ratio_comparison_report.md)
- [소형주 계절성 전략 vs 코스피/코스닥 10.5개년 비교 리포트](docs/seasonality_vs_kospi_backtest_result.md)
- [인터랙티브 웹 대시보드 (HTML)](docs/charts/backtest_dashboard.html)
