"""Unit tests for small-cap universe filtering bugs and edge cases."""

import pytest

from quant_ko.data.collector import DataCollector
from quant_ko.data.store import DataStore
from quant_ko.strategy.universe import filter_universe


@pytest.fixture
def store() -> DataStore:
    ds = DataStore(":memory:")
    ds.initialize_schema()
    yield ds
    ds.close()


def test_filter_universe_excludes_konex(store: DataStore) -> None:
    companies = [
        {
            "ticker": "000010",
            "corp_code": "00000010",
            "name": "코스닥기업",
            "market": "KOSDAQ",
            "sector": "제조업",
            "fiscal_month": 12,
        },
        {
            "ticker": "000020",
            "corp_code": "00000020",
            "name": "코넥스기업",
            "market": "KONEX",
            "sector": "제조업",
            "fiscal_month": 12,
        },
    ]
    store.upsert_companies(companies)

    prices = [
        {
            "ticker": "000010",
            "date": "2024-04-01",
            "close": 1000.0,
            "market_cap": 10_000_000_000.0,
            "trading_value": 300_000_000.0,
        },
        {
            "ticker": "000020",
            "date": "2024-04-01",
            "close": 1000.0,
            "market_cap": 5_000_000_000.0,
            "trading_value": 300_000_000.0,
        },
    ]
    store.upsert_daily_prices(prices)

    financials = [
        {
            "corp_code": "00000010",
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
        },
        {
            "corp_code": "00000020",
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
        },
    ]
    store.upsert_financials(financials)

    universe_df = filter_universe(store, as_of_date="2024-04-01", market_cap_quantile=1.0)
    assert list(universe_df["ticker"]) == ["000010"]

    collector = DataCollector(store=store)
    pool = collector.identify_small_cap_pool(as_of_date="2024-04-01", quantile=1.0)
    assert pool == ["000010"]


