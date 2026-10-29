import pandas as pd

from quant_ko.data.store import DataStore


def test_initialize_schema_creates_tables_and_indices():
    # Arrange & Act
    store = DataStore(":memory:")
    store.initialize_schema()

    # Assert tables created
    with store.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}

    expected_tables = {
        "companies",
        "daily_prices",
        "financials",
        "designations",
        "orders",
    }
    assert expected_tables.issubset(tables)

    # Assert indices created
    with store.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indices = {row[0] for row in cursor.fetchall()}

    expected_indices = {
        "idx_companies_corp_code",
        "idx_daily_prices_date",
        "idx_financials_lookup",
        "idx_financials_rcept_dt",
        "idx_designations_ticker_date",
        "idx_orders_rebalance",
    }
    assert expected_indices.issubset(indices)


def test_upsert_and_get_companies():
    store = DataStore(":memory:")
    store.initialize_schema()

    records = [
        {
            "ticker": "005930",
            "corp_code": "00126380",
            "name": "삼성전자",
            "market": "KOSPI",
            "sector": "전기전자",
            "listed_at": "1975-06-11",
            "delisted_at": None,
            "fiscal_month": 12,
            "is_preferred": 0,
            "is_spac": 0,
        },
        {
            "ticker": "000660",
            "corp_code": "00164779",
            "name": "SK하이닉스",
            "market": "KOSPI",
            "sector": "전기전자",
            "listed_at": "1996-12-26",
            "delisted_at": None,
            "fiscal_month": 12,
            "is_preferred": 0,
            "is_spac": 0,
        },
    ]

    store.upsert_companies(records)
    df = store.get_companies()
    assert len(df) == 2
    assert "005930" in df["ticker"].values

    # Test updating existing record
    updated_records = [
        {
            "ticker": "005930",
            "corp_code": "00126380",
            "name": "삼성전자(수정)",
            "market": "KOSPI",
            "sector": "전기전자",
            "listed_at": "1975-06-11",
            "delisted_at": None,
            "fiscal_month": 12,
            "is_preferred": 0,
            "is_spac": 0,
        }
    ]
    store.upsert_companies(updated_records)
    df_filtered = store.get_companies(tickers=["005930"])
    assert len(df_filtered) == 1
    assert df_filtered.iloc[0]["name"] == "삼성전자(수정)"


def test_upsert_and_get_daily_prices():
    store = DataStore(":memory:")
    store.initialize_schema()

    prices = [
        {
            "ticker": "005930",
            "date": "2024-01-02",
            "close": 79600.0,
            "market_cap": 4750000.0,
            "trading_value": 100000.0,
        },
        {
            "ticker": "005930",
            "date": "2024-01-03",
            "close": 77000.0,
            "market_cap": 4600000.0,
            "trading_value": 90000.0,
        },
        {
            "ticker": "000660",
            "date": "2024-01-02",
            "close": 142000.0,
            "market_cap": 1030000.0,
            "trading_value": 50000.0,
        },
    ]

    store.upsert_daily_prices(prices)
    df = store.get_daily_prices(ticker="005930", start_date="2024-01-02", end_date="2024-01-02")
    assert len(df) == 1
    assert df.iloc[0]["close"] == 79600.0

    # Test update existing price
    updated = [
        {
            "ticker": "005930",
            "date": "2024-01-02",
            "close": 80000.0,
            "market_cap": 4770000.0,
            "trading_value": 110000.0,
        }
    ]
    store.upsert_daily_prices(updated)
    df_updated = store.get_daily_prices(
        ticker="005930", start_date="2024-01-02", end_date="2024-01-02"
    )
    assert df_updated.iloc[0]["close"] == 80000.0


