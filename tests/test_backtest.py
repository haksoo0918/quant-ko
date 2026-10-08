"""Tests for backtest engine, calendar, metrics, and reporting."""

import pytest

from quant_ko.backtest.calendar import RebalanceEvent, get_rebalance_schedule
from quant_ko.backtest.engine import execute_rebalance


def test_rebalance_calendar_schedule():
    trading_days = [
        "2024-03-28",
        "2024-03-29",
        "2024-04-01",
        "2024-04-02",
        "2024-05-30",
        "2024-05-31",
        "2024-06-03",
        "2024-08-29",
        "2024-08-30",
        "2024-09-02",
        "2024-11-28",
        "2024-11-29",
        "2024-12-02",
    ]

    events = get_rebalance_schedule(trading_days)
    assert len(events) == 4

    assert events[0] == RebalanceEvent(
        rebalance_date="2024-04-01",
        prior_date="2024-03-29",
        period_label="2024-04",
    )
    assert events[1] == RebalanceEvent(
        rebalance_date="2024-05-31",
        prior_date="2024-05-30",
        period_label="2024-05",
    )
    assert events[2] == RebalanceEvent(
        rebalance_date="2024-08-30",
        prior_date="2024-08-29",
        period_label="2024-08",
    )
    assert events[3] == RebalanceEvent(
        rebalance_date="2024-11-29",
        prior_date="2024-11-28",
        period_label="2024-11",
    )


def test_execute_rebalance_differential_trading():
    current_cash = 1_000_000.0
    current_positions = {"000010": 100, "000020": 500}
    prices = {
        "000010": 20_000.0,
        "000020": 10_000.0,
        "000030": 10_000.0,
    }
    # 000010 value = 2,000,000; 000020 value = 5,000,000; cash = 1,000,000 -> Total Equity = 8,000,000
    # Target 50% for 000010 and 50% for 000030. 000020 is eliminated.
    target_weights = {
        "000010": 0.5,
        "000030": 0.5,
    }

    result = execute_rebalance(
        date="2024-04-01",
        current_cash=current_cash,
        current_positions=current_positions,
        target_weights=target_weights,
        prices=prices,
        cost_rate=0.003,
    )

    # 000020 should be sold completely: 500 shares * 10,000 = 5,000,000. Fee = 15,000.
    # 000010 should buy delta: held 100, target 200 -> buy 100 shares * 20,000 = 2,000,000. Fee = 6,000.
    # 000030 should buy target: target ~ 400 shares, capped by remaining cash if needed.
    assert "000020" not in result.positions or result.positions["000020"] == 0
    assert result.positions["000010"] == 200
    assert result.positions["000030"] > 0
    assert result.cash >= 0.0

    # Check trades list
    tickers_traded = {t.ticker for t in result.trades}
    assert tickers_traded == {"000010", "000020", "000030"}

    sell_trade = next(t for t in result.trades if t.ticker == "000020")
    assert sell_trade.side == "SELL"
    assert sell_trade.shares == 500
    assert sell_trade.trade_value == 5_000_000.0
    assert sell_trade.fee == 15_000.0


def test_in_period_events_liquidation_and_delisting():
    from quant_ko.backtest.engine import EventTracker

    # Tracker initialized with held positions
    tracker = EventTracker()
    positions = {"000010": 100, "000020": 200, "000030": 300}
    cash = 1_000_000.0

    # Day 1:
    # 000010 is designated as "관리"
    # 000020 is designated as "거래정지"
    # Prices on Day 1:
    prices_day1 = {"000010": 10_000.0, "000020": 5_000.0, "000030": 2_000.0}
    cash, positions, trades = tracker.process_day(
        date="2024-04-15",
        cash=cash,
        positions=positions,
        prices=prices_day1,
        active_designations={"000010": {"관리"}, "000020": {"거래정지"}},
        suspended_tickers={"000020"},
        delisted_tickers=set(),
    )
    # On Day 1 (the day designation starts), it should flag them for liquidation on the NEXT available trading day.
    # Therefore, no trades on Day 1 yet.
    assert len(trades) == 0
    assert "000010" in positions
    assert "000020" in positions

    # Day 2:
    # 000010 is tradable -> should be liquidated at close price (say 9,000)
    # 000020 is still suspended -> cannot be sold yet
    # 000030 is suddenly delisted (delisted_at <= 2024-04-16) -> -100% loss (0 proceeds)
    prices_day2 = {"000010": 9_000.0, "000020": 5_000.0, "000030": 0.0}
    cash, positions, trades = tracker.process_day(
        date="2024-04-16",
        cash=cash,
        positions=positions,
        prices=prices_day2,
        active_designations={"000010": {"관리"}, "000020": {"거래정지"}},
        suspended_tickers={"000020"},
        delisted_tickers={"000030"},
    )

    # 000010 liquidated: 100 * 9,000 = 900,000. Fee = 900,000 * 0.003 = 2,700. Net = 897,300.
    assert "000010" not in positions
    assert positions["000020"] == 200
    assert "000030" not in positions  # Delisted, wiped out
    assert cash == 1_000_000.0 + 897_300.0

    # 1 liquidation trade occurred for 000010
    assert len(trades) == 1
    assert trades[0].ticker == "000010"
    assert trades[0].shares == 100
    assert trades[0].price == 9_000.0

    # Day 3:
    # 000020 suspension lifted! Price = 4,000
    prices_day3 = {"000020": 4_000.0}
    cash, positions, trades = tracker.process_day(
        date="2024-04-17",
        cash=cash,
        positions=positions,
        prices=prices_day3,
        active_designations={"000020": {"거래정지"}},
        suspended_tickers=set(),  # suspension lifted!
        delisted_tickers=set(),
    )
    assert len(trades) == 1
    assert trades[0].ticker == "000020"


