"""Quant-KO 모니터링 대시보드 데이터 로더 및 시각화 단위 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest

from quant_ko.broker.kis import Balance, Position
from quant_ko.dashboard.app import (
    create_backtest_comparison_figure,
    create_equity_curve_figure,
    create_portfolio_allocation_figure,
)
from quant_ko.dashboard.data_loader import (
    build_account_equity_curve,
    get_db_status_summary,
    load_account_and_positions,
    load_actual_trade_logs,
    load_top20_preview,
    mask_account_no,
)
from quant_ko.data.store import DataStore


@pytest.fixture
def sample_dashboard_db(tmp_path: Path) -> Path:
    """테스트용 임시 SQLite 데이터베이스를 생성하고 샘플 데이터를 적재합니다."""
    db_file = tmp_path / "test_dashboard.db"
    store = DataStore(db_file)
    store.initialize_schema()

    store.upsert_companies(
        [
            {
                "ticker": "000010",
                "corp_code": "00000001",
                "name": "알파테크",
                "market": "KOSDAQ",
                "sector": "IT",
                "listed_at": "2015-01-01",
                "delisted_at": None,
                "fiscal_month": 12,
                "is_preferred": 0,
                "is_spac": 0,
            },
            {
                "ticker": "000020",
                "corp_code": "00000002",
                "name": "베타바이오",
                "market": "KOSDAQ",
                "sector": "제약",
                "listed_at": "2015-01-01",
                "delisted_at": None,
                "fiscal_month": 12,
                "is_preferred": 0,
                "is_spac": 0,
            },
        ]
    )

    store.upsert_daily_prices(
        [
            {
                "ticker": "000010",
                "date": "2026-10-14",
                "close": 1000.0,
                "market_cap": 30_000_000_000.0,
                "trading_value": 500_000_000.0,
            },
            {
                "ticker": "000020",
                "date": "2026-10-14",
                "close": 2000.0,
                "market_cap": 40_000_000_000.0,
                "trading_value": 600_000_000.0,
            },
            {
                "ticker": "000010",
                "date": "2026-10-15",
                "close": 1100.0,
                "market_cap": 33_000_000_000.0,
                "trading_value": 550_000_000.0,
            },
            {
                "ticker": "000020",
                "date": "2026-10-15",
                "close": 1900.0,
                "market_cap": 38_000_000_000.0,
                "trading_value": 520_000_000.0,
            },
            {
                "ticker": "000010",
                "date": "2026-10-16",
                "close": 1200.0,
                "market_cap": 36_000_000_000.0,
                "trading_value": 610_000_000.0,
            },
            {
                "ticker": "000020",
                "date": "2026-10-16",
                "close": 2100.0,
                "market_cap": 42_000_000_000.0,
                "trading_value": 630_000_000.0,
            },
        ]
    )

    # 2026-10-14: 알파테크 1,000주 @ 1,000원 매수 체결, 베타바이오 500주 @ 2,000원 매수 접수(ORDERED)
    store.insert_order(
        {
            "rebalance_date": "2026-10-14",
            "ticker": "000010",
            "side": "BUY",
            "qty": 1000,
            "price": 1000.0,
            "status": "FILLED",
            "filled_qty": 1000,
            "env": "mock",
        }
    )
    store.insert_order(
        {
            "rebalance_date": "2026-10-14",
            "ticker": "000020",
            "side": "BUY",
            "qty": 500,
            "price": 2000.0,
            "status": "ORDERED",
            "filled_qty": 0,
            "env": "mock",
        }
    )
    # 실패 주문 (잔고/자산 추이 계산에서 제외되어야 함)
    store.insert_order(
        {
            "rebalance_date": "2026-10-14",
            "ticker": "000020",
            "side": "BUY",
            "qty": 9999,
            "price": 2000.0,
            "status": "FAILED",
            "filled_qty": 0,
            "env": "mock",
        }
    )
    # 2026-10-16: 알파테크 400주 @ 1,200원 일부 매도 체결
    store.insert_order(
        {
            "rebalance_date": "2026-10-16",
            "ticker": "000010",
            "side": "SELL",
            "qty": 400,
            "price": 1200.0,
            "status": "FILLED",
            "filled_qty": 400,
            "env": "real",
        }
    )

    return db_file


def test_mask_account_no() -> None:
    """계좌번호 마스킹 처리가 다양한 입력 포맷에서 정확히 동작하는지 검증합니다."""
    assert mask_account_no("50219876", "01") == "5021****-01"
    assert mask_account_no("50219876-01") == "5021****-01"
    assert mask_account_no("5021987601") == "5021****-01"
    assert mask_account_no("", "01") == "미설정-01"


def test_load_account_and_positions_offline_fallback(sample_dashboard_db: Path) -> None:
    """오프라인(SQLite 폴백) 모드에서 보유 종목과 현금, 총자산이 정확히 복원되는지 검증합니다."""
    info = load_account_and_positions(
        db_path=sample_dashboard_db,
        fetch_live_kis=False,
        initial_capital=10_000_000.0,
    )

    assert info["source"] == "SQLITE_FALLBACK"
    # 초기자본 10,000,000 - 매수(1,000,000 + 1,000,000) + 매도(480,000) = 8,480,000원
    assert info["cash"] == 8_480_000.0

    # 잔여 보유: 000010 600주 @ 최신종가 1,200원 = 720,000원, 000020 500주 @ 최신종가 2,100원 = 1,050,000원
    assert info["stock_value"] == 1_770_000.0
    assert info["total_equity"] == 10_250_000.0
    assert info["positions_count"] == 2
    assert info["total_orders_count"] == 4

    pos_by_ticker = {p["ticker"]: p for p in info["positions"]}
    assert pos_by_ticker["000010"]["name"] == "알파테크"
    assert pos_by_ticker["000010"]["qty"] == 600
    assert pos_by_ticker["000010"]["current_price"] == 1200.0
    assert pos_by_ticker["000010"]["eval_amount"] == 720_000.0

    assert pos_by_ticker["000020"]["name"] == "베타바이오"
    assert pos_by_ticker["000020"]["qty"] == 500
    assert pos_by_ticker["000020"]["current_price"] == 2100.0
    assert pos_by_ticker["000020"]["eval_amount"] == 1_050_000.0


def test_load_account_and_positions_live_kis_mocked(
    sample_dashboard_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """KIS 실시간 연동 성공 시 브로커 잔고 응답을 우선 사용하는지 검증합니다."""

    class DummyKisClient:
        app_key = "dummy_key"
        app_secret = "dummy_secret"
        account_prefix = "50211234"
        account_suffix = "01"

        def fetch_balance(self) -> Balance:
            return Balance(
                cash=5_000_000.0,
                total_eval_amount=7_400_000.0,
                positions=[
                    Position(
                        ticker="000010",
                        name="알파테크",
                        qty=2000,
                        current_price=1200.0,
                        eval_amount=2_400_000.0,
                        purchase_price=1000.0,
                    )
                ],
            )

    monkeypatch.setattr("quant_ko.dashboard.data_loader.KisClient", DummyKisClient)
    info = load_account_and_positions(
        db_path=sample_dashboard_db,
        fetch_live_kis=True,
        initial_capital=10_000_000.0,
    )
    assert info["source"] == "KIS_LIVE"
    assert info["account_masked"] == "5021****-01"
    assert info["cash"] == 5_000_000.0
    assert info["stock_value"] == 2_400_000.0
    assert info["total_equity"] == 7_400_000.0
    assert info["positions_count"] == 1


def test_build_account_equity_curve(sample_dashboard_db: Path) -> None:
    """실제 계좌의 일자별 예수금, 주식평가액, 총자산, 수익률 추이를 정확히 계산하는지 검증합니다."""
    eq_df = build_account_equity_curve(
        db_path=sample_dashboard_db,
        initial_capital=10_000_000.0,
    )

    assert list(eq_df.columns) == ["date", "cash", "stock_value", "total_equity", "return_pct"]
    assert len(eq_df) == 3

    # 2026-10-14: 현금 8,000,000 + 주식(1,000*1,000 + 500*2,000 = 2,000,000) = 10,000,000
    day1 = eq_df.iloc[0]
    assert day1["date"] == "2026-10-14"
    assert day1["cash"] == 8_000_000.0
    assert day1["stock_value"] == 2_000_000.0
    assert day1["total_equity"] == 10_000_000.0
    assert day1["return_pct"] == 0.0

    # 2026-10-15: 현금 8,000,000 + 주식(1,000*1,100 + 500*1,900 = 2,050,000) = 10,050,000 (+0.5%)
    day2 = eq_df.iloc[1]
    assert day2["date"] == "2026-10-15"
    assert day2["cash"] == 8_000_000.0
    assert day2["stock_value"] == 2_050_000.0
    assert day2["total_equity"] == 10_050_000.0
    assert day2["return_pct"] == 0.5

    # 2026-10-16: 000010 400주 @ 1,200원 매도 -> 현금 8,480,000 + 주식(600*1,200 + 500*2,100 = 1,770,000) = 10,250,000 (+2.5%)
    day3 = eq_df.iloc[2]
    assert day3["date"] == "2026-10-16"
    assert day3["cash"] == 8_480_000.0
    assert day3["stock_value"] == 1_770_000.0
    assert day3["total_equity"] == 10_250_000.0
    assert day3["return_pct"] == 2.5


def test_load_actual_trade_logs_filters(sample_dashboard_db: Path) -> None:
    """실제 거래기록 조회 및 환경/매매구분/상태별 필터링이 정확히 동작하는지 검증합니다."""
    all_logs = load_actual_trade_logs(db_path=sample_dashboard_db)
    assert len(all_logs) == 4
    expected_cols = [
        "주문일시",
        "환경(모의/실전)",
        "종목코드",
        "종목명",
        "매매구분",
        "주문수량",
        "주문단가",
        "체결수량",
        "상태",
    ]
    assert list(all_logs.columns) == expected_cols
    assert "알파테크" in all_logs["종목명"].values
    assert "베타바이오" in all_logs["종목명"].values

    mock_only = load_actual_trade_logs(db_path=sample_dashboard_db, mode_filter="MOCK")
    assert len(mock_only) == 3

    real_only = load_actual_trade_logs(db_path=sample_dashboard_db, mode_filter="REAL")
    assert len(real_only) == 1
    assert real_only.iloc[0]["매매구분"] == "SELL"

    failed_only = load_actual_trade_logs(db_path=sample_dashboard_db, status_filter="FAILED")
    assert len(failed_only) == 1
    assert failed_only.iloc[0]["주문수량"] == 9999


def test_db_status_and_plotly_figures(sample_dashboard_db: Path) -> None:
    """DB 상태 요약과 Plotly 차트 생성 함수들이 오류 없이 Figure를 반환하는지 검증합니다."""
    summary = get_db_status_summary(db_path=sample_dashboard_db)
    assert summary["latest_date"] == "2026-10-16"
    assert summary["companies_count"] == 2
    assert summary["orders_count"] == 4

    acc_info = load_account_and_positions(db_path=sample_dashboard_db, fetch_live_kis=False)
    eq_df = build_account_equity_curve(db_path=sample_dashboard_db)

    fig_eq = create_equity_curve_figure(eq_df)
    assert len(fig_eq.data) == 3

    fig_alloc = create_portfolio_allocation_figure(acc_info["positions_df"], cash=acc_info["cash"])
    assert len(fig_alloc.data) >= 2

    fig_bt = create_backtest_comparison_figure()
    assert len(fig_bt.data) == 3

    latest_dt, univ_cnt, top_df = load_top20_preview(db_path=sample_dashboard_db)
    assert latest_dt == "2026-10-16"
    assert univ_cnt == 0
    assert top_df.empty


def test_streamlit_dashboard_full_ui_rendering_audit(
    sample_dashboard_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """대시보드 main() 실행 시 4대 탭, 메트릭, 차트, 테이블, 버튼 인터랙션이 예외 없이 렌더링되는지 검증합니다."""
    from contextlib import contextmanager
    from typing import Any

    from quant_ko.dashboard import app as dashboard_app

    class _MockColumnOrTab:
        def __init__(self, recorder: _MockStreamlit) -> None:
            self._st = recorder

        def __enter__(self) -> _MockColumnOrTab:
            return self

        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            return None

        def metric(self, label: str, value: Any, delta: Any = None) -> None:
            self._st.metric(label=label, value=value, delta=delta)

        def selectbox(self, label: str, options: list[Any], **kwargs: Any) -> Any:
            return self._st.selectbox(label=label, options=options, **kwargs)

    class _MockStreamlit:
        def __init__(self, button_clicked: bool = False) -> None:
            self.button_clicked = button_clicked
            self.page_config: dict[str, Any] = {}
            self.markdowns: list[str] = []
            self.subheaders: list[str] = []
            self.metrics: list[tuple[str, Any, Any]] = []
            self.plotly_charts: list[Any] = []
            self.dataframes: list[Any] = []
            self.tabs_created: list[str] = []
            self.selectboxes: list[str] = []
            self.download_buttons: list[str] = []
            self.success_messages: list[str] = []
            self.info_messages: list[str] = []
            self.warning_messages: list[str] = []

        def set_page_config(self, **kwargs: Any) -> None:
            self.page_config = kwargs

        def markdown(self, body: str, **kwargs: Any) -> None:
            self.markdowns.append(body)

        def subheader(self, body: str, **kwargs: Any) -> None:
            self.subheaders.append(body)

        def divider(self) -> None:
            pass

        def columns(self, spec: int | list[int]) -> list[_MockColumnOrTab]:
            count = spec if isinstance(spec, int) else len(spec)
            return [_MockColumnOrTab(self) for _ in range(count)]

        def tabs(self, tab_labels: list[str]) -> list[_MockColumnOrTab]:
            self.tabs_created.extend(tab_labels)
            return [_MockColumnOrTab(self) for _ in tab_labels]

        def metric(self, label: str, value: Any, delta: Any = None) -> None:
            self.metrics.append((label, value, delta))

        def plotly_chart(self, fig: Any, **kwargs: Any) -> None:
            self.plotly_charts.append(fig)

        def dataframe(self, data: Any, **kwargs: Any) -> None:
            self.dataframes.append(data)

        def selectbox(self, label: str, options: list[Any], **kwargs: Any) -> Any:
            self.selectboxes.append(label)
            return options[0]

        def download_button(self, label: str, **kwargs: Any) -> bool:
            self.download_buttons.append(label)
            return False

        def button(self, label: str, **kwargs: Any) -> bool:
            return self.button_clicked

        def info(self, body: str) -> None:
            self.info_messages.append(body)

        def warning(self, body: str) -> None:
            self.warning_messages.append(body)

        def success(self, body: str) -> None:
            self.success_messages.append(body)

        def toggle(self, label: str, value: bool = False, **kwargs: Any) -> bool:
            return value

        def error(self, body: str) -> None:
            pass

        def caption(self, body: str) -> None:
            pass

        @contextmanager
        def container(self, **kwargs: Any) -> Any:
            yield self

        @contextmanager
        def expander(self, label: str, **kwargs: Any) -> Any:
            yield self

        @contextmanager
        def spinner(self, text: str) -> Any:
            yield self

        def image(self, image: Any, **kwargs: Any) -> None:
            pass

    orig_load_acc = dashboard_app.load_account_and_positions
    monkeypatch.setattr(
        dashboard_app,
        "load_account_and_positions",
        lambda db_path="data/quant_ko.db", fetch_live_kis=True: orig_load_acc(
            db_path=db_path,
            fetch_live_kis=False,
        ),
    )

    mock_st = _MockStreamlit(button_clicked=True)
    monkeypatch.setattr(dashboard_app, "st", mock_st)

    dashboard_app.main(db_path=str(sample_dashboard_db))

    # 4개 필수 탭 검증
    assert mock_st.tabs_created == [
        "📈 전체 자산 변화 추이 & 보유 포트폴리오",
        "🧾 실제 거래기록 (Orders)",
        "🎯 전략 소개 (Strategy Spec)",
        "🔍 최신 타깃 20종목 & 시스템 상태",
    ]
    # 상단 4개 KPI + Tab 1 백테스트 4개 KPI + Tab 2 주문 4개 KPI + Tab 4 DB 상태 4개 KPI = 총 16개 메트릭
    assert len(mock_st.metrics) == 16
    # Tab 1의 3대 Plotly 차트 (Equity Curve, Portfolio Allocation, Backtest 10y Trajectory)
    # 및 Tab 4의 팩터 프로파일 차트 지원
    assert len(mock_st.plotly_charts) >= 3
    # 보유 종목 테이블 및 거래기록 테이블 렌더링 검증
    assert len(mock_st.dataframes) >= 2
    assert len(mock_st.selectboxes) == 3
    assert len(mock_st.download_buttons) == 1
    # 정상 진단 메시지 및 타깃 산출 메시지 확인
    assert len(mock_st.success_messages) >= 1

def test_load_account_and_positions_unfunded_waiting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """보유종목과 주문이 없는 자투리 잔고 계좌(예: 453원)는 -100%가 아니라 0.00% (운용 대기)로 처리되는지 검증합니다."""
    db_file = tmp_path / "empty_acc.db"
    store = DataStore(db_file)
    store.initialize_schema()

    class EmptyBalanceKisClient:
        app_key = "dummy_key"
        app_secret = "dummy_secret"
        account_prefix = "50219999"
        account_suffix = "01"

        def fetch_balance(self) -> Balance:
            return Balance(
                cash=453.0,
                total_eval_amount=453.0,
                positions=[],
            )

    monkeypatch.setattr("quant_ko.dashboard.data_loader.KisClient", EmptyBalanceKisClient)
    info = load_account_and_positions(
        db_path=db_file,
        fetch_live_kis=True,
        initial_capital=10_000_000.0,
    )
    assert info["source"] == "KIS_LIVE"
    assert info["total_equity"] == 453.0
    assert info["return_pct"] == 0.0
    assert info["return_label"] == "0.00% (운용 대기)"


def test_load_account_and_positions_custom_initial_capital(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """환경변수 INITIAL_CAPITAL이 지정되었을 때 초기자본금이 정확히 반영되는지 검증합니다."""
    db_file = tmp_path / "empty_acc2.db"
    store = DataStore(db_file)
    store.initialize_schema()

    monkeypatch.setenv("INITIAL_CAPITAL", "5000000")
    info = load_account_and_positions(
        db_path=db_file,
        fetch_live_kis=False,
    )
    assert info["initial_capital"] == 5_000_000.0

