import pandas as pd
import pytest

from quant_ko.data.store import DataStore
from quant_ko.strategy.universe import filter_universe


@pytest.fixture
def store():
    ds = DataStore(":memory:")
    ds.initialize_schema()
    yield ds
    ds.close()


def test_filter_universe_exclusions(store):
    # Setup test companies:
    # 1. Normal stock
    # 2. Preferred stock
    # 3. SPAC
    # 4. Chinese company
    # 5. Holding company
    # 6. Non-Dec fiscal month
    # 7. Active designation (관리종목)
    companies = [
        {
            "ticker": "000010",
            "corp_code": "00000010",
            "name": "정상기업",
            "sector": "제조업",
            "fiscal_month": 12,
        },
        {
            "ticker": "000015",
            "corp_code": "00000015",
            "name": "정상우",
            "sector": "제조업",
            "is_preferred": 1,
            "fiscal_month": 12,
        },
        {
            "ticker": "000020",
            "corp_code": "00000020",
            "name": "미래스팩1호",
            "sector": "금융",
            "is_spac": 1,
            "fiscal_month": 12,
        },
        {
            "ticker": "900010",
            "corp_code": "00000030",
            "name": "차이나그레이트",
            "sector": "기타",
            "fiscal_month": 12,
        },
        {
            "ticker": "000040",
            "corp_code": "00000040",
            "name": "카카오홀딩스",
            "sector": "금융업",
            "fiscal_month": 12,
        },
        {
            "ticker": "000050",
            "corp_code": "00000050",
            "name": "3월결산사",
            "sector": "제조업",
            "fiscal_month": 3,
        },
        {
            "ticker": "000060",
            "corp_code": "00000060",
            "name": "관리기업",
            "sector": "제조업",
            "fiscal_month": 12,
        },
    ]
    store.upsert_companies(companies)

    # Active designation for 000060
    store.upsert_designations(
        [{"ticker": "000060", "type": "관리", "start_date": "2024-01-01", "end_date": None}]
    )

    # Prices for all tickers so market cap / liquidity exists
    prices = []
    for comp in companies:
        t = comp["ticker"]
        for day in range(1, 25):
            d_str = f"2024-03-{day:02d}"
            prices.append(
                {
                    "ticker": t,
                    "date": d_str,
                    "close": 1000.0,
                    "market_cap": 50_000_000_000.0,
                    "trading_value": 300_000_000.0,
                }
            )
    store.upsert_daily_prices(prices)

    # Healthy financials for all
    financials = []
    for comp in companies:
        c = comp["corp_code"]
        financials.append(
            {
                "corp_code": c,
                "fiscal_year": 2023,
                "quarter": 4,
                "fs_type": "CFS",
                "revenue": 1000.0,
                "gross_profit": 500.0,
                "op_income": 100.0,
                "net_income_owner": 80.0,
                "total_liabilities": 50.0,
                "total_equity": 100.0,
                "capital_stock": 20.0,
                "rcept_dt": "20240315",
            }
        )
    store.upsert_financials(financials)

    # Filter universe as of 2024-04-01
    universe_df = filter_universe(store, as_of_date="2024-04-01")

    # Only "정상기업" (000010) should survive all exclusion filters
    assert len(universe_df) == 1
    assert universe_df.iloc[0]["ticker"] == "000010"


def test_filter_universe_market_cap_and_liquidity(store):
    # Setup 10 companies with market caps 10B, 20B, 30B, ... 100B
    # Bottom 20% should be 10B and 20B (the 2 smallest).
    # But one of them has trading value < 200M KRW -> should be filtered out by liquidity filter.
    companies = []
    prices = []
    financials = []
    for i in range(1, 11):
        ticker = f"000{i:02d}0"  # KRX common stocks end with 0
        corp = f"corp_{i:02d}"
        companies.append(
            {"ticker": ticker, "corp_code": corp, "name": f"기업{i}", "fiscal_month": 12}
        )
        # Trading value: ticker 000010 has 100M KRW (< 200M), others have 300M
        tv = 100_000_000.0 if i == 1 else 300_000_000.0
        mcap = i * 10_000_000_000.0  # 10B to 100B
        prices.append(
            {
                "ticker": ticker,
                "date": "2024-04-01",
                "close": 1000.0,
                "market_cap": mcap,
                "trading_value": tv,
            }
        )
        financials.append(
            {
                "corp_code": corp,
                "fiscal_year": 2023,
                "quarter": 4,
                "fs_type": "CFS",
                "revenue": 1000.0,
                "gross_profit": 500.0,
                "op_income": 100.0,
                "net_income_owner": 80.0,
                "total_liabilities": 50.0,
                "total_equity": 100.0,
                "capital_stock": 20.0,
                "rcept_dt": "20240315",
            }
        )

    store.upsert_companies(companies)
    store.upsert_daily_prices(prices)
    store.upsert_financials(financials)

    # Bottom 20% of 10 companies = bottom 2 (000010 and 000020)
    # 000010 fails liquidity (< 200M)
    # Only 000020 should survive!
    universe_df = filter_universe(store, as_of_date="2024-04-01")
    assert len(universe_df) == 1
    assert universe_df.iloc[0]["ticker"] == "000020"


