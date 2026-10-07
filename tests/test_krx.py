import pandas as pd
import pytest

from quant_ko.data.krx import (
    is_chinese_company,
    is_holding_or_financial,
    is_preferred_stock,
    is_spac,
    tag_stock,
)


def test_is_preferred_stock():
    # Common stocks ending in '0'
    assert not is_preferred_stock("005930", "삼성전자")
    assert not is_preferred_stock("000660", "SK하이닉스")

    # Preferred stocks ending in non-zero or letters
    assert is_preferred_stock("005935", "삼성전자우")
    assert is_preferred_stock("00593K", "삼성전자1우M")
    assert is_preferred_stock("000105", "유한양행우")
    assert is_preferred_stock("001045", "CJ우")


def test_is_spac():
    # Normal stocks
    assert not is_spac("삼성전자")
    assert not is_spac("카카오")

    # SPAC stocks
    assert is_spac("하나금융25호스팩")
    assert is_spac("삼성스팩6호")
    assert is_spac("대신밸런스제10호스팩")
    assert is_spac("IBKS제16호스팩")
    assert is_spac("Mirae Asset Daewoo SPAC 3")


def test_is_chinese_company():
    # Normal Korean stocks
    assert not is_chinese_company("삼성전자", "005930")
    assert not is_chinese_company("현대차", "005380")

    # Name contains '차이나'
    assert is_chinese_company("차이나그레이트", "900040")
    assert is_chinese_company("차이나하오란", "900090")

    # Foreign / Chinese company 900xxx series
    assert is_chinese_company("GRT", "900290")
    assert is_chinese_company("골든센츄리", "900280")
    assert is_chinese_company("크리스탈신소재", "900250")
    assert is_chinese_company("헝셩그룹", "900270")
    assert is_chinese_company("로스웰", "900260")
    assert is_chinese_company("윙입푸드", "900340")


def test_is_holding_or_financial():
    # Normal manufacturing / tech stocks
    assert not is_holding_or_financial(sector="반도체", name="삼성전자")
    assert not is_holding_or_financial(sector="소프트웨어", name="카카오")

    # Financial sectors / names
    assert is_holding_or_financial(sector="금융업", name="신한지주")
    assert is_holding_or_financial(sector="은행", name="KB금융")
    assert is_holding_or_financial(sector="증권", name="키움증권")
    assert is_holding_or_financial(sector="보험", name="삼성생명")
    assert is_holding_or_financial(sector="기타금융", name="아주캐피탈")

    # Holding companies by name
    assert is_holding_or_financial(sector="기타", name="CJ제일제당홀딩스")
    assert is_holding_or_financial(sector="서비스업", name="LG홀딩스")
    assert is_holding_or_financial(sector="제조업", name="한진칼")


def test_tag_stock():
    # Common normal stock
    tags = tag_stock(ticker="005930", name="삼성전자", sector="전기전자", market="KOSPI")
    assert tags["is_preferred"] is False
    assert tags["is_spac"] is False
    assert tags["is_chinese"] is False
    assert tags["is_financial_or_holding"] is False
    assert tags["is_excluded"] is False

    # Preferred stock
    tags_pref = tag_stock(ticker="005935", name="삼성전자우", sector="전기전자", market="KOSPI")
    assert tags_pref["is_preferred"] is True
    assert tags_pref["is_excluded"] is True

    # SPAC stock
    tags_spac = tag_stock(
        ticker="417310", name="유진스팩8호", sector="금융지원서비스업", market="KOSDAQ"
    )
    tags_spac["is_spac"] = True
    assert tags_spac["is_excluded"] is True


def test_normalize_date():
    from quant_ko.data.krx import normalize_date

    assert normalize_date("20240102") == "2024-01-02"
    assert normalize_date("2024-01-02") == "2024-01-02"
    assert normalize_date("2024.01.02") == "2024-01-02"
    assert normalize_date("2024/01/02") == "2024-01-02"
    assert normalize_date("") == ""
    assert normalize_date(None) == ""


def test_clean_price_val():
    from quant_ko.data.krx import clean_price_val

    assert clean_price_val("79,600") == 79600.0
    assert clean_price_val("1,234,567,890") == 1234567890.0
    assert clean_price_val("-100") == -100.0
    assert clean_price_val(0) == 0.0
    assert clean_price_val(None) == 0.0
    assert clean_price_val("-") == 0.0


