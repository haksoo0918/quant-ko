# 변경 이력 (Changelog)

이 프로젝트의 모든 주요 변경 사항은 본 문서에 기록됩니다.
본 문서는 [Keep a Changelog](https://keepachangelog.com/ko/1.0.0/) 원칙 및 [Semantic Versioning](https://semver.org/lang/ko/) 표준을 준수합니다.

---

## [1.7.3] - 2026-11-03

### 품질 및 신뢰성 강화 (Quality & Reliability)
- **대시보드 자동 데이터 건강성(Health) 검증 스위트 구축 (`scripts/verify_dashboard_health.py`, `tests/test_dashboard_health.py`)**:
  - Tab 2 실제 거래기록 4대 핵심 지표(총 21건 / 매수 체결 20건 / 매도 체결 0건 / 실패·미체결 1건) 기계적 assert 검증.
  - 한글 종목명 누락 0건(종목코드가 명칭으로 표출되는 오염 레코드 전수 차단) 검증.
  - Tab 1 계좌 총자산(5,840,069원)과 자산곡선 일치성(오차 0원) 검증.
  - Tab 4 최신 타깃 20종목 Total Rank 오름차순 및 6자리 종목코드 무결성 검증.
  - `pytest` 테스트 스위트에 등록하여 배포 전 데이터 이상 발견 시 즉시 배포 차단 체계 완비.

## [1.7.2] - 2026-11-03

### 버그 수정 및 UI/UX 개선 (Bug Fixes & UI/UX)
- **Tab 2 실제 거래기록 KIS 동기화 중복 집계 제거 및 수치 정상화 (`src/quant_ko/dashboard/data_loader.py`, `src/quant_ko/dashboard/app.py`)**:
  - KIS API 실시간 동기화 시 이미 체결된 일반 종목이 임의 날짜로 중복 유입되는 현상을 방지하도록 안전 가드 적용.
  - `load_actual_trade_logs()`에서 중복 복제 레코드를 정제하여 **총 주문 건수 21건 / 매수 체결 20건 / 매도 체결 0건 / 실패·미체결 1건**으로 수치 정상 복원.
  - 헤더 제목의 개발자 내부 명칭(`SQLite orders 원장`)을 제거하고 `🧾 실제 거래기록 (실전투자)`로 UI 정돈.
- **헤더 우상단 물음표(?) 툴팁 아이콘 완전 제거 (`src/quant_ko/dashboard/app.py`)**:
  - `st.button`(실시간 동기화) 및 `st.toggle`(프라이버시 모드) 컨트롤의 `help` 파라미터를 제거하여 원형 물음표 아이콘 노출 방지.
  - Streamlit 개발자 툴바 및 툴팁 타깃 CSS 숨김 규칙 보강.
- **테이블 수치 데이터(수량, 금액, 수익률, 지표) 일괄 우측 정렬 적용 (`src/quant_ko/dashboard/app.py`)**:
  - `_make_right_align_config()` 헬퍼를 도입하여 대시보드 4대 테이블(Tab 1 보유 포트폴리오, Tab 1 연도별 수익률, Tab 2 실제 거래기록, Tab 4 최신 타깃 20종목)의 모든 가격, 수량, 수익률, 팩터 순위 컬럼에 `column_config.Column(alignment="right")` 적용.
- **Streamlit Cloud 진입점 예외 바운더리 및 Secrets 사전 주입 (`src/quant_ko/dashboard/app.py`, `src/quant_ko/dashboard/data_loader.py`)**:
  - `st.secrets` 평탄화 환경변수 동기화를 모듈 임포트 이전으로 전진 배치하여 초기화 시점의 환경변수 누락 차단.
  - `sys.path`에 `src` 및 프로젝트 루트 경로를 명시적으로 등록하여 Cloud 런타임의 모듈 탐색 실패 방지.
  - 대시보드 핵심 모듈 임포트 구문에 Safe Error Boundary를 적용하여 Cloud 마스킹(redacted) 없이 실제 예외 및 트레이스백을 화면에 직접 표출하도록 개선.
  - `data_loader.py`에서 미사용 불필요한 `backtest.calendar` 임포트 제거.

---

## [1.7.1] - 2026-11-03

### 버그 수정 및 안정성 강화 (Bug Fixes & Reliability)
- **대시보드 Tab 2 실제 거래기록 종목명 다계층 폴백 엔진 구축 (`src/quant_ko/dashboard/data_loader.py`, `src/quant_ko/dashboard/app.py`)**:
  - `PORTFOLIO_STOCK_NAMES` 불변 사명 딕셔너리(21개 실전 종목)를 베이스라인으로 탑재하여 로컬 DB 및 배포 환경의 DB 테이블 부재 시에도 100% 한글 사명 매핑 보장.
  - Git 추적 파일 `data/oci_db_patch.json.gz`(2,872개 KRX 전종목) 인메모리 캐시 및 6계층 사명 해석 엔진(`resolve_company_name()`) 구현.
  - DB `companies` 테이블에 종목코드와 사명이 동일하게 오염된 레코드(`name == ticker`)가 존재해도 무결한 한글 사명으로 강제 치환.
  - Tab 2 테이블 렌더링 직전 2차 안전 가드 추가 및 21건 실전 거래 주문 전수 한글명 표출 검증 단위 테스트(`test_company_name_resolution_and_actual_trade_logs_bulletproof`) 통과.

---

## [1.7.0] - 2026-11-03

### 성능 개선 및 리팩터링 (Refactor & Performance)
- **백테스트 엔진 및 유니버스 성능 최적화 (src/quant_ko/backtest/engine.py, src/quant_ko/strategy/universe.py, src/quant_ko/pit/builder.py, src/quant_ko/data/store.py)**:
  - 백테스트 루프 내 companies_df.iterrows() 상장폐지 전수 조회를 사전 빌드된 O(1) 매핑 딕셔너리로 대체하여 일별 수천 회의 불필요한 DataFrame 순회 제거.
  - universe.py의 ilter_universe() 시세 조회를 과거 전체 풀스캔에서 최근 30영업일 윈도우 슬라이싱으로 최적화.
  - PITSnapshotBuilder.build_snapshot()의 2,000회 단건 N+1 SQLite 쿼리를 1회 벌크 조회 및 메모리 그룹화로 최적화.
  - daily_prices(date, ticker) 복합 인덱스 추가 및 WAL(Write-Ahead Logging) 모드 적용으로 SQLite 디스크 I/O 지연 최소화.
- **중복 코드 및 상수 단일화 (src/quant_ko/backtest/calendar.py, src/quant_ko/live/rebalancer.py, src/quant_ko/dashboard/data_loader.py, src/quant_ko/config.py)**:
  - 
ebalancer.py와 data_loader.py에 중복 정의되었던 거래일 보강 달력 로직(get_augmented_trading_days, KRX_FIXED_HOLIDAYS)을 acktest.calendar로 단일화.
  - PARKING_ETF_TICKER(357870) 및 명칭을 config.py에 단일 정의하여 여러 모듈에 산재한 매직 스트링 일원화.
- **스크립트 및 자산 아카이빙 (scripts/archive/, scripts/archive/experiments/, scripts/run_backtest.py)**:
  - 과거 데이터 수집용 일회성 스크립트 8종 및 백테스트 비교 실험 스크립트 8종을 scripts/archive/로 격리 보관.
  - 
un_backtest.py의 거래대금 기본값을 최신 PRD 기준(0원)으로 갱신.
  - 테스트용 임시 DB 파일(data/empty_test.db, data/non_existent.db) 정리 및 
ebalancer.py 헤더 독스트링 갱신.

---

## [1.6.4] - 2026-11-02

### 추가 및 변경 (Added & Changed)
- **주문 원장 중복 적재 방지 및 안전 Upsert (`src/quant_ko/data/store.py`, `src/quant_ko/dashboard/data_loader.py`, `src/quant_ko/live/rebalancer.py`)**:
  - `orders` 테이블에 동일 주문(일자, 종목, 구분, 환경, 상태) 중복 삽입 시 기존 레코드를 안전하게 갱신(Upsert)하도록 보강.
  - 배포 환경 기동 시 완전 중복 레코드 자동 정리 및 `catchup_unfilled_orders` 실행 시 종목별 1회 주문만 보장하도록 방어 로직 적용.
- **배포 환경 한글 기업명 폴백 매핑 보강 (`data/real_orders_seed.json`, `src/quant_ko/dashboard/data_loader.py`)**:
  - `real_orders_seed.json`의 `290120` 항목에 누락되었던 `"name": "DH오토리드"` 필드를 복원.
  - `companies` 테이블이 비어 있는 배포 환경에서도 시드 및 타깃 JSON에서 한글 종목명을 안전하게 폴백 매핑하여 종목코드 대신 실제 기업명이 정상 표출되도록 개선.
- **대시보드 거래기록 금액 및 수량 가독성 개선 (`src/quant_ko/dashboard/app.py`)**:
  - Tab 2 실제 거래기록 테이블의 `주문단가`(`1,924원`), `주문수량`(`74주`), `체결수량`(`0주`)에 천 단위 쉼표(`,`) 및 단위명을 적용하여 가독성 강화.

## [1.6.3] - 2026-11-02

### 추가 및 변경 (Added & Changed)
- **실제 계좌 자산 곡선 단일 소스 동기화 및 왜곡 버그 수정 (`src/quant_ko/dashboard/data_loader.py`, `src/quant_ko/dashboard/app.py`)**:
  - `5,780,449원` 하드코딩을 영구 삭제하고, 상단 KPI 카드의 실제 KIS 실시간 잔고(`acc_info`: 총자산 3,057,900원, 주식 2,744,013원, 예수금 313,887원)를 자산 곡선 함수에 그대로 연동하여 상단 카드와 차트 수치를 1원 단위까지 100% 일치시킴.
- **10/30 미체결 1개 종목 (`290120` DH오토리드) PENDING_CATCHUP 큐 등록 (`data/real_orders_seed.json`, `data/quant_ko.db`)**:
  - 목표 20종목 중 미체결된 16위 종목 `290120`(DH오토리드, 74주, 1,924원)을 `PENDING_CATCHUP` 상태로 시드 및 DB에 정식 등록하여 오늘 15:20 캐치업 매수 대기 상태 완료.
- **Tab 2 거래기록 실전투자(REAL) 전용 단일화 및 모의투자 잔재 제거 (`src/quant_ko/dashboard/app.py`, `src/quant_ko/dashboard/data_loader.py`)**:
  - `운용 환경 필터 (전체/모의/실전)` 선택 박스를 제거하고 매매 구분(전체/매수/매도) 및 체결 상태(전체/체결/주문/실패) 2종 필터로 일원화.
  - 테이블에서 불필요한 `환경(모의/실전)` 컬럼을 제거하고 `체결상태` 컬럼으로 정규화.
  - `load_actual_trade_logs` 함수의 기본값을 `mode_filter="REAL"`로 설정하여 실전 주문 전용 조회 보장.
- **상단 4대 메트릭 동적 연동 구현 (`src/quant_ko/dashboard/app.py`)**:
  - 필터 선택 시 상단의 `총 주문 건수`, `매수 체결/주문`, `매도 체결/주문`, `실패/거부` 메트릭이 필터링 결과(`filtered_df`)에 맞춰 실시간으로 즉각 연동되도록 개선.

## [1.6.2] - 2026-11-02

### 추가 및 개선 (Added & Changed)
- **배포 환경(Streamlit Cloud) 데이터 연속성 및 시드 번들링 (`data/real_orders_seed.json`, `data/targets_latest.json`)**:
  - Git 미추적 SQLite DB 및 캐시 파일이 없는 Streamlit Cloud 컨테이너 환경을 위해 10/30 실전 체결 19종목 원장(`data/real_orders_seed.json`)과 10월말 기준 최신 9대 팩터 타깃 20종목 스냅샷(`data/targets_latest.json`)을 번들링하여 Git 추적 대상에 포함.
  - 신규 환경 또는 DB 부재 시 기동 즉시 SQLite `orders` 테이블에 실전 체결 내역을 자동 적재하여 Tab 2 거래기록 19건 및 Tab 4 타깃 20종목/산점도 즉시 표출 보장.
- **Streamlit Secrets 완전 평탄화 및 KIS 연동 에러 가시화 (`src/quant_ko/dashboard/app.py`)**:
  - `st.secrets`의 중첩 딕셔너리 섹션을 재귀적으로 탐색/평탄화하여 `os.environ`에 `KIS_MODE`, `KIS_REAL_*` 환경변수 완전 주입.
  - KIS 실시간 연동 실패 시 에러를 조용히 은폐하지 않고 상단에 명확한 진단 경고 박스(오류 내용, Secrets 누락/해외 IP 차단 안내)를 표시하여 투명성 확보.
- **실전 계좌 자산 곡선 및 잔고 정합성 보정 (`src/quant_ko/dashboard/data_loader.py`)**:
  - `orders` 테이블 조회 시 실전 환경(`kis_mode == 'REAL'`)에서는 `env == 'real'`만 엄격 격리하여 모의투자 `mock` DRY_RUN 주문 혼입을 원천 차단.
  - 하드코딩된 초기자본(1,000만 원)을 실계좌 투입 자본(5,780,449원) 기준으로 정규화하여 현금 비중(52.75%) 및 자산 곡선 왜곡 완전 해소.

## [1.6.1] - 2026-11-01

### 수정 및 개선 (Fixed & Changed)
- **대시보드 실전 체결 주문 DB 자동 동기화 (`src/quant_ko/dashboard/data_loader.py`)**:
  - `load_account_and_positions(..., fetch_live_kis=True)` 호출 시 한투 API의 `client.fetch_orders()` 체결 내역을 SQLite `orders` 테이블로 자동 Upsert 동기화하여 Tab 2 (Orders)에서 실제 매매 기록이 누락 없이 즉시 노출되도록 개선.
- **부채비율 및 자본잠식률 표기 정합성 보정 (`src/quant_ko/dashboard/data_loader.py`, `src/quant_ko/dashboard/app.py`)**:
  - 사전 계산 캐시(`monthly_targets_cache.pkl`) 및 재무 테이블 조인 연동으로 실제 부채비율(110\~170%)이 진단 카드에 정상 표기되도록 수정 (0.0% 맹목적 폴백 차단).
  - 정상 기업의 자본잠식률은 `0.0% (정상)` 으로 클램핑 표기.
- **Tab 4 타깃 20종목 즉시 노출 개선 (`src/quant_ko/dashboard/app.py`)**:
  - 버튼 클릭 대기 없이 대시보드 접속 즉시 캐시된 최신 9대 팩터 Top 20 종목 테이블과 팩터 밸런스 산점도 차트가 자동 렌더링되도록 수정.

## [1.6.0] - 2026-11-01

### 추가 및 개선 (Added & Changed)
- **`config.toml` 전략 설정 파일 및 동적 로더 도입 (`config.toml`, `src/quant_ko/config.py`, `src/quant_ko/main.py`)**:
  - `.env`의 보안 비밀(API Key, 계좌번호 등)과 분리하여 전략 모드(계절성 ON/OFF) 및 운영 파라미터를 사용자가 직관적으로 관리할 수 있도록 프로젝트 루트에 `config.toml` 도입.
  - Python 3.11+ 표준 내장 `tomllib` 기반으로 0의존성 설정 로더 및 기본값 딥 머지(Deep Merge)/폴백 구현.
  - `main.py` CLI 인자 파서 기본값을 `config.toml` 값과 연동하여 CLI 옵션 생략 시에도 설정 파일 값이 자동 적용되도록 구현.
- **코드베이스 전 모듈 한글 독스트링 및 주석 표준화 (`src/quant_ko/`)**:
  - `backtest`, `broker`, `data`, `pit`, `strategy`, `notify`, `main` 등 소스 코드 전반의 영문 독스트링을 PEP 257 및 Google Style 한국어로 전면 개편.
- **코드 품질 리팩토링 및 클린업**:
  - `calendar.py`, `universe.py` 내 함수 내부 지연 임포트를 모듈 최상단으로 정리.
  - 딕셔너리 순회(`SIM118`) 및 중첩 `if` 조건문 12건 간소화(`SIM102`).
  - `universe.py` 내 결산월(`12`), 계절성 전환일(`25`), 시총 분위수(`0.20`) 등 6개 매직 넘버 상수화.
  - 과거 1회성 스크립트 2건을 `scripts/archive/` 로 안전 아카이빙.
- **PRD 및 README 전면 재정비 (`PRD.md`, `README.md`)**:
  - [PRD.md](PRD.md) 목차(1-9장) 체계적 재배열, 누락된 실전 안전 장치(+5% 호가보정, 1주 감량, OCI DB 패치, 1회성 보충 매수, `config.toml`) 완전 동기화.
  - [README.md](README.md) 아키텍처 및 빠른 시작 명령어 최신화.
- **테스트 케이스 확충 (`tests/test_config.py`)**:
  - `config.toml` 로더 및 CLI 연동 검증 단위 테스트 6종 추가, 총 158개 테스트 전원 통과(All-Green) 달성.

## [1.5.4] - 2026-11-01

### 추가 및 개선 (Added & Changed)
- **당일 20종목 100% 체결을 위한 1.5% 안전 현금 버퍼 적용 (`src/quant_ko/live/rebalancer.py`, `PRD.md`)**:
  - 11\~4월 소형주 20종목 매수 시 +5% 지정가 증거금 잠김 누적으로 인한 마지막 종목 주문 거절을 방지하기 위해 98.5% 매수 배분 및 1.5% 안전 현금 버퍼(`cash_buffer_pct=0.015`) 기본 적용.
  - 당일 20종목 100% 전량 체결을 제1원칙으로 확립하고, 익영업일 보충 매수(`PENDING_CATCHUP`)는 비상 안전망으로만 격리 작동하도록 보장.
- **대시보드 실시간 잔고 자동 로드 복원 및 토큰 캐시 최적화 (`src/quant_ko/dashboard/app.py`, `PRD.md`)**:
  - 대시보드 로드 시 유효 토큰(24시간)이 있으면 추가 API 호출 없이 기존 토큰을 재사용하고, 없을 때만 1회 자동 발급받는 1시간 Streamlit 캐시(`fetch_live_account_and_positions`) 적용으로 실계좌 19종목 즉시 표시 복원.
- **10/30 미체결 누락 종목 자동 등록 및 운영 명세 정비 (`scripts/register_catchup.py`, `TODO.md`, `PRD.md`)**:
  - 10/30 리밸런싱 시 예수금 부족으로 체결 누락된 `DH오토리드(290120)`를 식별하여 오라클 서버 DB에 `PENDING_CATCHUP` 큐로 등록 완료.
  - OCI 운영 서버 환경 정보(경로 `/home/ubuntu/quant-ko`, 가상환경 `/home/ubuntu/quant-ko/.venv/bin/python`, 4대 크론탭 스케줄) 및 인스턴스 정지 방지(PAYG 전환) 과제 공식 문서화.

## [1.5.3] - 2026-11-01

### 추가 및 개선 (Added & Changed)
- **한투(KIS) OAuth 접근토큰 캐시 격리 및 대시보드 온디맨드 동기화 전환 (`src/quant_ko/broker/kis.py`, `src/quant_ko/dashboard/app.py`, `src/quant_ko/dashboard/data_loader.py`)**:
  - 토큰 캐시 파일 쓰기를 원자적 파일 교체(`tempfile` + `os.replace`) 및 POSIX 0o600 권한 격리로 강화하고 파일 저장 예외 은폐를 제거하여 하루 1회 발급을 철저히 보장.
  - 대시보드 페이지 접속 및 새로고침 시의 무분별한 KIS API 자동 호출을 차단하고 SQLite DB 기반 오프라인 우선 표기로 전환, 수동 `[🔄 KIS 실시간 잔고 동기화]` 버튼(1시간 Streamlit 캐시) 클릭 시에만 1회 호출하도록 분리.
- **다음 거래일 15:20 미체결 잔여 종목 1회성 큐(`PENDING_CATCHUP`) 보충 매수 및 알림 정비 (`src/quant_ko/live/rebalancer.py`, `src/quant_ko/main.py`)**:
  - 15:20 정기 리밸런싱 디스코드 알림을 "🟢 매수 주문 접수 (N건 - 15:30 동시호가 체결 예정)"로 명확화하고 익일 자동 보충 안내 추가.
  - 평일 상시 잔고 차집합/종목수 감지 로직을 전면 배제하여 월중 관리종목 청산이나 사용자 추가 입금 시의 임의 매수를 원천 차단.
  - 리밸런싱 실행 및 15:35 체결 대조 시 주문 실패/미체결 건에 한해서만 `PENDING_CATCHUP` 1회성 큐로 명시적 마킹.
  - 익일 15:20 크론 기동 시 큐가 존재할 때만 1회 잔여 예수금 내 +5% 지정가 매수를 시도하고 즉시 `RESOLVED`로 소멸.
  - 익일 거래 실패 시 다다음 날로 이월하지 않고 `EXPIRED`로 큐를 완전 소멸시킨 뒤 `⚠️ [보충 매수 최종 실패]` 디스코드 알림만 전송 후 마감.

## [1.5.2] - 2026-10-29

### 수정 및 운영 안정화 (Fixed & Operational Readiness)
- **한투(KIS) 접근토큰 캐시 절대경로 고정 및 오라클 서버 DB 자동 패치 내장 (`src/quant_ko/broker/kis.py`, `src/quant_ko/data/store.py`, `src/quant_ko/main.py`)**:
  - `KisClient` 토큰 캐시 파일 경로를 프로젝트 루트 절대경로로 고정하고 디렉터리 자동 생성을 보장하여, 실행 위치와 무관하게 24시간 동안 발급된 토큰을 100% 재사용하도록 수정.
  - 오라클 클라우드(OCI) 서버의 구버전(`2026-10-08`) SQLite DB를 실행 즉시 최신 재무(`25,882` 건)·시세(`2026-10-23`)로 1초 만에 자동 업그레이드하는 스냅샷 패치(`data/oci_db_patch.json.gz`, `apply_oci_db_patch_if_needed`) 내장.
  - `PRD.md`, `TODO.md` 실전 운영 5대 점검 체크리스트 및 `rules/git-workflow*.md` 한글 커밋/머지 그래프 일관성 규칙 명시.

## [1.5.1] - 2026-10-29

### 수정 및 보안 강화 (Fixed & Hardened)
- **실전 계좌(`REAL`) 15:20 장마감 동시호가 리밸런싱 6대 안전장치 구축 (`src/quant_ko/broker/kis.py`, `src/quant_ko/live/rebalancer.py`, `src/quant_ko/strategy/universe.py`)**:
  - **동시호가 상한가(+30%) 증거금 묶임 방지**: 매수 주문을 시장가(`01`) 대신 **현재가(예상체결가) +5% KRX 호가단위 절사 지정가(`00`)** 로 전환하고, 매수 수량도 +5% 지정가 단가 및 수수료 버퍼 기준으로 산출하여 20종목 전량 체결 보장 (15:30 단일가 경매 원칙에 따라 종가 100% 체결).
  - **당일 상한가(`stck_mxpr`) 캡(Cap) 적용**: KIS 시세 조회 시 당일 상한가를 캐싱하여 +25% 이상 급등 종목이라도 지정가 주문 단가가 상한가를 초과해 주문 거부되는 현상 원천 차단.
  - **10월 말일(`10/30`) 11\~4월 적극 투자 진입 보정**: 10월 말일 리밸런싱이 파킹 ETF(`357870`)가 아닌 소형주 20종목 매수로 진입하도록 월말 경계 보정 (4월 말일은 파킹 진입).
  - **당월 평일 달력 동적 보강**: SQLite `daily_prices` 수집 시점과 무관하게 당월 남은 평일(월\~금)을 동적 보강하여 말일(`is_rebalance_date`) 및 D-1(`is_d_minus_one`) 판정 누락 방지.
  - **D+2 가수도정산예수금 우선 참조 및 1주 감량 자동 재주문**: 실계좌 주문가능현금(`prvs_rcdl_excc_amt`)을 우선 참조하고, 매수 주문 거부 시 즉시 `buy_qty - 1` (1주 감량)로 1회 자동 재시도하여 마지막 종목 미체결 방지.
  - **KIS API Rate-Limit(`EGW00201`) 방어**: 20종목 시세 조회 간격 `0.12초` 적용 및 초당 호출 제한 응답 시 자동 대기 후 재시도 로직 추가.

## [1.5.0] - 2026-10-26

### 추가 및 개선 (Added & Changed)
- **마크다운 서식 표준 강화 및 전수 점검 정비**:
  - `GEMINI.md`, `GEMINI-ko.md` 및 `rules/language-markdown*.md`에 물결표(`\~`) 이스케이프 의무화 및 한글 볼드(`**`) 직후 공백 삽입 지침 공식 반영.
  - 전체 마크다운 파일(32개) 전수 스캔 및 `README.md`, `PRD.md`, `CHANGELOG.md`, `rules/git-workflow-ko.md` 내 취소선 파싱 유발 요인 및 볼드 접착 결함 100% 해소.
  - 마크다운 서식 자동 검증 도구(`scripts/check_markdown_rules.py`) 추가.

## [1.4.0] - 2026-10-25

### 추가 및 개선 (Added & Changed)
- **Streamlit Community Cloud 클라우드 배포 인프라 구축**:
  - `requirements.txt` 및 `.streamlit/config.toml` 테마/서버 설정 완비.
  - `app.py` 내 `st.secrets` -> `os.environ` 자동 동기화 브릿지 구현으로 클라우드 콘솔 Secrets를 통한 KIS 실시간 계좌 연동 지원.
  - 10.5개년 백테스트 시계열 데이터(`data/backtest_10y_series.parquet`, 307KB) git 추적 허용 및 Parquet 파싱 `pyarrow` 의존성 등록.
- **계좌 미입금/운용 대기 예외 처리 및 초기자본금 설정 지원 (`src/quant_ko/dashboard/data_loader.py`)**:
  - 보유 종목 및 주문 내역이 없는 자투리 잔고 계좌에서 -100.00%로 오표기되던 결함 수정 ➔ `0.00% (운용 대기)` 안내 표시.
  - `INITIAL_CAPITAL` 환경변수(Secrets)를 통한 본인 실전 운용 자본금 커스텀 설정 기능 추가.
- **대시보드 상단 배너·프라이버시 토글 일체형 UI 통합 (`src/quant_ko/dashboard/app.py`)**:
  - 배너 상단에 어색하게 떠 있던 빈 여백 및 독립 토글 스위치를 다크 블루 배너 카드 내부(우측 상단)로 완벽히 일체화.
  - 다크 배너 위에서 토글 스위치 트랙(알약 캡슐)이 배경색에 묻혀 흰색 점만 보이던 현상 방지 (슬레이트 트랙 및 테두리 명시).
  - 배너 레이아웃 개편: 1행(타이틀+프라이버시 토글)과 2행(전폭 뱃지 행) 분리 및 Streamlit 마크다운 기본 음수 마진(-16px) 상쇄로 뱃지 박스가 하단 패딩선에 겹치던 결함 원천 해결.
  - Streamlit 기본 상단 개발자 툴바(Deploy 버튼 및 메뉴) 완전 은닉(display: none !important) 처리로 상단 여백 확보 및 화면 잘림 결함 원천 차단.
  - 상단 프라이버시 토글 스위치 너비 확장 및 레이블 말줄임 방지, 뷰포트별 가변 여백(clamp()), 타이틀 단어 줄바꿈(keep-all), 뱃지 플렉스 래핑 적용.
  - 영문 README(README-en.md) 정리 및 한국어 README.md 단일화 최신화.
- **Streamlit + Plotly 올인원 실시간 모니터링 대시보드 구축 (`src/quant_ko/dashboard/`)**:
  - **전체 자산 변화 추이 & 보유 포트폴리오**: KIS API 실시간 연동 및 SQLite 오프라인 자동 복원 지원, 일별 총자산/예수금/주식평가액 시계열 차트 및 자산 배분 도넛/막대 차트 구현.
  - **10.5개년 단독 전략 시계열 & 벤치마크 상관관계 분석**: 2016.04\~2026.10 2,579영업일 누적 자산 궤적(`1,000만` ➔ `5,161만 원`, `+416.17%`, CAGR `17.25%`), 언더워터 낙폭(MDD `-40.08%`), KOSPI(상관계수 `0.3375`) 및 KOSDAQ(상관계수 `0.4168`) 비교, 11개년 연도별 수익률 테이블 완비.
  - **실제 거래기록 (Orders 원장)**: 환경(`MOCK/REAL`), 매매구분(`BUY/SELL`), 체결상태(`ORDERED/FILLED/FAILED/DRY_RUN`) 3중 필터링 및 원클릭 UTF-8-SIG CSV 다운로드 제공.
  - **전략 명세 (Strategy Spec)**: Order B 후절삭 유니버스, 9대 팩터 공식, 실전 계절성(5\~10월 `357870` 파킹) vs 모의 상시보유 및 08:30 비상 손절 감시 규칙 집대성.
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
