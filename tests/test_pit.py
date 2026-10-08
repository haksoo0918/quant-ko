import pytest

from quant_ko.data.store import DataStore
from quant_ko.pit.builder import PITSnapshotBuilder


@pytest.fixture
def store():
    ds = DataStore(":memory:")
    ds.initialize_schema()
    yield ds
    ds.close()


def test_pit_builder_respects_rcept_dt_cutoff(store):
    # Company with reports:
    # 2023 Q3 filed on 2023-11-14
    # 2023 Q4 filed on 2024-03-15
    financials = [
        {
            "corp_code": "00126380",
            "fiscal_year": 2023,
            "quarter": 3,
            "fs_type": "CFS",
            "revenue": 300.0,
            "gross_profit": 100.0,
            "op_income": 30.0,
            "net_income_owner": 20.0,
            "total_liabilities": 100.0,
            "total_equity": 200.0,
            "capital_stock": 50.0,
            "rcept_dt": "20231114",
        },
        {
            "corp_code": "00126380",
            "fiscal_year": 2023,
            "quarter": 4,
            "fs_type": "CFS",
            "revenue": 450.0,
            "gross_profit": 150.0,
            "op_income": 45.0,
            "net_income_owner": 30.0,
            "total_liabilities": 120.0,
            "total_equity": 230.0,
            "capital_stock": 50.0,
            "rcept_dt": "20240315",
        },
    ]
    store.upsert_financials(financials)

    builder = PITSnapshotBuilder(store)

    # As of 2023-12-31, 2023 Q4 is NOT yet published (published 20240315)
    # So latest available quarter must be 2023 Q3
    res_dec = builder.get_company_pit_financials("00126380", as_of_date="20231231")
    assert res_dec is not None
    assert res_dec["fiscal_year"] == 2023
    assert res_dec["quarter"] == 3
    assert res_dec["rcept_dt"] == "20231114"

    # As of 2024-03-20, 2023 Q4 is published and should be the latest quarter
    res_mar = builder.get_company_pit_financials("00126380", as_of_date="20240320")
    assert res_mar is not None
    assert res_mar["fiscal_year"] == 2023
    assert res_mar["quarter"] == 4
    assert res_mar["rcept_dt"] == "20240315"


def test_pit_builder_cfs_priority_and_amendments(store):
    # Company with both CFS and OFS, and an amendment
    financials = [
        # Original CFS for 2023 Q3
        {
            "corp_code": "00000001",
            "fiscal_year": 2023,
            "quarter": 3,
            "fs_type": "CFS",
            "revenue": 100.0,
            "gross_profit": 50.0,
            "op_income": 10.0,
            "net_income_owner": 8.0,
            "total_liabilities": 50.0,
            "total_equity": 100.0,
            "capital_stock": 20.0,
            "rcept_dt": "20231114",
        },
        # OFS for 2023 Q3 on same date
        {
            "corp_code": "00000001",
            "fiscal_year": 2023,
            "quarter": 3,
            "fs_type": "OFS",
            "revenue": 80.0,
            "gross_profit": 40.0,
            "op_income": 8.0,
            "net_income_owner": 6.0,
            "total_liabilities": 40.0,
            "total_equity": 90.0,
            "capital_stock": 20.0,
            "rcept_dt": "20231114",
        },
        # Amendment to CFS filed on 2023-11-20
        {
            "corp_code": "00000001",
            "fiscal_year": 2023,
            "quarter": 3,
            "fs_type": "CFS",
            "revenue": 110.0,
            "gross_profit": 55.0,
            "op_income": 12.0,
            "net_income_owner": 9.0,
            "total_liabilities": 50.0,
            "total_equity": 100.0,
            "capital_stock": 20.0,
            "rcept_dt": "20231120",
        },
        # Another amendment filed in 2024-01-10
        {
            "corp_code": "00000001",
            "fiscal_year": 2023,
            "quarter": 3,
            "fs_type": "CFS",
            "revenue": 120.0,
            "gross_profit": 60.0,
            "op_income": 15.0,
            "net_income_owner": 10.0,
            "total_liabilities": 50.0,
            "total_equity": 100.0,
            "capital_stock": 20.0,
            "rcept_dt": "20240110",
        },
    ]
    store.upsert_financials(financials)

    builder = PITSnapshotBuilder(store)

    # As of 2023-11-15: should choose CFS over OFS, with original values (100 revenue)
    res_nov15 = builder.get_company_pit_financials("00000001", as_of_date="20231115")
    assert res_nov15["fs_type"] == "CFS"
    assert res_nov15["revenue"] == 100.0

    # As of 2023-11-25: should choose the amended CFS (110 revenue)
    res_nov25 = builder.get_company_pit_financials("00000001", as_of_date="20231125")
    assert res_nov25["revenue"] == 110.0
    assert res_nov25["rcept_dt"] == "20231120"

    # As of 2024-01-15: should choose the 2nd amended CFS (120 revenue)
    res_jan15 = builder.get_company_pit_financials("00000001", as_of_date="20240115")
    assert res_jan15["revenue"] == 120.0
    assert res_jan15["rcept_dt"] == "20240110"


