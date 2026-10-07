import io
import zipfile
from unittest.mock import MagicMock

import pandas as pd
import pytest

from quant_ko.data.dart import DartClient, _clean_amount


def _create_mock_corp_code_zip() -> bytes:
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<result>
    <list>
        <corp_code>00126380</corp_code>
        <corp_name>삼성전자</corp_name>
        <stock_code>005930</stock_code>
        <modify_date>20230101</modify_date>
    </list>
    <list>
        <corp_code>00164779</corp_code>
        <corp_name>SK하이닉스</corp_name>
        <stock_code>000660</stock_code>
        <modify_date>20230101</modify_date>
    </list>
    <list>
        <corp_code>00999999</corp_code>
        <corp_name>비상장회사</corp_name>
        <stock_code> </stock_code>
        <modify_date>20230101</modify_date>
    </list>
</result>
"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("CORPCODE.xml", xml_content.encode("utf-8"))
    return buffer.getvalue()


def test_fetch_corp_codes_parses_zip_and_filters_listed():
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = _create_mock_corp_code_zip()
    mock_session.get.return_value = mock_response

    client = DartClient(api_key="TEST_KEY", session=mock_session)
    df = client.fetch_corp_codes(only_listed=True)

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert set(df["ticker"]) == {"005930", "000660"}
    assert df.loc[df["ticker"] == "005930", "corp_code"].iloc[0] == "00126380"
    assert df.loc[df["ticker"] == "005930", "name"].iloc[0] == "삼성전자"

    # Test mapping helper
    ticker_map = client.get_ticker_to_corp_code()
    assert ticker_map["005930"] == "00126380"
    assert "비상장회사" not in ticker_map.values()


def test_fetch_financial_statements_single_company():
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "000",
        "message": "정상",
        "list": [
            {
                "rcept_no": "20240315000123",
                "bsns_year": "2023",
                "corp_code": "00126380",
                "sj_div": "IS",
                "account_id": "ifrs-full_Revenue",
                "account_nm": "매출액",
                "thstrm_amount": "258,939,300",
            }
        ],
    }
    mock_session.get.return_value = mock_response

    client = DartClient(api_key="TEST_KEY", session=mock_session)
    items = client.fetch_financial_statements(
        corp_code="00126380", fiscal_year=2023, quarter=4, fs_type="CFS"
    )

    assert len(items) == 1
    assert items[0]["account_nm"] == "매출액"

    # Verify request query parameters
    call_args, call_kwargs = mock_session.get.call_args
    assert "fnlttSinglAcntAll.json" in call_args[0]
    assert call_kwargs["params"]["corp_code"] == "00126380"
    assert call_kwargs["params"]["bsns_year"] == "2023"
    assert call_kwargs["params"]["reprt_code"] == "11011"
    assert call_kwargs["params"]["fs_div"] == "CFS"


def test_fetch_financial_statements_handles_no_data():
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "013",
        "message": "조회된 데이타가 없습니다.",
    }
    mock_session.get.return_value = mock_response

    client = DartClient(api_key="TEST_KEY", session=mock_session)
    items = client.fetch_financial_statements(corp_code="00126380", fiscal_year=2023, quarter=1)
    assert items == []


def test_fetch_multi_financial_statements():
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "000",
        "message": "정상",
        "list": [
            {"corp_code": "00126380", "account_nm": "매출액", "thstrm_amount": "100"},
            {"corp_code": "00164779", "account_nm": "매출액", "thstrm_amount": "200"},
        ],
    }
    mock_session.get.return_value = mock_response

    client = DartClient(api_key="TEST_KEY", session=mock_session)
    items = client.fetch_multi_financial_statements(
        corp_codes=["00126380", "00164779"], fiscal_year=2023, quarter=3
    )

    assert len(items) == 2
    call_args, call_kwargs = mock_session.get.call_args
    assert "fnlttMultiAcnt.json" in call_args[0]
    assert call_kwargs["params"]["corp_code"] == "00126380,00164779"
    assert call_kwargs["params"]["reprt_code"] == "11014"