def test_performance_metrics_calculation():
    import pandas as pd

    from quant_ko.backtest.metrics import calculate_metrics

    # Create daily equity history across two years
    equity_df = pd.DataFrame(
        [
            {"date": "2023-01-02", "equity": 10_000_000.0},
            {"date": "2023-06-30", "equity": 12_000_000.0},  # peak
            {"date": "2023-12-29", "equity": 9_000_000.0},  # trough, mdd = -25%
            {"date": "2024-06-30", "equity": 11_000_000.0},
            {"date": "2024-12-31", "equity": 15_000_000.0},
        ]
    )

    rebalance_records = [
        {"rebalance_date": "2023-04-03", "period_label": "2023-04", "turnover_rate": 0.5},
        {"rebalance_date": "2023-05-31", "period_label": "2023-05", "turnover_rate": 0.3},
        {"rebalance_date": "2023-08-31", "period_label": "2023-08", "turnover_rate": 0.2},
        {"rebalance_date": "2023-11-30", "period_label": "2023-11", "turnover_rate": 0.4},
        {"rebalance_date": "2024-04-01", "period_label": "2024-04", "turnover_rate": 0.3},
    ]

    metrics = calculate_metrics(
        equity_history=equity_df,
        rebalance_records=rebalance_records,
        initial_capital=10_000_000.0,
        risk_free_rate=0.035,
    )

    assert metrics.initial_capital == 10_000_000.0
    assert metrics.final_equity == 15_000_000.0
    assert pytest.approx(metrics.total_return, 0.001) == 0.50
    assert metrics.mdd == pytest.approx(-0.25, 0.001)
    assert metrics.mdd_peak_date == "2023-06-30"
    assert metrics.mdd_trough_date == "2023-12-29"
    assert metrics.cagr > 0
    assert metrics.avg_turnover_rate == pytest.approx(0.34, 0.01)
    assert 2023 in metrics.yearly_returns
    assert 2024 in metrics.yearly_returns
    # 2023 went from 10M to 9M -> negative return (-10%)
    assert metrics.yearly_returns[2023] < 0
    # 2024 went from 9M to 15M -> positive return (+66.7%)
    assert metrics.yearly_returns[2024] > 0
    assert metrics.win_rate_yearly == 0.5


def test_compare_benchmark():
    import pandas as pd

    from quant_ko.backtest.metrics import compare_benchmark

    port_df = pd.DataFrame(
        [
            {"date": "2023-01-02", "equity": 10_000_000.0},
            {"date": "2023-01-03", "equity": 10_200_000.0},
            {"date": "2023-01-04", "equity": 10_100_000.0},
            {"date": "2023-01-05", "equity": 10_500_000.0},
        ]
    )

    bench_df = pd.DataFrame(
        [
            {"date": "2023-01-02", "close": 1000.0},
            {"date": "2023-01-03", "close": 1010.0},
            {"date": "2023-01-04", "close": 1005.0},
            {"date": "2023-01-05", "close": 1020.0},
        ]
    )

    comp = compare_benchmark(port_df, bench_df, benchmark_name="KOSDAQ")
    assert comp.benchmark_name == "KOSDAQ"
    assert pytest.approx(comp.benchmark_return, 0.001) == 0.02
    assert comp.correlation > 0.9


