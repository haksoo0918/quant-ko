"""Tests for Data Ingestion and Collector runner."""

import pandas as pd
import pytest

from quant_ko.data.collector import DataCollector
from quant_ko.data.store import DataStore


@pytest.fixture
def mem_store() -> DataStore:
    store = DataStore(":memory:")
    store.initialize_schema()
    return store


def test_identify_small_cap_pool_filters_and_quantiles(mem_store: DataStore):
    # Setup test companies:
    # 10 common companies + 1 preferred + 1 spac + 1 chinese + 1 holding
    companies = [
        # Normal common companies
        {
            "ticker": f"0000{i}0",
            "corp_code": f"0000000{i}",
            "name": f"정상기업{i}",
            "market": "KOSDAQ",
            "sector": "제조업",
        }
        for i in range(1, 11)
    ]
    # Excluded companies
    companies.extend(
        [
            {
                "ticker": "000995",
                "corp_code": "00000095",
                "name": "우선주A우",
                "market": "KOSPI",
                "sector": "제조업",
                "is_preferred": 1,
            },
            {
                "ticker": "000990",
                "corp_code": "00000096",
                "name": "대신스팩1호",
                "market": "KOSDAQ",
                "sector": "금융",
                "is_spac": 1,
            },
            {
                "ticker": "900010",
                "corp_code": "00000097",
                "name": "차이나그레이트",
                "market": "KOSDAQ",
                "sector": "제조업",
            },
            {
                "ticker": "000992",
                "corp_code": "00000098",
                "name": "한국금융지주",
                "market": "KOSPI",
                "sector": "금융업",
            },
        ]
    )
    mem_store.upsert_companies(companies)

    # Setup daily prices with varying market caps for the 10 normal companies
    # Market caps: 100M, 200M, 300M, ..., 1000M
    prices = []
    for i in range(1, 11):
        prices.append(
            {
                "ticker": f"0000{i}0",
                "date": "2024-01-02",
                "close": 1000.0 * i,
                "market_cap": 100_000_000.0 * i,
                "trading_value": 500_000_000.0,
            }
        )
    # Also add prices for excluded companies (even if low market cap, they must be filtered out)
    prices.append(
        {
            "ticker": "000995",
            "date": "2024-01-02",
            "close": 500.0,
            "market_cap": 50_000_000.0,
            "trading_value": 500_000_000.0,
        }
    )
    prices.append(
        {
            "ticker": "900010",
            "date": "2024-01-02",
            "close": 500.0,
            "market_cap": 50_000_000.0,
            "trading_value": 500_000_000.0,
        }
    )
    mem_store.upsert_daily_prices(prices)

    collector = DataCollector(store=mem_store)
    pool = collector.identify_small_cap_pool(as_of_date="2024-01-02", quantile=0.20)

    # Out of 10 normal companies, bottom 20% quantile (quantile=0.20) gives smallest 2:
    # 000010 (100M) and 000020 (200M)
    assert len(pool) == 2
    assert "000010" in pool
    assert "000020" in pool
    # Excluded stocks should NOT be in the pool
    assert "000995" not in pool
    assert "900010" not in pool