def test_parse_financial_accounts_cfs():
    raw_items = [
        {
            "rcept_no": "20240315000888",
            "corp_code": "00126380",
            "sj_div": "IS",
            "account_id": "ifrs-full_Revenue",
            "account_nm": "매출액",
            "thstrm_amount": "258,939,300",
        },
        {
            "rcept_no": "20240315000888",
            "corp_code": "00126380",
            "sj_div": "IS",
            "account_id": "ifrs-full_GrossProfit",
            "account_nm": "매출총이익",
            "thstrm_amount": "55,000,000",
        },
        {
            "rcept_no": "20240315000888",
            "corp_code": "00126380",
            "sj_div": "IS",
            "account_id": "dart_OperatingIncomeLoss",
            "account_nm": "영업이익",
            "thstrm_amount": "6,567,000",
        },
        {
            "rcept_no": "20240315000888",
            "corp_code": "00126380",
            "sj_div": "IS",
            "account_id": "ifrs-full_ProfitLossAttributableToOwnersOfParent",
            "account_nm": "지배기업의 소유주지분 당기순이익",
            "thstrm_amount": "14,472,000",
        },
        {
            "rcept_no": "20240315000888",
            "corp_code": "00126380",
            "sj_div": "BS",
            "account_id": "ifrs-full_Liabilities",
            "account_nm": "부채총계",
            "thstrm_amount": "92,228,000",
        },
        {
            "rcept_no": "20240315000888",
            "corp_code": "00126380",
            "sj_div": "BS",
            "account_id": "ifrs-full_Equity",
            "account_nm": "자본총계",
            "thstrm_amount": "360,000,000",
        },
        {
            "rcept_no": "20240315000888",
            "corp_code": "00126380",
            "sj_div": "BS",
            "account_id": "ifrs-full_IssuedCapital",
            "account_nm": "자본금",
            "thstrm_amount": "897,514",
        },
    ]

    client = DartClient(api_key="TEST_KEY")
    result = client.parse_financial_accounts(
        items=raw_items,
        corp_code="00126380",
        fiscal_year=2023,
        quarter=4,
        fs_type="CFS",
    )

    assert result is not None
    assert result["corp_code"] == "00126380"
    assert result["fiscal_year"] == 2023
    assert result["quarter"] == 4
    assert result["fs_type"] == "CFS"
    assert result["rcept_dt"] == "20240315"
    assert result["revenue"] == 258939300.0
    assert result["gross_profit"] == 55000000.0
    assert result["op_income"] == 6567000.0
    assert result["net_income_owner"] == 14472000.0
    assert result["total_liabilities"] == 92228000.0
    assert result["total_equity"] == 360000000.0
    assert result["capital_stock"] == 897514.0


def test_parse_financial_accounts_ofs_fallback_net_income():
    raw_items = [
        {
            "rcept_no": "20240315000999",
            "corp_code": "00126380",
            "sj_div": "IS",
            "account_id": "ifrs-full_Revenue",
            "account_nm": "매출액",
            "thstrm_amount": "170,000,000",
        },
        {
            "rcept_no": "20240315000999",
            "corp_code": "00126380",
            "sj_div": "IS",
            "account_id": "ifrs-full_GrossProfit",
            "account_nm": "매출총이익",
            "thstrm_amount": "30,000,000",
        },
        {
            "rcept_no": "20240315000999",
            "corp_code": "00126380",
            "sj_div": "IS",
            "account_id": "dart_OperatingIncomeLoss",
            "account_nm": "영업이익",
            "thstrm_amount": "-5,000,000",
        },
        {
            "rcept_no": "20240315000999",
            "corp_code": "00126380",
            "sj_div": "IS",
            "account_id": "ifrs-full_ProfitLoss",
            "account_nm": "당기순이익",
            "thstrm_amount": "-3,000,000",
        },
        {
            "rcept_no": "20240315000999",
            "corp_code": "00126380",
            "sj_div": "BS",
            "account_id": "ifrs-full_Liabilities",
            "account_nm": "부채총계",
            "thstrm_amount": "50,000,000",
        },
        {
            "rcept_no": "20240315000999",
            "corp_code": "00126380",
            "sj_div": "BS",
            "account_id": "ifrs-full_Equity",
            "account_nm": "자본총계",
            "thstrm_amount": "200,000,000",
        },
        {
            "rcept_no": "20240315000999",
            "corp_code": "00126380",
            "sj_div": "BS",
            "account_id": "ifrs-full_IssuedCapital",
            "account_nm": "자본금",
            "thstrm_amount": "500,000",
        },
    ]

    client = DartClient(api_key="TEST_KEY")
    result = client.parse_financial_accounts(
        items=raw_items,
        corp_code="00126380",
        fiscal_year=2023,
        quarter=4,
        fs_type="OFS",
    )

    assert result is not None
    assert result["fs_type"] == "OFS"
    assert result["op_income"] == -5000000.0
    # In OFS, net_income_owner is extracted from 당기순이익
    assert result["net_income_owner"] == -3000000.0