def test_generate_report_markdown_and_text():
    from quant_ko.backtest.metrics import BenchmarkComparison, PerformanceMetrics
    from quant_ko.backtest.report import generate_report

    metrics = PerformanceMetrics(
        initial_capital=10_000_000.0,
        final_equity=15_000_000.0,
        total_return=0.50,
        cagr=0.225,
        mdd=-0.25,
        mdd_peak_date="2023-06-30",
        mdd_trough_date="2023-12-29",
        annualized_volatility=0.18,
        sharpe_ratio=1.05,
        win_rate_rebalance=0.75,
        win_rate_yearly=1.0,
        avg_turnover_rate=0.34,
        yearly_returns={2023: 0.15, 2024: 0.30},
    )

    bench = BenchmarkComparison(
        benchmark_name="KOSDAQ",
        benchmark_return=0.10,
        benchmark_cagr=0.048,
        benchmark_mdd=-0.32,
        benchmark_sharpe=0.12,
        correlation=0.65,
        alpha=0.15,
        beta=0.75,
    )

    md_report = generate_report(metrics, benchmarks=[bench], format_type="markdown")
    assert "# Backtest Performance Report" in md_report
    assert "50.00%" in md_report
    assert "-25.00%" in md_report
    assert "2023-06-30" in md_report
    assert "KOSDAQ" in md_report
    assert "1.05" in md_report

    text_report = generate_report(metrics, benchmarks=[bench], format_type="text")
    assert "Backtest Performance Report" in text_report
    assert "50.00%" in text_report


def test_backtest_engine_full_run():
    from quant_ko.backtest.engine import BacktestEngine
    from quant_ko.data.store import DataStore

    store = DataStore(":memory:")
    store.initialize_schema()

    # Setup 4 valid companies
    companies = [
        {
            "ticker": "000010",
            "corp_code": "00000010",
            "name": "기업A",
            "sector": "제조업",
            "fiscal_month": 12,
        },
        {
            "ticker": "000020",
            "corp_code": "00000020",
            "name": "기업B",
            "sector": "IT",
            "fiscal_month": 12,
        },
        {
            "ticker": "000030",
            "corp_code": "00000030",
            "name": "기업C",
            "sector": "바이오",
            "fiscal_month": 12,
        },
        {
            "ticker": "000040",
            "corp_code": "00000040",
            "name": "기업D",
            "sector": "화학",
            "fiscal_month": 12,
        },
    ]
    store.upsert_companies(companies)

    # Financials filed on 2024-03-20 (available before April rebalance)
    fin_records = []
    for c in companies:
        corp = c["corp_code"]
        # 4 quarters for 2023 to compute TTM (Q4 is annual report cumulative total)
        for q, rev, op, net in [
            (1, 100e8, 20e8, 15e8),
            (2, 110e8, 22e8, 16e8),
            (3, 120e8, 24e8, 18e8),
            (4, 460e8, 92e8, 69e8),
        ]:
            fin_records.append(
                {
                    "corp_code": corp,
                    "fiscal_year": 2023,
                    "quarter": q,
                    "fs_type": "CFS",
                    "revenue": rev,
                    "gross_profit": rev * 0.4,
                    "op_income": op,
                    "net_income_owner": net,
                    "total_liabilities": 50e8,
                    "total_equity": 100e8,
                    "capital_stock": 20e8,
                    "rcept_dt": "2024-03-20",
                }
            )
        # Prior year 2022 quarters for YoY growth
        for q, rev, op, net in [
            (1, 80e8, 15e8, 10e8),
            (2, 90e8, 16e8, 11e8),
            (3, 100e8, 18e8, 12e8),
            (4, 380e8, 69e8, 48e8),
        ]:
            fin_records.append(
                {
                    "corp_code": corp,
                    "fiscal_year": 2022,
                    "quarter": q,
                    "fs_type": "CFS",
                    "revenue": rev,
                    "gross_profit": rev * 0.4,
                    "op_income": op,
                    "net_income_owner": net,
                    "total_liabilities": 50e8,
                    "total_equity": 100e8,
                    "capital_stock": 20e8,
                    "rcept_dt": "2023-03-20",
                }
            )
    store.upsert_financials(fin_records)

    # Daily prices from 2024-03-01 to 2024-06-05
    # Trading days: 2024-03-28, 2024-03-29, 2024-04-01, 2024-05-10, 2024-05-13, 2024-05-30, 2024-05-31, 2024-06-03
    trading_dates = [
        "2024-03-28",
        "2024-03-29",  # prior date for April
        "2024-04-01",  # April rebalance
        "2024-05-10",  # designation date
        "2024-05-13",  # liquidation date
        "2024-05-30",  # prior date for May
        "2024-05-31",  # May rebalance
        "2024-06-03",
    ]

    prices = []
    for d in trading_dates:
        for c in companies:
            prices.append(
                {
                    "ticker": c["ticker"],
                    "date": d,
                    "close": 10_000.0,
                    "market_cap": 200_000_000.0,
                    "trading_value": 500_000_000.0,
                }
            )
    store.upsert_daily_prices(prices)

    # In-period event: 000020 designated as 관리종목 on 2024-05-10
    store.upsert_designations(
        [{"ticker": "000020", "type": "관리", "start_date": "2024-05-10", "end_date": None}]
    )

    engine = BacktestEngine(
        store=store,
        initial_capital=10_000_000.0,
        cost_rate=0.003,
        top_n=20,
    )

    result = engine.run(start_date="2024-04-01", end_date="2024-06-03")

    assert result.metrics.initial_capital == 10_000_000.0
    assert result.metrics.final_equity > 0
    assert len(result.rebalance_records) >= 1
    assert len(result.equity_history) > 0

    # Verify that in-period liquidation of 000020 was handled
    traded_tickers = {t.ticker for t in result.trades}
    assert "000020" in traded_tickers

    # Verify that report can be generated
    report_text = result.generate_report(format_type="text")
    assert "Backtest Performance Report" in report_text


