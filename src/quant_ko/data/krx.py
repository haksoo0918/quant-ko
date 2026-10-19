"""KRX Data Collector and Ingestion Module.

Handles ticker listing, price history, market capitalization, designations,
and exclusion filtering according to PRD strategy requirements.
"""

from typing import Any

import pandas as pd
import requests

# Known Chinese companies listed on Korean exchanges (KOSPI/KOSDAQ)
CHINESE_COMPANY_NAMES = {
    "GRT",
    "골든센츄리",
    "크리스탈신소재",
    "헝셩그룹",
    "로스웰",
    "윙입푸드",
    "씨케이에이치",
    "에스앤씨엔진그룹",
    "이스트아시아홀딩스",
    "차이나그레이트",
    "차이나하오란",
    "완리",
    "웨이포트",
    "평산차업",
    "연합과기",
    "중국원양자원",
    "오가닉티코스메틱",
    "컬러레이",
    "JTC",
}

# Known holding companies that may not end with '홀딩스' or '지주'
KNOWN_HOLDING_COMPANIES = {
    "한진칼",
    "CJ",
    "SK",
    "LG",
    "GS",
    "LS",
    "두산",
    "효성",
    "하림지주",
}

FINANCIAL_SECTOR_KEYWORDS = (
    "금융",
    "은행",
    "증권",
    "보험",
    "카드",
    "캐피탈",
    "저축은행",
    "종금",
    "여신",
    "투자회사",
    "지주회사",
)

ETF_NAME_PREFIXES = (
    "KODEX",
    "TIGER",
    "KBSTAR",
    "ACE",
    "SOL",
    "KOSEF",
    "PLUS",
    "ARIRANG",
    "HANARO",
    "TIMEFOLIO",
    "WOORI",
    "FOCUS",
    "TREX",
)


def normalize_date(val: Any) -> str:
    """Normalize various date formats (e.g. '20240102', '2024.01.02') into 'YYYY-MM-DD'."""
    if not val:
        return ""
    s = str(val).strip()
    if not s:
        return ""
    # Remove separators
    s_clean = s.replace("-", "").replace(".", "").replace("/", "")
    if len(s_clean) == 8 and s_clean.isdigit():
        return f"{s_clean[:4]}-{s_clean[4:6]}-{s_clean[6:]}"
    return s