def test_is_etf_or_etn():
    from quant_ko.data.krx import is_etf_or_etn

    assert not is_etf_or_etn("삼성전자")
    assert is_etf_or_etn("KODEX 200", sec_type="ETF")
    assert is_etf_or_etn("TIGER 미국S&P500")
    assert is_etf_or_etn("신한 레버리지 WTI원유 선물 ETN", sec_type="ETN")
    assert is_etf_or_etn("미래에셋 ELW", sec_type="ELW")


def test_fetch_ticker_list_parses_response_and_tags():
    from unittest.mock import MagicMock

    from quant_ko.data.krx import KrxClient

    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "OutBlock_1": [
            {
                "ISU_SRT_CD": "005930",
                "ISU_ABBRV": "삼성전자",
                "MKT_TP_NM": "KOSPI",
                "SECT_TP_NM": "전기전자",
                "LIST_DD": "19750611",
                "KIND_STKCERT_TP_NM": "보통주",
            },
            {
                "ISU_SRT_CD": "005935",
                "ISU_ABBRV": "삼성전자우",
                "MKT_TP_NM": "KOSPI",
                "SECT_TP_NM": "전기전자",
                "LIST_DD": "19750611",
                "KIND_STKCERT_TP_NM": "우선주",
            },
            {
                "ISU_SRT_CD": "417310",
                "ISU_ABBRV": "유진스팩8호",
                "MKT_TP_NM": "KOSDAQ",
                "SECT_TP_NM": "금융지원서비스업",
                "LIST_DD": "20220318",
                "KIND_STKCERT_TP_NM": "보통주",
            },
            {
                "ISU_SRT_CD": "069500",
                "ISU_ABBRV": "KODEX 200",
                "MKT_TP_NM": "KOSPI",
                "SECT_TP_NM": "",
                "LIST_DD": "20021014",
                "KIND_STKCERT_TP_NM": "ETF",
            },
        ]
    }
    mock_session.post.return_value = mock_resp

    client = KrxClient(session=mock_session)
    df = client.fetch_ticker_list(common_only=False)

    assert len(df) == 4
    samsung = df[df["ticker"] == "005930"].iloc[0]
    assert samsung["name"] == "삼성전자"
    assert samsung["market"] == "KOSPI"
    assert samsung["listed_at"] == "1975-06-11"
    assert samsung["is_preferred"] == 0
    assert samsung["is_spac"] == 0

    samsung_pref = df[df["ticker"] == "005935"].iloc[0]
    assert samsung_pref["is_preferred"] == 1

    spac = df[df["ticker"] == "417310"].iloc[0]
    assert spac["is_spac"] == 1


def test_fetch_ticker_list_common_only_excludes_pref_spac_etf():
    from unittest.mock import MagicMock

    from quant_ko.data.krx import KrxClient

    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "OutBlock_1": [
            {
                "ISU_SRT_CD": "005930",
                "ISU_ABBRV": "삼성전자",
                "MKT_TP_NM": "KOSPI",
                "SECT_TP_NM": "전기전자",
                "LIST_DD": "19750611",
                "KIND_STKCERT_TP_NM": "보통주",
            },
            {
                "ISU_SRT_CD": "005935",
                "ISU_ABBRV": "삼성전자우",
                "MKT_TP_NM": "KOSPI",
                "SECT_TP_NM": "전기전자",
                "LIST_DD": "19750611",
                "KIND_STKCERT_TP_NM": "우선주",
            },
            {
                "ISU_SRT_CD": "417310",
                "ISU_ABBRV": "유진스팩8호",
                "MKT_TP_NM": "KOSDAQ",
                "SECT_TP_NM": "금융지원서비스업",
                "LIST_DD": "20220318",
                "KIND_STKCERT_TP_NM": "보통주",
            },
            {
                "ISU_SRT_CD": "069500",
                "ISU_ABBRV": "KODEX 200",
                "MKT_TP_NM": "KOSPI",
                "SECT_TP_NM": "",
                "LIST_DD": "20021014",
                "KIND_STKCERT_TP_NM": "ETF",
            },
        ]
    }
    mock_session.post.return_value = mock_resp

    client = KrxClient(session=mock_session)
    df_filtered = client.fetch_ticker_list(common_only=True)

    assert len(df_filtered) == 1
    assert df_filtered.iloc[0]["ticker"] == "005930"