def test_backtest_engine_custom_capital_and_benchmark():
    import pandas as pd

    from quant_ko.backtest.engine import BacktestEngine
    from quant_ko.data.store import DataStore

    store = DataStore(":memory:")
    store.initialize_schema()

    # Setup 2 valid companies
    companies = [
        {
            "ticker": "000010",
            "corp_code": "00000010",
            "name": "기업A",
            "sector": "제조업",
            "fiscal_month": 12,
        },
        {
            "ticker": "000020",
            "corp_code": "00000020",
            "name": "기업B",
            "sector": "IT",
            "fiscal_month": 12,
        },
    ]
    store.upsert_companies(companies)

    fin_records = []
    for c in companies:
        corp = c["corp_code"]
        for q, rev, op, net in [
            (1, 100e8, 20e8, 15e8),
            (2, 110e8, 22e8, 16e8),
            (3, 120e8, 24e8, 18e8),
            (4, 460e8, 92e8, 69e8),
        ]:
            fin_records.append(
                {
                    "corp_code": corp,
                    "fiscal_year": 2023,
                    "quarter": q,
                    "fs_type": "CFS",
                    "revenue": rev,
                    "gross_profit": rev * 0.4,
                    "op_income": op,
                    "net_income_owner": net,
                    "total_liabilities": 50e8,
                    "total_equity": 100e8,
                    "capital_stock": 20e8,
                    "rcept_dt": "2024-03-20",
                }
            )
        for q, rev, op, net in [
            (1, 80e8, 15e8, 10e8),
            (2, 90e8, 16e8, 11e8),
            (3, 100e8, 18e8, 12e8),
            (4, 380e8, 69e8, 48e8),
        ]:
            fin_records.append(
                {
                    "corp_code": corp,
                    "fiscal_year": 2022,
                    "quarter": q,
                    "fs_type": "CFS",
                    "revenue": rev,
                    "gross_profit": rev * 0.4,
                    "op_income": op,
                    "net_income_owner": net,
                    "total_liabilities": 50e8,
                    "total_equity": 100e8,
                    "capital_stock": 20e8,
                    "rcept_dt": "2023-03-20",
                }
            )
    store.upsert_financials(fin_records)

    trading_dates = ["2024-03-28", "2024-03-29", "2024-04-01", "2024-04-02"]
    prices = []
    for d in trading_dates:
        for c in companies:
            prices.append(
                {
                    "ticker": c["ticker"],
                    "date": d,
                    "close": 50_000.0,
                    "market_cap": 200_000_000.0,
                    "trading_value": 500_000_000.0,
                }
            )
    store.upsert_daily_prices(prices)

    # Benchmark daily prices
    benchmark_df = pd.DataFrame(
        [
            {"date": "2024-04-01", "close": 800.0},
            {"date": "2024-04-02", "close": 810.0},
        ]
    )

    # Test initial capital = 2,000,000 KRW
    engine = BacktestEngine(
        store=store,
        initial_capital=2_000_000.0,
        cost_rate=0.003,
        top_n=20,
    )

    result = engine.run(
        start_date="2024-04-01",
        end_date="2024-04-02",
        benchmark_df=benchmark_df,
        benchmark_name="KOSDAQ",
    )

    assert result.metrics.initial_capital == 2_000_000.0
    assert result.metrics.final_equity > 0
    assert len(result.benchmarks) == 1
    assert result.benchmarks[0].benchmark_name == "KOSDAQ"
    assert pytest.approx(result.benchmarks[0].benchmark_return, 0.001) == 0.0125

    # Check report format in markdown
    md_report = result.generate_report(format_type="markdown")
    assert "2,000,000 KRW" in md_report
    assert "KOSDAQ" in md_report