def clean_price_val(val: Any) -> float:
    """Parse numeric values from KRX formatted strings (e.g. '79,600', '-') into float."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(",", "")
    if not s or s == "-":
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def is_etf_or_etn(name: str, sec_type: str = "") -> bool:
    """Determine if security is an ETF, ETN, or ELW derivative."""
    type_upper = (sec_type or "").upper().strip()
    if any(t in type_upper for t in ("ETF", "ETN", "ELW", "신주인수권")):
        return True
    name_upper = (name or "").upper().strip()
    if any(p in name_upper for p in ETF_NAME_PREFIXES):
        return True
    if any(t in name_upper for t in ("ETN", "ELW")):
        return True
    return False


def is_preferred_stock(ticker: str, name: str = "") -> bool:
    """Determine if a stock is a preferred share.

    In the KRX numbering convention, common stocks end in '0'.
    Preferred shares end in non-zero numbers ('5', '7', '9') or characters ('K', 'L', 'M').
    """
    if not ticker:
        return False
    # Standard KRX rule: Common stocks end with '0'
    if not ticker.endswith("0"):
        return True
    if name:
        clean_name = name.strip()
        if clean_name.endswith(("우", "우B", "우C", "1우", "2우B", "3우B", "(우)")):
            return True
    return False


def is_spac(name: str, ticker: str = "") -> bool:
    """Determine if a stock is a SPAC (Special Purpose Acquisition Company)."""
    if not name:
        return False
    upper_name = name.upper().strip()
    return "스팩" in upper_name or "SPAC" in upper_name


def is_chinese_company(name: str, ticker: str = "") -> bool:
    """Determine if a stock represents a Chinese-headquartered / high-risk foreign entity."""
    if "차이나" in name:
        return True
    if name in CHINESE_COMPANY_NAMES:
        return True
    if ticker:
        # KRX foreign (predominantly Chinese) stock codes start with 900xxx
        if ticker.startswith("900"):
            return True
    return False


def is_holding_or_financial(sector: str = "", name: str = "") -> bool:
    """Determine if a company is in financial or holding company sectors."""
    clean_sec = (sector or "").strip()
    clean_nm = (name or "").strip()

    for kw in FINANCIAL_SECTOR_KEYWORDS:
        if kw in clean_sec or kw in clean_nm:
            return True

    if clean_nm.endswith(("홀딩스", "지주", "지주회사", "Holdings", "HOLDINGS")):
        return True

    if clean_nm in KNOWN_HOLDING_COMPANIES:
        return True

    return False


def tag_stock(
    ticker: str,
    name: str = "",
    sector: str = "",
    market: str = "",
) -> dict[str, Any]:
    """Tag stock metadata with exclusion flags required by the quant-ko strategy."""
    pref = is_preferred_stock(ticker, name)
    spac = is_spac(name, ticker)
    chinese = is_chinese_company(name, ticker)
    fin_hold = is_holding_or_financial(sector, name)

    is_excluded = pref or spac or chinese or fin_hold

    return {
        "ticker": ticker,
        "name": name,
        "sector": sector,
        "market": market,
        "is_preferred": pref,
        "is_spac": spac,
        "is_chinese": chinese,
        "is_financial_or_holding": fin_hold,
        "is_excluded": is_excluded,
    }


class KrxAPIError(Exception):
    """Exception raised when KRX API or scraping requests fail."""


def normalize_designation_type(raw_type: str) -> str:
    """Normalize designation type name into standard types: 관리, 투자주의환기, 거래정지."""
    s = (raw_type or "").strip()
    if "관리" in s:
        return "관리"
    if "환기" in s or "주의" in s:
        return "투자주의환기"
    if "정지" in s:
        return "거래정지"
    return s


class KrxClient:
    """Client for fetching stock metadata, daily market data, and designations from KRX."""

    DEFAULT_BASE_URL = "http://data.krx.co.kr/comm/bldAttPage/getJsonData.cmd"

    def __init__(
        self,
        base_url: str | None = None,
        session: requests.Session | None = None,
        api_key: str | None = None,
        offline: bool = False,
        offline_mode: bool | None = None,
    ) -> None:
        self.base_url = base_url or self.DEFAULT_BASE_URL
        self.session = session or requests.Session()
        self.api_key = api_key
        self.offline = offline_mode if offline_mode is not None else offline

        if not session:
            self.session.headers.update(
                {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Referer": "http://data.krx.co.kr/",
                }
            )

    def _post(self, data: dict[str, Any]) -> dict[str, Any]:
        """Send POST request to KRX scraping endpoint."""
        if self.offline:
            return {"OutBlock_1": []}
        try:
            headers = {}
            if self.api_key:
                headers["AUTH_KEY"] = self.api_key
            resp = self.session.post(self.base_url, data=data, headers=headers, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            if self.offline:
                return {"OutBlock_1": []}
            raise KrxAPIError(f"KRX request failed: {e}") from e

    def fetch_ticker_list(
        self,
        market: str = "ALL",
        date: str | None = None,
        common_only: bool = False,
    ) -> pd.DataFrame:
        """Fetch list of listed tickers on KRX (KOSPI, KOSDAQ)."""
        mkt_code_map = {"ALL": "ALL", "KOSPI": "STK", "KOSDAQ": "KSQ"}
        mkt_id = mkt_code_map.get(market.upper(), market)

        payload = {
            "bld": "dbms/MDC/STAT/standard/MDCSTAT01901",
            "mktId": mkt_id,
        }
        if date:
            payload["trdDd"] = date.replace("-", "").replace(".", "")

        res_json = self._post(payload)
        items = res_json.get("OutBlock_1") or res_json.get("output") or res_json.get("block1") or []

        rows = []
        for it in items:
            ticker = str(it.get("ISU_SRT_CD") or it.get("ticker") or "").strip()
            name = str(it.get("ISU_ABBRV") or it.get("ISU_NM") or it.get("name") or "").strip()
            mkt = str(it.get("MKT_TP_NM") or it.get("MKT_NM") or it.get("market") or "").strip()
            sec = str(it.get("SECT_TP_NM") or it.get("sector") or "").strip()
            list_dd = normalize_date(it.get("LIST_DD") or it.get("listed_at") or "")
            delist_dd = normalize_date(it.get("DELIST_DD") or it.get("delisted_at") or "")
            sec_type = str(it.get("KIND_STKCERT_TP_NM") or it.get("sec_type") or "").strip()

            if not ticker:
                continue

            # Exclude KONEX from universe
            if mkt.upper() == "KONEX":
                continue

            pref = 1 if is_preferred_stock(ticker, name) else 0
            spac = 1 if is_spac(name, ticker) else 0
            etf = is_etf_or_etn(name, sec_type)
            chinese = 1 if is_chinese_company(name, ticker) else 0
            fin_hold = 1 if is_holding_or_financial(sec, name) else 0

            if common_only:
                # Common stocks only: exclude preferred, spac, etf, chinese companies
                if pref or spac or etf or chinese:
                    continue

            rows.append(
                {
                    "ticker": ticker,
                    "corp_code": None,
                    "name": name,
                    "market": mkt,
                    "sector": sec,
                    "listed_at": list_dd,
                    "delisted_at": delist_dd if delist_dd else None,
                    "fiscal_month": 12,
                    "is_preferred": pref,
                    "is_spac": spac,
                    "is_chinese": chinese,
                    "is_financial_or_holding": fin_hold,
                }
            )

        return pd.DataFrame(rows)

    def fetch_delisted_tickers(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        common_only: bool = False,
    ) -> pd.DataFrame:
        """Fetch historical delisted tickers."""
        payload = {
            "bld": "dbms/MDC/STAT/standard/MDCSTAT02001",
            "mktId": "ALL",
        }
        if start_date:
            payload["strtDd"] = start_date.replace("-", "").replace(".", "")
        if end_date:
            payload["endDd"] = end_date.replace("-", "").replace(".", "")

        res_json = self._post(payload)
        items = res_json.get("OutBlock_1") or res_json.get("output") or res_json.get("block1") or []

        rows = []
        for it in items:
            ticker = str(it.get("ISU_SRT_CD") or it.get("ticker") or "").strip()
            name = str(it.get("ISU_ABBRV") or it.get("ISU_NM") or it.get("name") or "").strip()
            mkt = str(it.get("MKT_TP_NM") or it.get("MKT_NM") or it.get("market") or "").strip()
            sec = str(it.get("SECT_TP_NM") or it.get("sector") or "").strip()
            list_dd = normalize_date(it.get("LIST_DD") or it.get("listed_at") or "")
            delist_dd = normalize_date(it.get("DELIST_DD") or it.get("delisted_at") or "")
            sec_type = str(it.get("KIND_STKCERT_TP_NM") or it.get("sec_type") or "").strip()

            if not ticker:
                continue

            pref = 1 if is_preferred_stock(ticker, name) else 0
            spac = 1 if is_spac(name, ticker) else 0
            etf = is_etf_or_etn(name, sec_type)
            chinese = 1 if is_chinese_company(name, ticker) else 0

            if common_only and (pref or spac or etf or chinese):
                continue

            rows.append(
                {
                    "ticker": ticker,
                    "corp_code": None,
                    "name": name,
                    "market": mkt,
                    "sector": sec,
                    "listed_at": list_dd,
                    "delisted_at": delist_dd if delist_dd else None,
                    "fiscal_month": 12,
                    "is_preferred": pref,
                    "is_spac": spac,
                }
            )

        return pd.DataFrame(rows)

    def fetch_daily_prices(
        self,
        date: str,
        market: str = "ALL",
    ) -> pd.DataFrame:
        """Fetch daily prices and market caps for all stocks on a given trading day."""
        mkt_code_map = {"ALL": "ALL", "KOSPI": "STK", "KOSDAQ": "KSQ"}
        mkt_id = mkt_code_map.get(market.upper(), market)
        norm_date = normalize_date(date)
        trd_dd = norm_date.replace("-", "")

        payload = {
            "bld": "dbms/MDC/STAT/standard/MDCSTAT01501",
            "mktId": mkt_id,
            "trdDd": trd_dd,
        }

        res_json = self._post(payload)
        items = res_json.get("OutBlock_1") or res_json.get("output") or res_json.get("block1") or []

        rows = []
        for it in items:
            ticker = str(it.get("ISU_SRT_CD") or it.get("ticker") or "").strip()
            if not ticker:
                continue

            close = clean_price_val(it.get("TDD_CLSPRC") or it.get("close") or it.get("CLSPRC"))
            market_cap = clean_price_val(
                it.get("MKTCAP") or it.get("market_cap") or it.get("MRKT_TOT_AMT")
            )
            trading_value = clean_price_val(
                it.get("ACC_TRDVAL") or it.get("trading_value") or it.get("TRD_VAL")
            )

            rows.append(
                {
                    "ticker": ticker,
                    "date": norm_date,
                    "close": close,
                    "market_cap": market_cap,
                    "trading_value": trading_value,
                }
            )

        return pd.DataFrame(rows)

    def fetch_designations(
        self,
        date: str | None = None,
        as_of_date: str | None = None,
    ) -> pd.DataFrame:
        """Fetch special issue designations (관리종목, 투자주의환기종목, 거래정지)."""
        payload = {
            "bld": "dbms/MDC/STAT/issue/MDCSTAT02401",
            "mktId": "ALL",
        }
        target_date = date or as_of_date
        if target_date:
            payload["trdDd"] = normalize_date(target_date).replace("-", "")

        res_json = self._post(payload)
        items = res_json.get("OutBlock_1") or res_json.get("output") or res_json.get("block1") or []

        rows = []
        for it in items:
            ticker = str(it.get("ISU_SRT_CD") or it.get("ticker") or "").strip()
            if not ticker:
                continue

            raw_type = str(it.get("DSG_TP_NM") or it.get("type") or "").strip()
            desig_type = normalize_designation_type(raw_type)

            start_dd = normalize_date(it.get("DSG_DD") or it.get("start_date") or "")
            end_dd = normalize_date(it.get("RLS_DD") or it.get("end_date") or "")

            rows.append(
                {
                    "ticker": ticker,
                    "type": desig_type,
                    "start_date": start_dd,
                    "end_date": end_dd if end_dd else None,
                }
            )

        return pd.DataFrame(rows)


class KrxIngestor:
    """Ingests KRX market data into DataStore."""

    def __init__(self, client: KrxClient, store: Any) -> None:
        self.client = client
        self.store = store

    def ingest_companies(
        self,
        market: str = "ALL",
        include_delisted: bool = True,
        common_only: bool = False,
        ticker_to_corp_code: dict[str, str] | None = None,
    ) -> int:
        """Fetch active (and optionally delisted) stocks and store them in DataStore."""
        active_df = self.client.fetch_ticker_list(market=market, common_only=common_only)
        all_dfs = [active_df]

        if include_delisted:
            delisted_df = self.client.fetch_delisted_tickers(common_only=common_only)
            if not delisted_df.empty:
                all_dfs.append(delisted_df)

        combined = pd.concat(all_dfs, ignore_index=True)
        if combined.empty:
            return 0

        # Drop duplicates by ticker keeping last
        combined = combined.drop_duplicates(subset=["ticker"], keep="last")

        if "corp_code" not in combined.columns:
            combined["corp_code"] = None

        if ticker_to_corp_code:
            combined["corp_code"] = (
                combined["ticker"].map(ticker_to_corp_code).fillna(combined["corp_code"])
            )

        self.store.upsert_companies(combined)
        return len(combined)

    def ingest_daily_prices(
        self,
        date: str,
        market: str = "ALL",
    ) -> int:
        """Fetch daily prices for a given date and store them in DataStore."""
        prices_df = self.client.fetch_daily_prices(date=date, market=market)
        if prices_df.empty:
            return 0
        self.store.upsert_daily_prices(prices_df)
        return len(prices_df)

    def ingest_designations(
        self,
        date: str | None = None,
    ) -> int:
        """Fetch designations and store them in DataStore."""
        desig_df = self.client.fetch_designations(date=date)
        if desig_df.empty:
            return 0
        self.store.upsert_designations(desig_df)
        return len(desig_df)