def test_upsert_and_get_financials():
    store = DataStore(":memory:")
    store.initialize_schema()

    financials = [
        {
            "corp_code": "00126380",
            "fiscal_year": 2023,
            "quarter": 4,
            "fs_type": "CFS",
            "revenue": 258939300.0,
            "gross_profit": 55000000.0,
            "op_income": 6567000.0,
            "net_income_owner": 14472000.0,
            "total_liabilities": 92228000.0,
            "total_equity": 360000000.0,
            "capital_stock": 897514.0,
            "rcept_dt": "20240312",
        }
    ]

    store.upsert_financials(financials)
    df = store.get_financials(corp_code="00126380", fiscal_year=2023, quarter=4)
    assert len(df) == 1
    assert df.iloc[0]["revenue"] == 258939300.0
    assert df.iloc[0]["rcept_dt"] == "20240312"


def test_upsert_and_get_designations():
    store = DataStore(":memory:")
    store.initialize_schema()

    designations = [
        {
            "ticker": "000001",
            "type": "관리",
            "start_date": "2023-03-20",
            "end_date": "2023-09-01",
        },
        {
            "ticker": "000002",
            "type": "투자주의환기",
            "start_date": "2023-05-02",
            "end_date": None,
        },
    ]

    store.upsert_designations(designations)
    df = store.get_designations(ticker="000001")
    assert len(df) == 1
    assert df.iloc[0]["type"] == "관리"

    all_df = store.get_designations()
    assert len(all_df) == 2


def test_insert_and_get_orders():
    store = DataStore(":memory:")
    store.initialize_schema()

    order_data = {
        "rebalance_date": "2024-04-01",
        "ticker": "005930",
        "side": "BUY",
        "qty": 100,
        "price": 82000.0,
        "status": "PENDING",
        "filled_qty": 0,
        "env": "mock",
    }

    order_id = store.insert_order(order_data)
    assert isinstance(order_id, int)
    assert order_id > 0

    df_orders = store.get_orders(rebalance_date="2024-04-01", env="mock")
    assert len(df_orders) == 1
    assert df_orders.iloc[0]["status"] == "PENDING"

    # Update order status
    store.update_order_status(order_id, status="FILLED", filled_qty=100)
    df_updated = store.get_orders(rebalance_date="2024-04-01", env="mock")
    assert df_updated.iloc[0]["status"] == "FILLED"
    assert df_updated.iloc[0]["filled_qty"] == 100


def test_upsert_dataframe_and_empty_records():
    store = DataStore(":memory:")
    store.initialize_schema()

    # Empty inputs should be no-ops
    store.upsert_companies([])
    store.upsert_daily_prices([])
    store.upsert_financials([])
    store.upsert_designations([])

    # Test DataFrame input
    df_companies = pd.DataFrame(
        [
            {
                "ticker": "005930",
                "corp_code": "00126380",
                "name": "삼성전자",
                "market": "KOSPI",
                "sector": "전기전자",
                "listed_at": "1975-06-11",
                "delisted_at": None,
                "fiscal_month": 12,
                "is_preferred": 0,
                "is_spac": 0,
            }
        ]
    )
    store.upsert_companies(df_companies)
    res = store.get_companies()
    assert len(res) == 1
    assert res.iloc[0]["ticker"] == "005930"


def test_get_designations_as_of_date_filter():
    store = DataStore(":memory:")
    store.initialize_schema()

    designations = [
        {
            "ticker": "000001",
            "type": "관리",
            "start_date": "2023-01-01",
            "end_date": "2023-06-30",
        },
        {
            "ticker": "000002",
            "type": "투자주의환기",
            "start_date": "2023-03-01",
            "end_date": None,
        },
    ]
    store.upsert_designations(designations)

    # Active on 2023-05-01: both 000001 and 000002 are active
    active_may = store.get_designations(as_of_date="2023-05-01")
    assert len(active_may) == 2

    # Active on 2023-07-01: 000001 has ended, 000002 still active (end_date IS NULL)
    active_july = store.get_designations(as_of_date="2023-07-01")
    assert len(active_july) == 1
    assert active_july.iloc[0]["ticker"] == "000002"