def test_filter_universe_financial_health_and_profitability(store):
    # Setup 4 small cap companies with adequate liquidity:
    # 1. Healthy & Profitable (survives)
    # 2. Debt ratio > 200% (fails health)
    # 3. Capital impairment > 0% (fails health)
    # 4. Negative quarterly op_income (fails profitability)
    # 5. Negative TTM net income (fails profitability)
    companies = [
        {"ticker": "000110", "corp_code": "c_101", "name": "우량소형", "fiscal_month": 12},
        {"ticker": "000120", "corp_code": "c_102", "name": "고부채기업", "fiscal_month": 12},
        {"ticker": "000130", "corp_code": "c_103", "name": "자본잠식기업", "fiscal_month": 12},
        {"ticker": "000140", "corp_code": "c_104", "name": "적자기업", "fiscal_month": 12},
    ]
    store.upsert_companies(companies)

    prices = []
    for c in companies:
        prices.append(
            {
                "ticker": c["ticker"],
                "date": "2024-04-01",
                "close": 1000.0,
                "market_cap": 10_000_000_000.0,
                "trading_value": 300_000_000.0,
            }
        )
    store.upsert_daily_prices(prices)

    financials = [
        # 1. Healthy: debt = 100/100 (100% <= 200%), equity 100 >= stock 50 (impairment <= 0%), op > 0, net > 0
        {
            "corp_code": "c_101",
            "fiscal_year": 2023,
            "quarter": 4,
            "fs_type": "CFS",
            "revenue": 1000.0,
            "gross_profit": 500.0,
            "op_income": 100.0,
            "net_income_owner": 50.0,
            "total_liabilities": 100.0,
            "total_equity": 100.0,
            "capital_stock": 50.0,
            "rcept_dt": "20240315",
        },
        # 2. High debt: liabilities 300, equity 100 -> debt ratio 300% > 200%
        {
            "corp_code": "c_102",
            "fiscal_year": 2023,
            "quarter": 4,
            "fs_type": "CFS",
            "revenue": 1000.0,
            "gross_profit": 500.0,
            "op_income": 100.0,
            "net_income_owner": 50.0,
            "total_liabilities": 300.0,
            "total_equity": 100.0,
            "capital_stock": 50.0,
            "rcept_dt": "20240315",
        },
        # 3. Capital impairment: equity 40 < stock 50 -> impairment ratio 20% > 0%
        {
            "corp_code": "c_103",
            "fiscal_year": 2023,
            "quarter": 4,
            "fs_type": "CFS",
            "revenue": 1000.0,
            "gross_profit": 500.0,
            "op_income": 100.0,
            "net_income_owner": 50.0,
            "total_liabilities": 50.0,
            "total_equity": 40.0,
            "capital_stock": 50.0,
            "rcept_dt": "20240315",
        },
        # 4. Loss: op_income -10 <= 0
        {
            "corp_code": "c_104",
            "fiscal_year": 2023,
            "quarter": 4,
            "fs_type": "CFS",
            "revenue": 1000.0,
            "gross_profit": 500.0,
            "op_income": -10.0,
            "net_income_owner": -15.0,
            "total_liabilities": 50.0,
            "total_equity": 100.0,
            "capital_stock": 50.0,
            "rcept_dt": "20240315",
        },
    ]
    store.upsert_financials(financials)

    # Use market_cap_quantile=1.0 to test health/profitability isolation
    res = filter_universe(store, as_of_date="2024-04-01", market_cap_quantile=1.0)
    assert len(res) == 1
    assert res.iloc[0]["ticker"] == "000110"