def test_pit_builder_q4_discrete_ttm_and_yoy(store):
    financials = [
        # 2022 Q1
        {
            "corp_code": "00100001",
            "fiscal_year": 2022,
            "quarter": 1,
            "fs_type": "CFS",
            "revenue": 100.0,
            "gross_profit": 50.0,
            "op_income": 10.0,
            "net_income_owner": 8.0,
            "total_liabilities": 100.0,
            "total_equity": 200.0,
            "capital_stock": 50.0,
            "rcept_dt": "20220515",
        },
        # 2022 Q2
        {
            "corp_code": "00100001",
            "fiscal_year": 2022,
            "quarter": 2,
            "fs_type": "CFS",
            "revenue": 120.0,
            "gross_profit": 60.0,
            "op_income": 12.0,
            "net_income_owner": 10.0,
            "total_liabilities": 110.0,
            "total_equity": 210.0,
            "capital_stock": 50.0,
            "rcept_dt": "20220814",
        },
        # 2022 Q3
        {
            "corp_code": "00100001",
            "fiscal_year": 2022,
            "quarter": 3,
            "fs_type": "CFS",
            "revenue": 110.0,
            "gross_profit": 55.0,
            "op_income": 11.0,
            "net_income_owner": 9.0,
            "total_liabilities": 115.0,
            "total_equity": 215.0,
            "capital_stock": 50.0,
            "rcept_dt": "20221114",
        },
        # 2022 Q4 Annual report
        {
            "corp_code": "00100001",
            "fiscal_year": 2022,
            "quarter": 4,
            "fs_type": "CFS",
            "revenue": 500.0,
            "gross_profit": 250.0,
            "op_income": 50.0,
            "net_income_owner": 40.0,
            "total_liabilities": 120.0,
            "total_equity": 220.0,
            "capital_stock": 50.0,
            "rcept_dt": "20230320",
        },
        # 2023 Q1 report
        {
            "corp_code": "00100001",
            "fiscal_year": 2023,
            "quarter": 1,
            "fs_type": "CFS",
            "revenue": 130.0,
            "gross_profit": 65.0,
            "op_income": 15.0,
            "net_income_owner": 12.0,
            "total_liabilities": 150.0,
            "total_equity": 250.0,
            "capital_stock": 50.0,
            "rcept_dt": "20230515",
        },
    ]
    store.upsert_financials(financials)

    builder = PITSnapshotBuilder(store)
    res = builder.get_company_pit_financials("00100001", as_of_date="20230601")
    assert res is not None

    # Latest quarter is 2023 Q1
    assert res["fiscal_year"] == 2023
    assert res["quarter"] == 1
    assert res["revenue_quarter"] == 130.0
    assert res["gross_profit_quarter"] == 65.0
    assert res["op_income_quarter"] == 15.0
    assert res["net_income_owner_quarter"] == 12.0

    # Discrete Q4 of 2022 is 500 - (100+120+110) = 170
    # TTM revenue = 130 (2023 Q1) + 170 (2022 Q4) + 110 (2022 Q3) + 120 (2022 Q2) = 530.0
    assert pytest.approx(res["revenue_ttm"]) == 530.0
    # TTM gross_profit = 65 + 85 + 55 + 60 = 265.0
    assert pytest.approx(res["gross_profit_ttm"]) == 265.0
    # TTM op_income = 15 + 17 + 11 + 12 = 55.0
    assert pytest.approx(res["op_income_ttm"]) == 55.0
    # TTM net_income_owner = 12 + 13 + 9 + 10 = 44.0
    assert pytest.approx(res["net_income_owner_ttm"]) == 44.0

    # YoY comparisons (2023 Q1 vs 2022 Q1)
    # revenue YoY = (130 - 100) / 100 = 0.30 (30%)
    assert pytest.approx(res["revenue_yoy"]) == 0.30
    assert pytest.approx(res["op_income_yoy"]) == 0.50
    assert pytest.approx(res["net_income_owner_yoy"]) == 0.50
    assert res["op_income_turnaround"] is False

    # Balance sheet & ratios
    assert res["total_liabilities"] == 150.0
    assert res["total_equity"] == 250.0
    assert res["capital_stock"] == 50.0
    assert pytest.approx(res["debt_ratio"]) == (150.0 / 250.0) * 100.0  # 60.0%
    # capital_stock 50, total_equity 250 -> (50 - 250) / 50 * 100 = -400.0%
    assert pytest.approx(res["impairment_ratio"]) == -400.0