def test_filter_universe_prevents_double_cut_on_prefiltered_prices(store: DataStore) -> None:
    # 50 valid companies in store, but daily_prices only has 10 pre-filtered small-cap stocks
    companies = []
    for i in range(1, 51):
        ticker = f"{i:05d}0"
        corp = f"corp_{i:04d}"
        companies.append(
            {
                "ticker": ticker,
                "corp_code": corp,
                "name": f"기업{i}",
                "market": "KOSDAQ",
                "sector": "제조업",
                "fiscal_month": 12,
            }
        )
    store.upsert_companies(companies)

    prices = []
    financials = []
    for i in range(1, 11):
        ticker = f"{i:05d}0"
        corp = f"corp_{i:04d}"
        prices.append(
            {
                "ticker": ticker,
                "date": "2024-04-01",
                "close": 1000.0,
                "market_cap": i * 10_000_000_000.0,
                "trading_value": 300_000_000.0,
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
    store.upsert_daily_prices(prices)
    store.upsert_financials(financials)

    universe_df = filter_universe(store, as_of_date="2024-04-01", market_cap_quantile=0.20)
    assert len(universe_df) == 10


def test_filter_universe_max_debt_ratio_parameter(store: DataStore) -> None:
    companies = [
        {
            "ticker": "000010",
            "corp_code": "00000010",
            "name": "저부채기업",
            "market": "KOSDAQ",
            "sector": "제조업",
            "fiscal_month": 12,
        },
        {
            "ticker": "000020",
            "corp_code": "00000020",
            "name": "고부채기업",
            "market": "KOSDAQ",
            "sector": "제조업",
            "fiscal_month": 12,
        },
    ]
    store.upsert_companies(companies)

    prices = [
        {
            "ticker": "000010",
            "date": "2024-04-01",
            "close": 1000.0,
            "market_cap": 10_000_000_000.0,
            "trading_value": 300_000_000.0,
        },
        {
            "ticker": "000020",
            "date": "2024-04-01",
            "close": 1000.0,
            "market_cap": 10_000_000_000.0,
            "trading_value": 300_000_000.0,
        },
    ]
    store.upsert_daily_prices(prices)

    financials = [
        # 1. Debt ratio = 100 / 100 = 100.0%
        {
            "corp_code": "00000010",
            "fiscal_year": 2023,
            "quarter": 4,
            "fs_type": "CFS",
            "revenue": 1000.0,
            "gross_profit": 500.0,
            "op_income": 100.0,
            "net_income_owner": 80.0,
            "total_liabilities": 100.0,
            "total_equity": 100.0,
            "capital_stock": 20.0,
            "rcept_dt": "20240315",
        },
        # 2. Debt ratio = 250 / 100 = 250.0%
        {
            "corp_code": "00000020",
            "fiscal_year": 2023,
            "quarter": 4,
            "fs_type": "CFS",
            "revenue": 1000.0,
            "gross_profit": 500.0,
            "op_income": 100.0,
            "net_income_owner": 80.0,
            "total_liabilities": 250.0,
            "total_equity": 100.0,
            "capital_stock": 20.0,
            "rcept_dt": "20240315",
        },
    ]
    store.upsert_financials(financials)

    # By default (max_debt_ratio=None), 250% debt ratio stock passes
    df_default = filter_universe(store, as_of_date="2024-04-01", market_cap_quantile=1.0)
    assert set(df_default["ticker"]) == {"000010", "000020"}

    # With explicit max_debt_ratio=200.0, 250% debt ratio stock is filtered out
    df_capped = filter_universe(
        store, as_of_date="2024-04-01", market_cap_quantile=1.0, max_debt_ratio=200.0
    )
    assert list(df_capped["ticker"]) == ["000010"]


def test_filter_universe_excludes_sector_designations_and_foreign(store: DataStore) -> None:
    companies = [
        {
            "ticker": "000010",
            "corp_code": "00000010",
            "name": "정상기업",
            "market": "KOSDAQ",
            "sector": "일반기업부",
            "fiscal_month": 12,
        },
        {
            "ticker": "000020",
            "corp_code": "00000020",
            "name": "관리섹터기업",
            "market": "KOSDAQ",
            "sector": "관리종목(소속부없음)",
            "fiscal_month": 12,
        },
        {
            "ticker": "000030",
            "corp_code": "00000030",
            "name": "환기섹터기업",
            "market": "KOSDAQ",
            "sector": "투자주의환기종목(소속부없음)",
            "fiscal_month": 12,
        },
        {
            "ticker": "000040",
            "corp_code": "00000040",
            "name": "외국섹터기업",
            "market": "KOSDAQ",
            "sector": "외국기업(소속부없음)",
            "fiscal_month": 12,
        },
    ]
    store.upsert_companies(companies)

    prices = []
    financials = []
    for comp in companies:
        prices.append(
            {
                "ticker": comp["ticker"],
                "date": "2024-04-01",
                "close": 1000.0,
                "market_cap": 10_000_000_000.0,
                "trading_value": 300_000_000.0,
            }
        )
        financials.append(
            {
                "corp_code": comp["corp_code"],
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
    store.upsert_daily_prices(prices)
    store.upsert_financials(financials)

    universe_df = filter_universe(store, as_of_date="2024-04-01", market_cap_quantile=1.0)
    assert list(universe_df["ticker"]) == ["000010"]

    collector = DataCollector(store=store)
    pool = collector.identify_small_cap_pool(as_of_date="2024-04-01", quantile=1.0)
    assert pool == ["000010"]


def test_filter_universe_require_quarter_profit_parameter(store: DataStore) -> None:
    companies = [
        {
            "ticker": "000010",
            "corp_code": "00000010",
            "name": "연간흑자분기적자기업",
            "market": "KOSDAQ",
            "sector": "일반기업부",
            "fiscal_month": 12,
        },
    ]
    store.upsert_companies(companies)

    store.upsert_daily_prices(
        [
            {
                "ticker": "000010",
                "date": "2024-04-01",
                "close": 1000.0,
                "market_cap": 10_000_000_000.0,
                "trading_value": 300_000_000.0,
            }
        ]
    )

    # Q1~Q3 standalone positive (50 each -> 150), Q4 annual cumulative 130 -> Q4 standalone = -20 (< 0), TTM = 130 (> 0)
    financials = [
        {
            "corp_code": "00000010",
            "fiscal_year": 2023,
            "quarter": 1,
            "fs_type": "CFS",
            "revenue": 300.0,
            "gross_profit": 150.0,
            "op_income": 50.0,
            "net_income_owner": 40.0,
            "total_liabilities": 50.0,
            "total_equity": 100.0,
            "capital_stock": 20.0,
            "rcept_dt": "20230515",
        },
        {
            "corp_code": "00000010",
            "fiscal_year": 2023,
            "quarter": 2,
            "fs_type": "CFS",
            "revenue": 300.0,
            "gross_profit": 150.0,
            "op_income": 50.0,
            "net_income_owner": 40.0,
            "total_liabilities": 50.0,
            "total_equity": 100.0,
            "capital_stock": 20.0,
            "rcept_dt": "20230814",
        },
        {
            "corp_code": "00000010",
            "fiscal_year": 2023,
            "quarter": 3,
            "fs_type": "CFS",
            "revenue": 300.0,
            "gross_profit": 150.0,
            "op_income": 50.0,
            "net_income_owner": 40.0,
            "total_liabilities": 50.0,
            "total_equity": 100.0,
            "capital_stock": 20.0,
            "rcept_dt": "20231114",
        },
        {
            "corp_code": "00000010",
            "fiscal_year": 2023,
            "quarter": 4,
            "fs_type": "CFS",
            "revenue": 1000.0,
            "gross_profit": 500.0,
            "op_income": 130.0,
            "net_income_owner": 100.0,
            "total_liabilities": 50.0,
            "total_equity": 100.0,
            "capital_stock": 20.0,
            "rcept_dt": "20240315",
        },
    ]
    store.upsert_financials(financials)

    # Default require_quarter_profit=False allows TTM profitable company even with Q4 standalone loss
    df_default = filter_universe(store, as_of_date="2024-04-01", market_cap_quantile=1.0)
    assert list(df_default["ticker"]) == ["000010"]
    assert df_default.iloc[0]["op_income_quarter"] == -20.0
    assert df_default.iloc[0]["op_income_ttm"] == 130.0

    # Explicit require_quarter_profit=True filters out the Q4 standalone loss company
    df_strict = filter_universe(
        store,
        as_of_date="2024-04-01",
        market_cap_quantile=1.0,
        require_quarter_profit=True,
    )
    assert df_strict.empty


def test_filter_universe_order_b_cuts_market_cap_after_financial_filter(store: DataStore) -> None:
    # 12 companies with market caps 10B..120B.
    # The 2 smallest (10B, 20B) are unprofitable (op_income=-10),
    # while the remaining 10 (30B..120B) are profitable (op_income=100, net_income_owner=80).
    companies = []
    prices = []
    financials = []
    for i in range(1, 13):
        ticker = f"{i:05d}0"
        corp = f"corp_{i:04d}"
        companies.append(
            {
                "ticker": ticker,
                "corp_code": corp,
                "name": f"기업{i}",
                "market": "KOSDAQ",
                "sector": "일반기업부",
                "fiscal_month": 12,
            }
        )
        prices.append(
            {
                "ticker": ticker,
                "date": "2024-04-01",
                "close": 1000.0,
                "market_cap": i * 10_000_000_000.0,
                "trading_value": 300_000_000.0,
            }
        )
        is_unprofitable = i <= 2
        financials.append(
            {
                "corp_code": corp,
                "fiscal_year": 2023,
                "quarter": 4,
                "fs_type": "CFS",
                "revenue": 1000.0,
                "gross_profit": 500.0,
                "op_income": -10.0 if is_unprofitable else 100.0,
                "net_income_owner": -10.0 if is_unprofitable else 80.0,
                "total_liabilities": 50.0,
                "total_equity": 100.0,
                "capital_stock": 20.0,
                "rcept_dt": "20240315",
            }
        )

    store.upsert_companies(companies)
    store.upsert_daily_prices(prices)
    store.upsert_financials(financials)

    # Order B filters out the 2 unprofitable micro-caps first, then takes bottom 20% of the 10 profitable stocks
    universe_df = filter_universe(store, as_of_date="2024-04-01", market_cap_quantile=0.20)
    assert len(universe_df) == 2
    assert set(universe_df["ticker"]) == {"000030", "000040"}