def test_score_and_select_factors_and_turnaround():
    from quant_ko.strategy.scoring import score_and_select

    # 3 mock universe stocks:
    # Stock A: Turnaround in op_income (prev <= 0, latest > 0), low market cap
    # Stock B: High normal YoY growth in op_income (100%), higher market cap
    # Stock C: Modest growth (20%), lowest PER
    data = [
        {
            "ticker": "000010",
            "market_cap": 20_000_000_000.0,
            "net_income_owner_ttm": 2_000_000_000.0,  # PER = 10
            "revenue_ttm": 20_000_000_000.0,  # PSR = 1.0
            "op_income_ttm": 2_500_000_000.0,  # POR = 8
            "gross_profit_ttm": 5_000_000_000.0,  # PGPR = 4
            "net_income_owner_yoy": 0.5,
            "net_income_owner_turnaround": False,
            "op_income_yoy": 0.4,
            "op_income_turnaround": True,  # Turnaround!
            "gross_profit_yoy": 0.3,
            "gross_profit_turnaround": False,
            "revenue_yoy": 0.2,
            "revenue_turnaround": False,
        },
        {
            "ticker": "000020",
            "market_cap": 50_000_000_000.0,
            "net_income_owner_ttm": 2_500_000_000.0,  # PER = 20
            "revenue_ttm": 25_000_000_000.0,  # PSR = 2.0
            "op_income_ttm": 3_000_000_000.0,  # POR = 16.67
            "gross_profit_ttm": 6_000_000_000.0,  # PGPR = 8.33
            "net_income_owner_yoy": 1.2,
            "net_income_owner_turnaround": False,
            "op_income_yoy": 1.5,  # 150% growth, but NOT turnaround
            "op_income_turnaround": False,
            "gross_profit_yoy": 1.0,
            "gross_profit_turnaround": False,
            "revenue_yoy": 0.8,
            "revenue_turnaround": False,
        },
        {
            "ticker": "000030",
            "market_cap": 10_000_000_000.0,
            "net_income_owner_ttm": 2_000_000_000.0,  # PER = 5 (best value)
            "revenue_ttm": 20_000_000_000.0,  # PSR = 0.5
            "op_income_ttm": 2_000_000_000.0,  # POR = 5
            "gross_profit_ttm": 5_000_000_000.0,  # PGPR = 2
            "net_income_owner_yoy": 0.1,
            "net_income_owner_turnaround": False,
            "op_income_yoy": 0.1,
            "op_income_turnaround": False,
            "gross_profit_yoy": 0.1,
            "gross_profit_turnaround": False,
            "revenue_yoy": 0.1,
            "revenue_turnaround": False,
        },
    ]
    df = pd.DataFrame(data)

    selected = score_and_select(df, top_n=2)

    assert len(selected) == 2
    # Verify equal weighting: 2 selected -> 0.5 each
    assert pytest.approx(selected["weight"].iloc[0]) == 0.5
    assert pytest.approx(selected["weight"].iloc[1]) == 0.5

    # Check that op_income rank of 000010 (turnaround) is 1, beating 000020 (150% non-turnaround)
    row_10 = selected[selected["ticker"] == "000010"].iloc[0]
    assert row_10["rank_op_income_yoy"] == 1

    # Check columns present in output
    assert "total_rank" in selected.columns
    assert "per" in selected.columns
    assert "psr" in selected.columns
    assert "por" in selected.columns
    assert "pgpr" in selected.columns


def test_score_and_select_tie_breaker_and_selection_limits():
    from quant_ko.strategy.scoring import score_and_select

    # 25 stocks:
    # Test top_n = 20 selection limit
    # Test tie-breaker: if two stocks have the exact same total_rank, smaller market_cap is chosen first
    records = []
    for i in range(1, 26):
        records.append(
            {
                "ticker": f"00{i:04d}",
                # Let market cap vary
                "market_cap": i * 1_000_000_000.0,
                # Set all metrics identical so total_rank will depend on market_cap
                "net_income_owner_ttm": 1_000_000_000.0,
                "revenue_ttm": 5_000_000_000.0,
                "op_income_ttm": 1_000_000_000.0,
                "gross_profit_ttm": 2_000_000_000.0,
                "net_income_owner_yoy": 0.2,
                "net_income_owner_turnaround": False,
                "op_income_yoy": 0.2,
                "op_income_turnaround": False,
                "gross_profit_yoy": 0.2,
                "gross_profit_turnaround": False,
                "revenue_yoy": 0.2,
                "revenue_turnaround": False,
            }
        )
    df = pd.DataFrame(records)

    selected = score_and_select(df, top_n=20)
    assert len(selected) == 20
    assert pytest.approx(selected["weight"].iloc[0]) == 1.0 / 20

    # Stock 1 has smaller market cap than Stock 25, so Stock 1 is ranked 1
    assert selected.iloc[0]["ticker"] == "000001"
    assert selected.iloc[-1]["ticker"] == "000020"