def test_fetch_delisted_tickers():
    from unittest.mock import MagicMock

    from quant_ko.data.krx import KrxClient

    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "OutBlock_1": [
            {
                "ISU_SRT_CD": "012340",
                "ISU_ABBRV": "과거상폐종목",
                "MKT_TP_NM": "KOSDAQ",
                "SECT_TP_NM": "제조업",
                "LIST_DD": "20100101",
                "DELIST_DD": "20180510",
                "KIND_STKCERT_TP_NM": "보통주",
            }
        ]
    }
    mock_session.post.return_value = mock_resp

    client = KrxClient(session=mock_session)
    df = client.fetch_delisted_tickers()

    assert len(df) == 1
    assert df.iloc[0]["ticker"] == "012340"
    assert df.iloc[0]["delisted_at"] == "2018-05-10"


def test_fetch_daily_prices():
    from unittest.mock import MagicMock

    from quant_ko.data.krx import KrxClient

    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "OutBlock_1": [
            {
                "ISU_SRT_CD": "005930",
                "ISU_ABBRV": "삼성전자",
                "TDD_CLSPRC": "79,600",
                "MKTCAP": "475,194,675,000,000",
                "ACC_TRDVAL": "1,234,567,890",
            },
            {
                "ISU_SRT_CD": "000660",
                "ISU_ABBRV": "SK하이닉스",
                "TDD_CLSPRC": "142,000",
                "MKTCAP": "103,376,000,000,000",
                "ACC_TRDVAL": "500,000,000",
            },
        ]
    }
    mock_session.post.return_value = mock_resp

    client = KrxClient(session=mock_session)
    df = client.fetch_daily_prices(date="2024-01-02", market="ALL")

    assert len(df) == 2
    samsung = df[df["ticker"] == "005930"].iloc[0]
    assert samsung["date"] == "2024-01-02"
    assert samsung["close"] == 79600.0
    assert samsung["market_cap"] == 475194675000000.0
    assert samsung["trading_value"] == 1234567890.0


def test_fetch_designations():
    from unittest.mock import MagicMock

    from quant_ko.data.krx import KrxClient

    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "OutBlock_1": [
            {
                "ISU_SRT_CD": "000001",
                "DSG_TP_NM": "관리종목",
                "DSG_DD": "20230320",
                "RLS_DD": "20230901",
            },
            {
                "ISU_SRT_CD": "000002",
                "DSG_TP_NM": "투자주의환기종목",
                "DSG_DD": "20230502",
                "RLS_DD": "",
            },
            {
                "ISU_SRT_CD": "000003",
                "DSG_TP_NM": "매매거래정지",
                "DSG_DD": "20230601",
                "RLS_DD": "20230615",
            },
        ]
    }
    mock_session.post.return_value = mock_resp

    client = KrxClient(session=mock_session)
    df = client.fetch_designations(date="2023-06-05")

    assert len(df) == 3
    rec1 = df[df["ticker"] == "000001"].iloc[0]
    assert rec1["type"] == "관리"
    assert rec1["start_date"] == "2023-03-20"
    assert rec1["end_date"] == "2023-09-01"

    rec2 = df[df["ticker"] == "000002"].iloc[0]
    assert rec2["type"] == "투자주의환기"
    assert rec2["start_date"] == "2023-05-02"
    assert pd.isna(rec2["end_date"]) or rec2["end_date"] is None

    rec3 = df[df["ticker"] == "000003"].iloc[0]

    assert rec3["type"] == "거래정지"


def test_ingest_companies_into_store():
    from unittest.mock import MagicMock

    from quant_ko.data.krx import KrxClient, KrxIngestor
    from quant_ko.data.store import DataStore

    store = DataStore(":memory:")
    store.initialize_schema()

    mock_client = MagicMock(spec=KrxClient)
    mock_client.fetch_ticker_list.return_value = pd.DataFrame(
        [
            {
                "ticker": "005930",
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
                "ticker": "417310",
                "name": "유진스팩8호",
                "market": "KOSDAQ",
                "sector": "금융지원",
                "listed_at": "2022-03-18",
                "delisted_at": None,
                "fiscal_month": 12,
                "is_preferred": 0,
                "is_spac": 1,
            },
        ]
    )
    mock_client.fetch_delisted_tickers.return_value = pd.DataFrame(
        [
            {
                "ticker": "012340",
                "name": "과거상폐종목",
                "market": "KOSDAQ",
                "sector": "제조업",
                "listed_at": "2010-01-01",
                "delisted_at": "2018-05-10",
                "fiscal_month": 12,
                "is_preferred": 0,
                "is_spac": 0,
            }
        ]
    )

    ingestor = KrxIngestor(client=mock_client, store=store)
    count = ingestor.ingest_companies(include_delisted=True)

    assert count == 3
    df_db = store.get_companies()
    assert len(df_db) == 3
    assert set(df_db["ticker"]) == {"005930", "417310", "012340"}
    samsung = df_db[df_db["ticker"] == "005930"].iloc[0]
    assert samsung["is_preferred"] == 0
    assert samsung["is_spac"] == 0

    spac = df_db[df_db["ticker"] == "417310"].iloc[0]
    assert spac["is_spac"] == 1

    delisted = df_db[df_db["ticker"] == "012340"].iloc[0]
    assert delisted["delisted_at"] == "2018-05-10"