def test_collect_companies_tags_and_maps_corp_code(mem_store: DataStore):
    from unittest.mock import MagicMock

    mock_krx = MagicMock()
    mock_krx.fetch_ticker_list.return_value = pd.DataFrame(
        [
            {
                "ticker": "005930",
                "name": "삼성전자",
                "market": "KOSPI",
                "sector": "전기전자",
                "listed_at": "1975-06-11",
                "delisted_at": None,
            },
            {
                "ticker": "005935",
                "name": "삼성전자우",
                "market": "KOSPI",
                "sector": "전기전자",
                "listed_at": "1975-06-11",
                "delisted_at": None,
            },
            {
                "ticker": "123450",
                "name": "KB스팩10호",
                "market": "KOSDAQ",
                "sector": "금융",
                "listed_at": "2020-01-01",
                "delisted_at": None,
            },
        ]
    )
    mock_krx.fetch_delisted_tickers.return_value = pd.DataFrame()

    mock_dart = MagicMock()
    mock_dart.get_ticker_to_corp_code.return_value = {
        "005930": "00126380",
        "005935": "00126380",
    }

    collector = DataCollector(store=mem_store, dart_client=mock_dart, krx_client=mock_krx)
    count = collector.collect_companies()

    assert count == 3
    stored = mem_store.get_companies()
    assert len(stored) == 3

    # Check mapping
    samsung = stored[stored["ticker"] == "005930"].iloc[0]
    assert samsung["corp_code"] == "00126380"
    assert samsung["is_preferred"] == 0
    assert samsung["is_spac"] == 0

    samsung_pref = stored[stored["ticker"] == "005935"].iloc[0]
    assert samsung_pref["is_preferred"] == 1

    spac = stored[stored["ticker"] == "123450"].iloc[0]
    assert spac["is_spac"] == 1


def test_collect_financials_skips_existing_and_saves_new(mem_store: DataStore):
    from unittest.mock import MagicMock

    # Pre-populate one quarter (2020 Q1) in store
    mem_store.upsert_financials(
        [
            {
                "corp_code": "00126380",
                "fiscal_year": 2020,
                "quarter": 1,
                "fs_type": "CFS",
                "revenue": 1000.0,
                "gross_profit": 300.0,
                "op_income": 100.0,
                "net_income_owner": 80.0,
                "total_liabilities": 500.0,
                "total_equity": 500.0,
                "capital_stock": 100.0,
                "rcept_dt": "20200515",
            }
        ]
    )

    mock_dart = MagicMock()
    # Mock fetching returns data for 2020 Q2 CFS
    mock_dart.fetch_and_parse_financials.side_effect = (
        lambda corp_code, fiscal_year, quarter, fs_type="CFS": {
            "corp_code": corp_code,
            "fiscal_year": fiscal_year,
            "quarter": quarter,
            "fs_type": fs_type,
            "revenue": 1200.0,
            "gross_profit": 350.0,
            "op_income": 120.0,
            "net_income_owner": 90.0,
            "total_liabilities": 520.0,
            "total_equity": 550.0,
            "capital_stock": 100.0,
            "rcept_dt": f"{fiscal_year}0815",
        }
    )

    collector = DataCollector(store=mem_store, dart_client=mock_dart)
    # Collect for 2020 Q1 and Q2
    count = collector.collect_financials(
        corp_codes=["00126380"],
        start_year=2020,
        end_year=2020,
        quarters=[1, 2],
    )

    # Only Q2 should be fetched since Q1 was already in store
    assert count == 1
    # Verify mock was only called for Q2, NOT for Q1
    assert mock_dart.fetch_and_parse_financials.call_count == 1
    call_args = mock_dart.fetch_and_parse_financials.call_args[1]
    assert call_args["fiscal_year"] == 2020
    assert call_args["quarter"] == 2

    # Check store has both Q1 and Q2
    fin_q1 = mem_store.get_financials(corp_code="00126380", fiscal_year=2020, quarter=1)
    assert not fin_q1.empty
    fin_q2 = mem_store.get_financials(corp_code="00126380", fiscal_year=2020, quarter=2)
    assert not fin_q2.empty
    assert fin_q2.iloc[0]["op_income"] == 120.0


