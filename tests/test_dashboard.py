"""Quant-KO 모니터링 대시보드 데이터 로더 및 시각화 단위 테스트."""

from __future__ import annotations

import pickle
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from quant_ko.broker.kis import Balance, Position
from quant_ko.dashboard.app import (
    create_backtest_comparison_figure,
    create_equity_curve_figure,
    create_portfolio_allocation_figure,
)
from quant_ko.dashboard.data_loader import (
    build_account_equity_curve,
    diagnose_held_positions_risk,
    get_db_status_summary,
    load_account_and_positions,
    load_actual_trade_logs,
    load_cached_top20,
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
    """실제 거래기록 조회 및 실전(REAL) 기본 필터링, 매매구분/상태별 조회가 정확히 동작하는지 검증합니다."""
    # 기본값은 실전(REAL) 전용
    real_default = load_actual_trade_logs(db_path=sample_dashboard_db)
    expected_cols = [
        "주문일시",
        "종목코드",
        "종목명",
        "매매구분",
        "주문수량",
        "주문단가",
        "체결수량",
        "체결상태",
    ]
    assert list(real_default.columns) == expected_cols
    assert "환경(모의/실전)" not in real_default.columns
    assert len(real_default) == 1
    assert real_default.iloc[0]["매매구분"] == "SELL"
    assert real_default.iloc[0]["체결상태"] == "FILLED"

    # 하위 호환성: mode_filter="ALL" 시 모의/실전 전체 4건 반환
    all_logs = load_actual_trade_logs(db_path=sample_dashboard_db, mode_filter="ALL")
    assert len(all_logs) == 4
    assert list(all_logs.columns) == expected_cols
    assert "알파테크" in all_logs["종목명"].values
    assert "베타바이오" in all_logs["종목명"].values

    mock_only = load_actual_trade_logs(db_path=sample_dashboard_db, mode_filter="MOCK")
    assert len(mock_only) == 3

    failed_only = load_actual_trade_logs(
        db_path=sample_dashboard_db, mode_filter="ALL", status_filter="FAILED"
    )
    assert len(failed_only) == 1
    assert failed_only.iloc[0]["주문수량"] == 9999
    assert failed_only.iloc[0]["체결상태"] == "FAILED"


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


def test_streamlit_dashboard_full_ui_rendering_audit(
    sample_dashboard_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """대시보드 main() 실행 시 4대 탭, 메트릭, 차트, 테이블, 버튼 인터랙션이 예외 없이 렌더링되는지 검증합니다."""
    from quant_ko.dashboard import app as dashboard_app

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
    assert len(mock_st.selectboxes) == 2
    assert mock_st.selectboxes == ["매매 구분 필터", "체결 상태 필터"]
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


def test_load_account_and_positions_default_offline(sample_dashboard_db: Path) -> None:
    """fetch_live_kis 기본 인자가 False여서 KIS API 호출 없이 오프라인 모드로 로드되는지 검증합니다."""
    info = load_account_and_positions(db_path=sample_dashboard_db)
    assert info["source"] == "SQLITE_FALLBACK"
    assert info["synced_at"] is None


def test_top_header_and_kpis_offline_and_live_sync_behavior(sample_dashboard_db: Path) -> None:
    """대시보드 상단 배너에서 오프라인 뱃지 및 동기화 버튼 클릭 시 실시간 뱃지와 잔고가 갱신되는지 검증합니다."""
    from contextlib import contextmanager

    from quant_ko.dashboard import app as dashboard_app

    offline_info = load_account_and_positions(db_path=sample_dashboard_db, fetch_live_kis=False)

    class _MockHeaderStreamlit:
        def __init__(self, button_clicked: bool = False) -> None:
            self.button_clicked = button_clicked
            self.markdowns: list[str] = []
            self.metrics: list[Any] = []
            self.toasts: list[str] = []
            self.session_state: dict[str, Any] = {}

        def markdown(self, body: str, **kwargs: Any) -> None:
            self.markdowns.append(body)

        def columns(self, spec: int | list[int]) -> list[Any]:
            count = spec if isinstance(spec, int) else len(spec)
            return [_MockHeaderColumn(self) for _ in range(count)]

        def button(self, label: str, **kwargs: Any) -> bool:
            return self.button_clicked

        def toggle(self, label: str, value: bool = False, **kwargs: Any) -> bool:
            return False

        def toast(self, body: str, **kwargs: Any) -> None:
            self.toasts.append(body)

        def metric(self, label: str, value: Any, delta: Any = None) -> None:
            self.metrics.append((label, value, delta))

        @contextmanager
        def container(self, **kwargs: Any) -> Any:
            yield self

    class _MockHeaderColumn:
        def __init__(self, recorder: Any) -> None:
            self._st = recorder

        def __enter__(self) -> Any:
            return self

        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            pass

        def metric(self, label: str, value: Any, delta: Any = None) -> None:
            self._st.metric(label=label, value=value, delta=delta)

    # 1. 오프라인 기본 상태 (버튼 미클릭)
    st_mock1 = _MockHeaderStreamlit(button_clicked=False)
    orig_st = dashboard_app.st
    dashboard_app.st = st_mock1
    try:
        acc_info_test = dict(offline_info)
        dashboard_app._render_top_header_and_kpis(acc_info_test, db_path=str(sample_dashboard_db))
        assert any("📦 DB 체결 기반 잔고" in m for m in st_mock1.markdowns)
        assert any("badge-offline-db" in m for m in st_mock1.markdowns)

        # 2. 실시간 동기화 상태 (source == KIS_LIVE)
        live_info = dict(offline_info)
        live_info["source"] = "KIS_LIVE"
        live_info["synced_at"] = "14:30"
        st_mock2 = _MockHeaderStreamlit(button_clicked=False)
        dashboard_app.st = st_mock2
        dashboard_app._render_top_header_and_kpis(live_info, db_path=str(sample_dashboard_db))
        assert any("⚡ KIS 실시간 잔고 (14:30 동기화)" in m for m in st_mock2.markdowns)
        assert any("badge-live-kis" in m for m in st_mock2.markdowns)
    finally:
        dashboard_app.st = orig_st


def test_load_account_and_positions_syncs_live_orders_to_db(
    sample_dashboard_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """KIS 실시간 연동 시 브로커 체결 주문이 DB orders 테이블에 자동 동기화되는지 검증합니다."""
    store = DataStore(sample_dashboard_db)
    # 초기 실전 주문은 1건 (000010 SELL 400)
    initial_real_orders = store.get_orders(env="real")
    assert len(initial_real_orders) == 1

    class LiveOrderKisClient:
        app_key = "dummy_key"
        app_secret = "dummy_secret"
        account_prefix = "50211234"
        account_suffix = "01"

        def fetch_balance(self) -> Balance:
            return Balance(
                cash=6_000_000.0,
                total_eval_amount=8_000_000.0,
                positions=[
                    Position(
                        ticker="000030",
                        name="감마제약",
                        qty=200,
                        current_price=10_000.0,
                        eval_amount=2_000_000.0,
                        purchase_price=9_500.0,
                    )
                ],
            )

        def fetch_orders(self, date: str | None = None) -> list[dict]:
            return [
                {
                    "order_no": "ORD-LIVE-101",
                    "ticker": "000030",
                    "side": "BUY",
                    "order_qty": 200,
                    "filled_qty": 200,
                    "order_price": 9500.0,
                    "status": "FILLED",
                    "raw_status": "체결완료",
                }
            ]

    monkeypatch.setattr("quant_ko.dashboard.data_loader.KisClient", LiveOrderKisClient)

    # 1. 1차 호출: 신규 체결 주문 동기화
    info = load_account_and_positions(
        db_path=sample_dashboard_db,
        fetch_live_kis=True,
    )
    assert info["source"] == "KIS_LIVE"

    real_orders = store.get_orders(env="real")
    assert len(real_orders) == 2
    new_order = real_orders[real_orders["ticker"] == "000030"].iloc[0]
    assert new_order["side"] == "BUY"
    assert new_order["qty"] == 200
    assert new_order["price"] == 9500.0
    assert new_order["status"] == "FILLED"
    assert new_order["filled_qty"] == 200
    assert new_order["env"] == "real"

    # 2. 2차 호출 시 중복 적재되지 않아야 함
    info2 = load_account_and_positions(
        db_path=sample_dashboard_db,
        fetch_live_kis=True,
    )
    real_orders2 = store.get_orders(env="real")
    assert len(real_orders2) == 2
    assert info2["total_orders_count"] == 5  # 기존 4건 + 신규 1건


def test_diagnose_held_positions_risk_debt_and_impairment(
    tmp_path: Path,
) -> None:
    """보유종목 진단 시 mock 캐시 pkl 및 DB financials에서 정상 부채비율과 자본잠식률(0.0% 정상)을 산출하는지 검증합니다."""
    # 1. Mock monthly_targets_cache.pkl 생성하여 캐시 우선 조회 검증
    mock_cache_file = tmp_path / "mock_monthly_targets_cache.pkl"
    mock_selected_df = pd.DataFrame(
        [
            {
                "ticker": "225590",
                "name": "엠에프엠코리아",
                "debt_ratio": 130.0,
                "impairment_ratio": 0.0,
            },
            {
                "ticker": "060480",
                "name": "포엔샤",
                "debt_ratio": 130.0,
                "impairment_ratio": 0.0,
            },
        ]
    )
    mock_cache_data = {
        "2026-10-31": {
            "period_label": "2026-10",
            "prior_date": "2026-09-30",
            "selected_df": mock_selected_df,
        }
    }
    with open(mock_cache_file, "wb") as f:
        pickle.dump(mock_cache_data, f)

    cache_positions_df = pd.DataFrame(
        [
            {"ticker": "225590", "name": "엠에프엠코리아"},
            {"ticker": "060480", "name": "포엔샤"},
        ]
    )
    diagnoses_cache = diagnose_held_positions_risk(
        cache_positions_df,
        cache_path=mock_cache_file,
    )
    assert len(diagnoses_cache) == 2
    diag_map = {d["ticker"]: d for d in diagnoses_cache}

    # 110% - 170% 범위의 실제 부채비율 확인 (0.0%로 폴백되지 않아야 함)
    assert 100.0 <= diag_map["225590"]["debt_ratio"] <= 200.0
    assert 100.0 <= diag_map["060480"]["debt_ratio"] <= 200.0
    assert diag_map["225590"]["debt_ratio"] == 130.0
    assert diag_map["060480"]["debt_ratio"] == 130.0
    # 자본잠식률은 정상 기업이므로 0.0% (정상)이어야 함
    assert diag_map["225590"]["impairment_ratio"] == 0.0
    assert diag_map["225590"]["impairment_display"] == "0.0% (정상)"
    assert diag_map["060480"]["impairment_ratio"] == 0.0
    assert diag_map["060480"]["impairment_display"] == "0.0% (정상)"

    # 2. 캐시에 없는 신규 종목의 DB financials 폴백 검증
    db_file = tmp_path / "test_fin.db"
    store = DataStore(db_file)
    store.initialize_schema()
    store.upsert_companies(
        [
            {
                "ticker": "999010",
                "corp_code": "00999010",
                "name": "클린테크",
                "market": "KOSDAQ",
                "sector": "IT",
                "listed_at": "2020-01-01",
                "fiscal_month": 12,
            },
            {
                "ticker": "999020",
                "corp_code": "00999020",
                "name": "잠식기업",
                "market": "KOSDAQ",
                "sector": "제조",
                "listed_at": "2020-01-01",
                "fiscal_month": 12,
            },
        ]
    )
    store.upsert_financials(
        [
            # 클린테크: 자본총계 1000억, 부채총계 1500억, 자본금 500억 (부채비율 150%, cs <= te 이므로 자본잠식 0.0%)
            {
                "corp_code": "00999010",
                "fiscal_year": 2026,
                "quarter": 2,
                "fs_type": "CFS",
                "revenue": 100.0,
                "gross_profit": 50.0,
                "op_income": 20.0,
                "net_income_owner": 15.0,
                "total_equity": 100_000_000_000.0,
                "total_liabilities": 150_000_000_000.0,
                "capital_stock": 50_000_000_000.0,
                "rcept_dt": "2026-08-14",
            },
            # 잠식기업: 자본총계 200억, 부채총계 600억, 자본금 500억 (부채비율 300%, 자본잠식률 60%)
            {
                "corp_code": "00999020",
                "fiscal_year": 2026,
                "quarter": 2,
                "fs_type": "CFS",
                "revenue": 50.0,
                "gross_profit": 10.0,
                "op_income": -10.0,
                "net_income_owner": -20.0,
                "total_equity": 20_000_000_000.0,
                "total_liabilities": 60_000_000_000.0,
                "capital_stock": 50_000_000_000.0,
                "rcept_dt": "2026-08-14",
            },
        ]
    )

    db_positions_df = pd.DataFrame(
        [
            {"ticker": "999010", "name": "클린테크"},
            {"ticker": "999020", "name": "잠식기업"},
        ]
    )
    diagnoses_db = diagnose_held_positions_risk(db_positions_df, db_path=db_file)
    db_map = {d["ticker"]: d for d in diagnoses_db}

    # 클린테크
    assert db_map["999010"]["debt_ratio"] == 150.0
    assert db_map["999010"]["impairment_ratio"] == 0.0
    assert db_map["999010"]["impairment_display"] == "0.0% (정상)"
    assert db_map["999010"]["severity"] == "NORMAL"

    # 잠식기업
    assert db_map["999020"]["debt_ratio"] == 300.0
    assert db_map["999020"]["impairment_ratio"] == 60.0
    assert db_map["999020"]["severity"] == "DANGER"
    assert "자본잠식 발생" in db_map["999020"]["issues"]


def test_tab4_renders_top20_preview_by_default(
    sample_dashboard_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tab 4 렌더링 시 버튼 클릭 없이도 최신 캐시 기반 Top 20 및 팩터 차트가 기본 표시되는지 검증합니다."""
    from quant_ko.dashboard import app as dashboard_app

    mock_top20_df = pd.DataFrame(
        [
            {
                "순위": 1,
                "종목코드": "000010",
                "종목명": "알파테크",
                "시가총액(억)": 300.0,
                "PER": 8.5,
                "PSR": 1.2,
                "POR": 7.0,
                "PGPR": 6.5,
                "부채비율(%)": 45.0,
                "밸류순위평균": 12.5,
                "성장순위평균": 8.0,
                "Total Rank": 1,
            },
            {
                "순위": 2,
                "종목코드": "000020",
                "종목명": "베타바이오",
                "시가총액(억)": 400.0,
                "PER": 12.0,
                "PSR": 2.1,
                "POR": 9.5,
                "PGPR": 8.0,
                "부채비율(%)": 30.0,
                "밸류순위평균": 15.0,
                "성장순위평균": 10.5,
                "Total Rank": 2,
            },
        ]
    )
    monkeypatch.setattr(
        dashboard_app,
        "load_cached_top20",
        lambda **kwargs: ("2026-10-31", 200, mock_top20_df),
    )

    class _MockTab4Streamlit:
        def __init__(self, button_clicked: bool = False) -> None:
            self.button_clicked = button_clicked
            self.subheaders: list[str] = []
            self.metrics: list[Any] = []
            self.markdowns: list[str] = []
            self.dataframes: list[Any] = []
            self.plotly_charts: list[Any] = []
            self.buttons_rendered: list[str] = []
            self.info_messages: list[str] = []
            self.success_messages: list[str] = []
            self.captions: list[str] = []

        def subheader(self, body: str, **kwargs: Any) -> None:
            self.subheaders.append(body)

        def columns(self, spec: int | list[int]) -> list[Any]:
            count = spec if isinstance(spec, int) else len(spec)

            class _MockCol:
                def __init__(self, st_ref: Any) -> None:
                    self.st = st_ref

                def metric(self, label: str, value: Any, delta: Any = None) -> None:
                    self.st.metric(label, value, delta)

            return [_MockCol(self) for _ in range(count)]

        def metric(self, label: str, value: Any, delta: Any = None) -> None:
            self.metrics.append((label, value, delta))

        def markdown(self, body: str, **kwargs: Any) -> None:
            self.markdowns.append(body)

        def caption(self, body: str, **kwargs: Any) -> None:
            self.captions.append(body)

        def button(self, label: str, **kwargs: Any) -> bool:
            self.buttons_rendered.append(label)
            return self.button_clicked

        def dataframe(self, data: Any, **kwargs: Any) -> None:
            self.dataframes.append(data)

        def plotly_chart(self, fig: Any, **kwargs: Any) -> None:
            self.plotly_charts.append(fig)

        def info(self, body: str) -> None:
            self.info_messages.append(body)

        def success(self, body: str) -> None:
            self.success_messages.append(body)

    mock_st = _MockTab4Streamlit(button_clicked=False)
    monkeypatch.setattr(dashboard_app, "st", mock_st)

    dashboard_app._render_tab4_universe_and_status(db_path=str(sample_dashboard_db))

    # 1. 재산출 버튼이 제공되는지 확인
    assert any("🔄 9대 팩터 Top 20 즉시 재산출 (전체 DB 재계산)" in b for b in mock_st.buttons_rendered)
    # 2. 버튼 미클릭 상태에서도 캐시된 Top 20 테이블이 즉시 표시되어야 함
    assert len(mock_st.dataframes) >= 1
    # 3. 팩터 프로파일 차트도 즉시 표시되어야 함
    assert len(mock_st.plotly_charts) >= 1


def test_diagnose_held_positions_risk_nonexistent_cache_fallback(
    tmp_path: Path,
) -> None:
    """존재하지 않는 캐시 경로 전달 시에도 에러 없이 정상 폴백되는지 검증합니다."""
    positions_df = pd.DataFrame([{"ticker": "000010", "name": "알파테크"}])
    non_existent_cache = tmp_path / "does_not_exist.pkl"
    diagnoses = diagnose_held_positions_risk(
        positions_df,
        db_path=tmp_path / "empty.db",
        cache_path=non_existent_cache,
    )
    assert len(diagnoses) == 1
    assert diagnoses[0]["debt_ratio"] == 0.0
    assert diagnoses[0]["impairment_ratio"] == 0.0
    assert diagnoses[0]["severity"] == "NORMAL"


def test_load_cached_top20_nonexistent_cache_fallback(
    tmp_path: Path,
) -> None:
    """존재하지 않는 캐시 경로 전달 시 load_cached_top20 이 예외 없이 폴백을 수행하는지 검증합니다."""
    non_existent_cache = tmp_path / "does_not_exist.pkl"
    latest_dt, count, df = load_cached_top20(
        cache_path=non_existent_cache,
        db_path=tmp_path / "empty.db",
    )
    assert latest_dt == "-"
    assert count == 0
    assert df.empty


def test_render_tab2_dynamic_metric_update(
    sample_dashboard_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tab 2 렌더링 시 필터 조건에 따라 상단 4대 메트릭이 동적으로 연동되는지 검증합니다."""
    from quant_ko.dashboard import app as dashboard_app

    store = DataStore(sample_dashboard_db)
    store.insert_order(
        {
            "rebalance_date": "2026-10-16",
            "ticker": "000020",
            "side": "BUY",
            "qty": 300,
            "price": 2100.0,
            "status": "FILLED",
            "filled_qty": 300,
            "env": "real",
        }
    )
    store.insert_order(
        {
            "rebalance_date": "2026-10-16",
            "ticker": "000020",
            "side": "BUY",
            "qty": 100,
            "price": 2100.0,
            "status": "FAILED",
            "filled_qty": 0,
            "env": "real",
        }
    )

    # 1. 기본 ALL / ALL 선택 시 (실전 주문 총 3건: BUY FILLED 1건, SELL FILLED 1건, FAILED 1건)
    mock_st1 = _MockStreamlit()
    monkeypatch.setattr(dashboard_app, "st", mock_st1)
    dashboard_app._render_tab2_trade_logs(db_path=str(sample_dashboard_db))

    metrics_dict1 = {label: val for label, val, _ in mock_st1.metrics}
    assert metrics_dict1["총 주문 건수"] == "3건"
    assert metrics_dict1["매수 체결/주문"] == "1건"
    assert metrics_dict1["매도 체결/주문"] == "1건"
    assert metrics_dict1["실패/거부"] == "1건"

    # 2. 매매구분 SELL 선택 시 동적 메트릭 변경 검증 (총 1건, 매수 0건, 매도 1건, 실패 0건)
    class _MockStreamlitSell(_MockStreamlit):
        def selectbox(self, label: str, options: list[Any], **kwargs: Any) -> Any:
            self.selectboxes.append(label)
            if label == "매매 구분 필터":
                return "SELL"
            return options[0]

    mock_st2 = _MockStreamlitSell()
    monkeypatch.setattr(dashboard_app, "st", mock_st2)
    dashboard_app._render_tab2_trade_logs(db_path=str(sample_dashboard_db))

    metrics_dict2 = {label: val for label, val, _ in mock_st2.metrics}
    assert metrics_dict2["총 주문 건수"] == "1건"
    assert metrics_dict2["매수 체결/주문"] == "0건"
    assert metrics_dict2["매도 체결/주문"] == "1건"
    assert metrics_dict2["실패/거부"] == "0건"

def test_actual_trade_logs_deduplication_and_name_fallback(tmp_path: Path) -> None:
    """배포 환경 빈 DB에서 시드 로드 시 중복 방지 및 기업명 폴백 매핑이 정상 동작하는지 검증합니다."""
    db_path = tmp_path / "quant_ko.db"
    store = DataStore(db_path)
    store.initialize_schema()

    # 1. 거래기록 조회 (10/30 20건 + 11/02 캐치업 체결 1건 = 총 21건 자동 로드)
    df = load_actual_trade_logs(db_path=db_path)
    assert len(df) == 21
    assert df["종목코드"].nunique() == 20

    # 2. 11/02 DH오토리드 당일 체결 내역 및 한글 종목명 정상 표기 검증
    dh_today = df[(df["종목코드"] == "290120") & (df["주문일시"] == "2026-11-02")]
    assert len(dh_today) == 1
    assert dh_today.iloc[0]["종목명"] == "DH오토리드"
    assert dh_today.iloc[0]["체결상태"] == "FILLED"
    assert dh_today.iloc[0]["체결수량"] == 74

    # 3. 모든 종목의 종목명이 종목코드가 아닌 실제 종목명으로 매핑되었는지 검증
    assert (df["종목코드"] == df["종목명"]).sum() == 0

    # 4. 중복 INSERT 시도 시에도 중복 레코드가 생기지 않는지 검증
    store.insert_order({
        "rebalance_date": "2026-11-02",
        "ticker": "290120",
        "side": "BUY",
        "qty": 74,
        "price": 1924.0,
        "status": "FILLED",
        "filled_qty": 74,
        "env": "real",
    })
    df_after = load_actual_trade_logs(db_path=db_path)
    assert len(df_after) == 21