def test_ingest_daily_prices_into_store():
    from unittest.mock import MagicMock

    from quant_ko.data.krx import KrxClient, KrxIngestor
    from quant_ko.data.store import DataStore

    store = DataStore(":memory:")
    store.initialize_schema()

    mock_client = MagicMock(spec=KrxClient)
    mock_client.fetch_daily_prices.return_value = pd.DataFrame(
        [
            {
                "ticker": "005930",
                "date": "2024-01-02",
                "close": 79600.0,
                "market_cap": 4750000.0,
                "trading_value": 100000.0,
            },
            {
                "ticker": "000660",
                "date": "2024-01-02",
                "close": 142000.0,
                "market_cap": 1030000.0,
                "trading_value": 50000.0,
            },
        ]
    )

    ingestor = KrxIngestor(client=mock_client, store=store)
    count = ingestor.ingest_daily_prices(date="2024-01-02")

    assert count == 2
    df_db = store.get_daily_prices(ticker="005930")
    assert len(df_db) == 1
    assert df_db.iloc[0]["close"] == 79600.0
    assert df_db.iloc[0]["market_cap"] == 4750000.0


def test_ingest_designations_into_store():
    from unittest.mock import MagicMock

    from quant_ko.data.krx import KrxClient, KrxIngestor
    from quant_ko.data.store import DataStore

    store = DataStore(":memory:")
    store.initialize_schema()

    mock_client = MagicMock(spec=KrxClient)
    mock_client.fetch_designations.return_value = pd.DataFrame(
        [
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
    )

    ingestor = KrxIngestor(client=mock_client, store=store)
    count = ingestor.ingest_designations(date="2023-06-05")

    assert count == 2
    df_db = store.get_designations(ticker="000001")
    assert len(df_db) == 1
    assert df_db.iloc[0]["type"] == "관리"


def test_ingest_companies_with_corp_code_mapping():
    from unittest.mock import MagicMock

    from quant_ko.data.krx import KrxClient, KrxIngestor
    from quant_ko.data.store import DataStore

    store = DataStore(":memory:")
    store.initialize_schema()

    mock_client = MagicMock(spec=KrxClient)
    mock_client.fetch_ticker_list.return_value = pd.DataFrame(
        [
            {
                "ticker": "005930",
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
    mock_client.fetch_delisted_tickers.return_value = pd.DataFrame()

    ticker_map = {"005930": "00126380"}
    ingestor = KrxIngestor(client=mock_client, store=store)
    ingestor.ingest_companies(include_delisted=False, ticker_to_corp_code=ticker_map)

    df_db = store.get_companies(tickers=["005930"])
    assert len(df_db) == 1
    assert df_db.iloc[0]["corp_code"] == "00126380"


def test_krx_api_error_on_http_failure():
    from unittest.mock import MagicMock

    import requests

    from quant_ko.data.krx import KrxAPIError, KrxClient

    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
    mock_session.post.return_value = mock_resp

    client = KrxClient(session=mock_session)
    with pytest.raises(KrxAPIError):
        client.fetch_ticker_list()


def test_krx_client_offline_mode():
    from quant_ko.data.krx import KrxClient

    # Offline mode should not attempt network connections
    client = KrxClient(offline=True)
    df_tickers = client.fetch_ticker_list()
    assert isinstance(df_tickers, pd.DataFrame)

    df_prices = client.fetch_daily_prices(date="2024-01-02")
    assert isinstance(df_prices, pd.DataFrame)

    df_desig = client.fetch_designations(date="2024-01-02")
    assert isinstance(df_desig, pd.DataFrame)