def test_collect_financials_fallback_to_ofs(mem_store: DataStore):
    from unittest.mock import MagicMock

    mock_dart = MagicMock()

    # CFS returns None, OFS returns valid dict
    def mock_fetch(corp_code, fiscal_year, quarter, fs_type="CFS"):
        if fs_type == "CFS":
            return None
        return {
            "corp_code": corp_code,
            "fiscal_year": fiscal_year,
            "quarter": quarter,
            "fs_type": "OFS",
            "revenue": 500.0,
            "gross_profit": 150.0,
            "op_income": 50.0,
            "net_income_owner": 40.0,
            "total_liabilities": 200.0,
            "total_equity": 300.0,
            "capital_stock": 50.0,
            "rcept_dt": f"{fiscal_year}0515",
        }

    mock_dart.fetch_and_parse_financials.side_effect = mock_fetch

    collector = DataCollector(store=mem_store, dart_client=mock_dart)
    count = collector.collect_financials(
        corp_codes=["00126380"],
        start_year=2021,
        end_year=2021,
        quarters=[1],
    )

    assert count == 1
    # Both CFS and OFS were attempted
    assert mock_dart.fetch_and_parse_financials.call_count == 2
    fin = mem_store.get_financials(corp_code="00126380", fiscal_year=2021, quarter=1)
    assert not fin.empty
    assert fin.iloc[0]["fs_type"] == "OFS"


def test_collect_daily_prices_with_checkpointing_and_resume(mem_store: DataStore):
    from unittest.mock import MagicMock

    mock_source = MagicMock()

    # Mock price source returning DataFrame
    def mock_fetch(ticker, start_date, end_date):
        if start_date == "2024-01-02" and end_date == "2024-01-03":
            return pd.DataFrame(
                [
                    {"Close": 1000.0, "Volume": 10000, "Amount": 10000000.0, "MarCap": 50000000.0},
                    {"Close": 1050.0, "Volume": 12000, "Amount": 12600000.0, "MarCap": 52500000.0},
                ],
                index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
            )
        elif start_date == "2024-01-04" and end_date == "2024-01-05":
            return pd.DataFrame(
                [
                    {"Close": 1100.0, "Volume": 15000, "Amount": 16500000.0, "MarCap": 55000000.0},
                    {"Close": 1080.0, "Volume": 8000, "Amount": 8640000.0, "MarCap": 54000000.0},
                ],
                index=pd.to_datetime(["2024-01-04", "2024-01-05"]),
            )
        return pd.DataFrame()

    mock_source.side_effect = mock_fetch

    collector = DataCollector(store=mem_store)

    # 1. First collection: 2024-01-02 to 2024-01-03
    count1 = collector.collect_daily_prices(
        tickers=["000010"],
        start_date="2024-01-02",
        end_date="2024-01-03",
        price_source_fn=mock_source,
    )
    assert count1 == 2
    prices = mem_store.get_daily_prices(ticker="000010")
    assert len(prices) == 2

    # 2. Re-running for same date range: should skip completely
    mock_source.reset_mock()
    count2 = collector.collect_daily_prices(
        tickers=["000010"],
        start_date="2024-01-02",
        end_date="2024-01-03",
        price_source_fn=mock_source,
    )
    assert count2 == 0
    assert mock_source.call_count == 0

    # 3. Extending range up to 2024-01-05: should resume from 2024-01-04
    count3 = collector.collect_daily_prices(
        tickers=["000010"],
        start_date="2024-01-02",
        end_date="2024-01-05",
        price_source_fn=mock_source,
    )
    assert count3 == 2
    assert mock_source.call_count == 1
    call_args = mock_source.call_args[0]
    assert call_args[0] == "000010"
    assert call_args[1] == "2024-01-04"
    assert call_args[2] == "2024-01-05"

    total_prices = mem_store.get_daily_prices(ticker="000010")
    assert len(total_prices) == 4