def test_get_financials_with_filters():
    store = DataStore(":memory:")
    store.initialize_schema()

    records = [
        {
            "corp_code": "00126380",
            "fiscal_year": 2023,
            "quarter": 4,
            "fs_type": "CFS",
            "revenue": 1000.0,
            "gross_profit": 500.0,
            "op_income": 200.0,
            "net_income_owner": 150.0,
            "total_liabilities": 300.0,
            "total_equity": 700.0,
            "capital_stock": 100.0,
            "rcept_dt": "20240315",
        },
        {
            "corp_code": "00126380",
            "fiscal_year": 2023,
            "quarter": 4,
            "fs_type": "OFS",
            "revenue": 800.0,
            "gross_profit": 400.0,
            "op_income": 150.0,
            "net_income_owner": 100.0,
            "total_liabilities": 200.0,
            "total_equity": 600.0,
            "capital_stock": 100.0,
            "rcept_dt": "20240315",
        },
    ]
    store.upsert_financials(records)

    # Filter by fs_type
    df_cfs = store.get_financials(corp_code="00126380", fs_type="CFS")
    assert len(df_cfs) == 1
    assert df_cfs.iloc[0]["fs_type"] == "CFS"

    # Filter by before_rcept_dt
    df_before = store.get_financials(before_rcept_dt="20240301")
    assert len(df_before) == 0

    df_after = store.get_financials(before_rcept_dt="20240320")
    assert len(df_after) == 2


def test_datastore_context_manager_and_file_path(tmp_path):
    db_file = tmp_path / "test.db"
    with DataStore(db_file) as store:
        store.initialize_schema()
        store.upsert_companies([{"ticker": "005930", "name": "삼성전자"}])
        df = store.get_companies()
        assert len(df) == 1

    # Re-open persisted db
    with DataStore(db_file) as store2:
        df2 = store2.get_companies()
        assert len(df2) == 1
        assert df2.iloc[0]["name"] == "삼성전자"


def test_apply_oci_db_patch_if_needed(tmp_path):
    """구버전 DB에 대해 oci_db_patch.json.gz 패치가 1회 자동 반영되고 이후 즉시 스킵되는지 검증."""
    import gzip
    import json

    from quant_ko.data.store import apply_oci_db_patch_if_needed

    patch_file = tmp_path / "oci_db_patch.json.gz"
    patch_payload = {
        "companies": [
            {
                "ticker": "000010",
                "corp_code": "c1",
                "name": "패치기업A",
                "market": "KOSDAQ",
                "sector": "IT",
                "listed_at": "2020-01-01",
                "delisted_at": None,
                "fiscal_month": 12,
                "is_preferred": 0,
                "is_spac": 0,
            }
        ],
        "financials": [
            {
                "corp_code": "c1",
                "fiscal_year": 2025,
                "quarter": 4,
                "fs_type": "CFS",
                "revenue": 100.0,
                "gross_profit": 50.0,
                "op_income": 20.0,
                "net_income_owner": 15.0,
                "total_liabilities": 30.0,
                "total_equity": 70.0,
                "capital_stock": 10.0,
                "rcept_dt": "20260320",
            }
        ],
        "daily_prices": [
            {
                "ticker": "000010",
                "date": "2026-10-29",
                "close": 12300.0,
                "market_cap": 50_000_000_000.0,
                "trading_value": 500_000_000.0,
            }
        ],
    }
    with gzip.open(patch_file, "wt", encoding="utf-8") as f:
        json.dump(patch_payload, f)

    store = DataStore(":memory:")
    store.initialize_schema()

    # 1차 호출: DB가 비어있으므로 패치가 적용되어 True 반환
    applied1 = apply_oci_db_patch_if_needed(
        store,
        patch_path=patch_file,
        min_latest_date="2026-10-23",
        min_financials_count=1,
    )
    assert applied1 is True
    assert len(store.get_companies()) == 1
    assert len(store.get_financials()) == 1
    assert store.get_trading_days() == ["2026-10-29"]

    # 2차 호출: 이미 최신 상태이므로 패치 파일을 읽지 않고 즉시 False 반환
    applied2 = apply_oci_db_patch_if_needed(
        store,
        patch_path=patch_file,
        min_latest_date="2026-10-23",
        min_financials_count=1,
    )
    assert applied2 is False