def test_dart_client_and_store_integration():
    from quant_ko.data.store import DataStore

    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "000",
        "message": "정상",
        "list": [
            {
                "rcept_no": "20240315000123",
                "bsns_year": "2023",
                "corp_code": "00126380",
                "sj_div": "IS",
                "account_id": "ifrs-full_Revenue",
                "account_nm": "매출액",
                "thstrm_amount": "258,939,300",
            },
            {
                "rcept_no": "20240315000123",
                "bsns_year": "2023",
                "corp_code": "00126380",
                "sj_div": "IS",
                "account_id": "ifrs-full_GrossProfit",
                "account_nm": "매출총이익",
                "thstrm_amount": "55,000,000",
            },
            {
                "rcept_no": "20240315000123",
                "bsns_year": "2023",
                "corp_code": "00126380",
                "sj_div": "IS",
                "account_id": "dart_OperatingIncomeLoss",
                "account_nm": "영업이익",
                "thstrm_amount": "6,567,000",
            },
            {
                "rcept_no": "20240315000123",
                "corp_code": "00126380",
                "sj_div": "IS",
                "account_id": "ifrs-full_ProfitLossAttributableToOwnersOfParent",
                "account_nm": "지배기업의소유주지분순이익",
                "thstrm_amount": "14,472,000",
            },
            {
                "rcept_no": "20240315000123",
                "corp_code": "00126380",
                "sj_div": "BS",
                "account_id": "ifrs-full_Liabilities",
                "account_nm": "부채총계",
                "thstrm_amount": "92,228,000",
            },
            {
                "rcept_no": "20240315000123",
                "corp_code": "00126380",
                "sj_div": "BS",
                "account_id": "ifrs-full_Equity",
                "account_nm": "자본총계",
                "thstrm_amount": "360,000,000",
            },
            {
                "rcept_no": "20240315000123",
                "corp_code": "00126380",
                "sj_div": "BS",
                "account_id": "ifrs-full_IssuedCapital",
                "account_nm": "자본금",
                "thstrm_amount": "897,514",
            },
        ],
    }
    mock_session.get.return_value = mock_response

    client = DartClient(api_key="TEST_KEY", session=mock_session)
    record = client.fetch_and_parse_financials("00126380", 2023, 4, fs_type="CFS")
    assert record is not None

    store = DataStore(":memory:")
    store.initialize_schema()
    store.upsert_financials([record])

    df = store.get_financials(corp_code="00126380", fiscal_year=2023, quarter=4)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["corp_code"] == "00126380"
    assert row["revenue"] == 258939300.0
    assert row["op_income"] == 6567000.0
    assert row["rcept_dt"] == "20240315"


def test_clean_amount_edge_cases():
    assert _clean_amount(None) is None
    assert _clean_amount(12345) == 12345.0
    assert _clean_amount(123.45) == 123.45
    assert _clean_amount("  -  ") == 0.0
    assert _clean_amount("") == 0.0
    assert _clean_amount("(1,234,567)") == -1234567.0
    assert _clean_amount("1,234.5") == 1234.5
    assert _clean_amount("invalid_str") is None


def test_fetch_financial_statements_invalid_quarter():
    client = DartClient(api_key="TEST_KEY")
    with pytest.raises(ValueError, match="Invalid quarter"):
        client.fetch_financial_statements(corp_code="00126380", fiscal_year=2023, quarter=5)


def test_fetch_multi_financial_statements_invalid_quarter():
    client = DartClient(api_key="TEST_KEY")
    with pytest.raises(ValueError, match="Invalid quarter"):
        client.fetch_multi_financial_statements(
            corp_codes=["00126380"], fiscal_year=2023, quarter=0
        )


def test_fetch_financial_statements_api_error():
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "020",
        "message": "요청 제한 초과",
    }
    mock_session.get.return_value = mock_response

    client = DartClient(api_key="TEST_KEY", session=mock_session)
    with pytest.raises(RuntimeError, match="요청 제한 초과"):
        client.fetch_financial_statements(corp_code="00126380", fiscal_year=2023, quarter=1)


def test_fetch_multi_financial_statements_api_error():
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "020",
        "message": "요청 제한 초과",
    }
    mock_session.get.return_value = mock_response

    client = DartClient(api_key="TEST_KEY", session=mock_session)
    with pytest.raises(RuntimeError, match="요청 제한 초과"):
        client.fetch_multi_financial_statements(
            corp_codes=["00126380"], fiscal_year=2023, quarter=1
        )


def test_parse_financial_accounts_empty_returns_none():
    client = DartClient(api_key="TEST_KEY")
    assert (
        client.parse_financial_accounts(items=[], corp_code="00126380", fiscal_year=2023, quarter=1)
        is None
    )


def test_fetch_and_parse_financials_empty():
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "013", "message": "조회된 데이타가 없습니다."}
    mock_session.get.return_value = mock_response

    client = DartClient(api_key="TEST_KEY", session=mock_session)
    assert client.fetch_and_parse_financials("00126380", 2023, 1) is None
