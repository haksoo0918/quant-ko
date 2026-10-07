# Quant-KO: 소형주 성장 가치 퀀트 자동매매 시스템

국내 코스피·코스닥 시가총액 하위 20% 소형주 중, 재무 건전성과 이익 성장률, 저평가 지표가 우수한 20개 종목을 분기별로 자동 추출하여 운용하는 퀀트 투자 및 한국투자증권(KIS) 자동매매 시스템입니다.

---

## 📌 주요 특징

1. **철저한 편향 제거 (Point-in-Time)**
   - OpenDART 실제 공시접수일(`rcept_dt`) 기준 데이터 반영 (미래참조 편향 0%)
   - 상장폐지 종목 및 관리/환기 종목 이력 반영 (생존 편향 제거)
2. **소형주 성장 가치 9대 팩터 모델**
   - **유니버스 필터**: 코스피/코스닥 보통주, 12월 결산법인 대상 (금융/지주/스팩/우선주/관리/중국계 제외)
   - **시총 필터**: 제외 필터 통과 종목 중 시가총액 하위 20%
   - **건전성 & 유동성**: 부채비율 ≤ 200%, 자본잠식률 ≤ 0%, 20일 평균 거래대금 ≥ 2억 원
   - **이익 기준**: 최근 분기 및 TTM 영업이익/지배주주순이익 > 0
   - **스코어링**: 시가총액(1) + 밸류 4종(PER, PSR, POR, PGPR) + 성장률 4종(순이익, 영업익, 총이익, 매출액 YoY)
3. **분기별 리밸런싱 & 리스크 관리**
   - 4월 첫 영업일, 5/8/11월 마지막 영업일 연 4회 리밸런싱
   - 장마감 동시호가(15:20~15:30) 지정가 분할/차이분 집행
   - 보유 종목 관리/환기 지정 시 익일 즉시 손절 및 현금화
4. **한국투자증권 KIS Open API 연동**
   - 모의투자 환경에서 1분기 이상 안전 검증 후 실계좌 전환 가능
   - 일일 감시 및 주문 결과 텔레그램 실시간 알림

---

## 🏗️ 시스템 아키텍처

```text
src/quant_ko/
  ├── data/        # OpenDART, KRX 수집기 및 SQLite 저장소
  ├── pit/         # 공시접수일 기준 Point-in-Time 재무 스냅샷 빌더
  ├── strategy/    # 유니버스 필터, 9대 팩터 스코어링 및 포트폴리오 산출
  ├── backtest/    # 2016~현재 백테스트 엔진, 거래비용 및 성과 리포트
  ├── broker/      # 한국투자증권 KIS Open API 연동 모듈 (모의/실전)
  ├── live/        # 분기 리밸런서, 일일 모니터링 봇, 스케줄러 진입점
  └── notify/      # 텔레그램 알림 봇
```

---

## 🚀 빠른 시작

### 1. 환경 설정
```bash
python -m venv .venv
source .venv/Scripts/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 환경 변수 설정
`.env.example`을 복사하여 `.env`를 생성하고 API 키를 입력합니다.
```env
OPENDART_API_KEY=your_dart_api_key
KIS_APP_KEY=your_kis_app_key
KIS_APP_SECRET=your_kis_app_secret
KIS_CANO=your_account_number
KIS_ACNT_PRDT_CD=01
KIS_MODE=MOCK  # MOCK(모의투자) 또는 REAL(실전)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 3. 데이터 수집 및 백테스트 실행
```bash
python -m quant_ko.data.collector --all
python -m quant_ko.backtest.run
```

---

## 📖 문서 링크
- [PRD (제품 요구사항 정의서)](PRD.md)
- [작업 큐 및 마일스톤](TODO.md)
- [변경 이력](CHANGELOG.md)