def test_run_collection_orchestration(mem_store: DataStore):
    from unittest.mock import MagicMock

    # Setup mock KRX
    mock_krx = MagicMock()
    mock_krx.fetch_ticker_list.return_value = pd.DataFrame(
        [
            {
                "ticker": "000010",
                "name": "기업A",
                "market": "KOSDAQ",
                "sector": "제조업",
                "listed_at": "2010-01-01",
            },
            {
                "ticker": "000020",
                "name": "기업B",
                "market": "KOSDAQ",
                "sector": "제조업",
                "listed_at": "2010-01-01",
            },
            {
                "ticker": "000030",
                "name": "기업C",
                "market": "KOSPI",
                "sector": "대형제조",
                "listed_at": "2010-01-01",
            },
        ]
    )
    mock_krx.fetch_delisted_tickers.return_value = pd.DataFrame()

    # Pre-populate snapshot prices so identify_small_cap_pool can identify bottom 20%
    # 기업A: 100M, 기업B: 200M, 기업C: 1000M
    mem_store.upsert_daily_prices(
        [
            {
                "ticker": "000010",
                "date": "2024-01-02",
                "close": 1000.0,
                "market_cap": 100_000_000.0,
                "trading_value": 500_000_000.0,
            },
            {
                "ticker": "000020",
                "date": "2024-01-02",
                "close": 2000.0,
                "market_cap": 200_000_000.0,
                "trading_value": 500_000_000.0,
            },
            {
                "ticker": "000030",
                "date": "2024-01-02",
                "close": 10000.0,
                "market_cap": 1_000_000_000.0,
                "trading_value": 500_000_000.0,
            },
        ]
    )

    # Setup mock DART
    mock_dart = MagicMock()
    mock_dart.get_ticker_to_corp_code.return_value = {
        "000010": "00000010",
        "000020": "00000020",
        "000030": "00000030",
    }
    mock_dart.fetch_and_parse_financials.side_effect = (
        lambda corp_code, fiscal_year, quarter, fs_type="CFS": {
            "corp_code": corp_code,
            "fiscal_year": fiscal_year,
            "quarter": quarter,
            "fs_type": fs_type,
            "revenue": 1000.0,
            "gross_profit": 300.0,
            "op_income": 100.0,
            "net_income_owner": 80.0,
            "total_liabilities": 500.0,
            "total_equity": 500.0,
            "capital_stock": 100.0,
            "rcept_dt": f"{fiscal_year}0515",
        }
    )

    # Mock price source for history
    def mock_price_fetch(ticker, start_date, end_date):
        return pd.DataFrame(
            [{"Close": 1000.0, "Volume": 1000, "Amount": 1000000.0, "MarCap": 100000000.0}],
            index=pd.to_datetime([start_date]),
        )

    collector = DataCollector(store=mem_store, dart_client=mock_dart, krx_client=mock_krx)

    # Run collection with quantile 0.35 (picks lowest cap: 000010)
    summary = collector.run_collection(
        start_year=2021,
        end_year=2021,
        quantile=0.35,
        price_start_date="2021-01-02",
        price_end_date="2021-01-05",
        price_source_fn=mock_price_fetch,
    )

    assert summary["companies_count"] == 3
    assert summary["small_cap_count"] == 1
    assert "000010" in summary["small_cap_tickers"]
    assert summary["financials_count"] == 4  # 4 quarters for 2021
    # Check that financials exist in DB
    fin = mem_store.get_financials(corp_code="00000010")
    assert len(fin) == 4


def test_cli_main_argument_parsing():
    from unittest.mock import patch

    from quant_ko.data.collector import main

    with patch("quant_ko.data.collector.DataCollector.run_collection") as mock_run:
        mock_run.return_value = {
            "companies_count": 10,
            "small_cap_count": 2,
            "small_cap_tickers": ["000010", "000020"],
            "benchmark_prices_count": 50,
            "target_prices_count": 100,
            "financials_count": 8,
        }

        ret = main(
            [
                "--start-year",
                "2020",
                "--end-year",
                "2024",
                "--quantile",
                "0.20",
                "--db-path",
                ":memory:",
            ]
        )

        assert ret == 0
        assert mock_run.call_count == 1
        _, kwargs = mock_run.call_args
        assert kwargs["start_year"] == 2020
        assert kwargs["end_year"] == 2024
        assert kwargs["quantile"] == 0.20