def test_pit_builder_turnaround_detection(store):
    financials = [
        # 2022 Q2: Loss
        {
            "corp_code": "00200001",
            "fiscal_year": 2022,
            "quarter": 2,
            "fs_type": "CFS",
            "revenue": 80.0,
            "gross_profit": 20.0,
            "op_income": -10.0,
            "net_income_owner": -15.0,
            "total_liabilities": 200.0,
            "total_equity": 50.0,
            "capital_stock": 100.0,
            "rcept_dt": "20220814",
        },
        # 2023 Q2: Profit (turnaround)
        {
            "corp_code": "00200001",
            "fiscal_year": 2023,
            "quarter": 2,
            "fs_type": "CFS",
            "revenue": 100.0,
            "gross_profit": 35.0,
            "op_income": 5.0,
            "net_income_owner": 3.0,
            "total_liabilities": 180.0,
            "total_equity": 60.0,
            "capital_stock": 100.0,
            "rcept_dt": "20230814",
        },
    ]
    store.upsert_financials(financials)

    builder = PITSnapshotBuilder(store)
    res = builder.get_company_pit_financials("00200001", as_of_date="20230901")
    assert res is not None

    assert res["op_income_quarter"] == 5.0
    assert res["op_income_turnaround"] is True
    # YoY growth rate formula: (latest - prev) / abs(prev) = (5 - (-10)) / 10 = 1.5 (150%)
    assert pytest.approx(res["op_income_yoy"]) == 1.5

    assert res["net_income_owner_quarter"] == 3.0
    assert res["net_income_owner_turnaround"] is True
    # (3 - (-15)) / 15 = 1.2
    assert pytest.approx(res["net_income_owner_yoy"]) == 1.2

    # Capital impairment ratio: (100 - 60) / 100 * 100 = 40.0% (impaired)
    assert pytest.approx(res["impairment_ratio"]) == 40.0
    # Debt ratio: (180 / 60) * 100 = 300.0%
    assert pytest.approx(res["debt_ratio"]) == 300.0


def test_pit_builder_build_snapshot_multi_company(store):
    store.upsert_companies(
        [
            {"ticker": "005930", "corp_code": "00126380", "name": "삼성전자"},
            {"ticker": "000660", "corp_code": "00164779", "name": "SK하이닉스"},
        ]
    )
    store.upsert_financials(
        [
            {
                "corp_code": "00126380",
                "fiscal_year": 2023,
                "quarter": 4,
                "fs_type": "CFS",
                "revenue": 1000.0,
                "gross_profit": 400.0,
                "op_income": 100.0,
                "net_income_owner": 80.0,
                "total_liabilities": 500.0,
                "total_equity": 1000.0,
                "capital_stock": 200.0,
                "rcept_dt": "20240315",
            },
            {
                "corp_code": "00164779",
                "fiscal_year": 2023,
                "quarter": 4,
                "fs_type": "CFS",
                "revenue": 800.0,
                "gross_profit": 300.0,
                "op_income": 80.0,
                "net_income_owner": 60.0,
                "total_liabilities": 400.0,
                "total_equity": 800.0,
                "capital_stock": 150.0,
                "rcept_dt": "20240318",
            },
        ]
    )

    builder = PITSnapshotBuilder(store)
    df = builder.build_snapshot(as_of_date="20240320")

    assert len(df) == 2
    assert set(df["ticker"].tolist()) == {"005930", "000660"}
    assert "debt_ratio" in df.columns
    assert "op_income_ttm" in df.columns
