"""OpenDART API Client for fetching company info and financial statements."""

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from typing import Any

import pandas as pd
import requests

REPRT_CODE_MAP = {
    1: "11013",  # 1분기보고서
    2: "11012",  # 반기보고서
    3: "11014",  # 3분기보고서
    4: "11011",  # 사업보고서
}


def _clean_amount(val: Any) -> float | None:
    """Parse raw financial statement number string into float."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)

    s = str(val).strip().replace(",", "")
    if not s or s == "-":
        return 0.0

    # Handle parenthesis format for negative values: "(1000)" -> "-1000"
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]

    try:
        return float(s)
    except ValueError:
        return None


class DartClient:
    """Client for interacting with OpenDART API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://opendart.fss.or.kr/api",
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self._corp_codes_cache: pd.DataFrame | None = None

    def fetch_corp_codes(self, only_listed: bool = True) -> pd.DataFrame:
        """Download corpCode.xml zip file from OpenDART and parse into DataFrame."""
        url = f"{self.base_url}/corpCode.xml"
        params = {"crtfc_key": self.api_key}

        response = self.session.get(url, params=params)
        response.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            xml_data = zf.read("CORPCODE.xml")

        root = ET.fromstring(xml_data)
        rows: list[dict[str, Any]] = []
        for item in root.findall("list"):
            corp_code = item.findtext("corp_code", default="").strip()
            corp_name = item.findtext("corp_name", default="").strip()
            stock_code = item.findtext("stock_code", default="").strip()
            modify_date = item.findtext("modify_date", default="").strip()

            if only_listed and not stock_code:
                continue

            rows.append(
                {
                    "ticker": stock_code,
                    "corp_code": corp_code,
                    "name": corp_name,
                    "modify_date": modify_date,
                }
            )

        df = pd.DataFrame(rows)
        self._corp_codes_cache = df
        return df

    def get_ticker_to_corp_code(self, only_listed: bool = True) -> dict[str, str]:
        """Return mapping of stock ticker (6 digits) to OpenDART 8-digit corp_code."""
        if self._corp_codes_cache is None:
            self.fetch_corp_codes(only_listed=only_listed)
        assert self._corp_codes_cache is not None
        df = self._corp_codes_cache
        if only_listed:
            df = df[df["ticker"].astype(str).str.strip() != ""]
        return dict(zip(df["ticker"], df["corp_code"], strict=False))

    def fetch_financial_statements(
        self,
        corp_code: str,
        fiscal_year: int,
        quarter: int,
        fs_type: str = "CFS",
    ) -> list[dict[str, Any]]:
        """Fetch all financial statement accounts for a single company."""
        reprt_code = REPRT_CODE_MAP.get(quarter)
        if not reprt_code:
            raise ValueError(f"Invalid quarter: {quarter}. Must be 1, 2, 3, or 4.")

        url = f"{self.base_url}/fnlttSinglAcntAll.json"
        params = {
            "crtfc_key": self.api_key,
            "corp_code": corp_code,
            "bsns_year": str(fiscal_year),
            "reprt_code": reprt_code,
            "fs_div": fs_type,
        }

        response = self.session.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        status = data.get("status")
        if status == "013":  # No data
            return []
        if status != "000":
            msg = data.get("message", "Unknown error")
            raise RuntimeError(f"OpenDART API error: {msg} (status: {status})")

        return data.get("list", [])

    def fetch_multi_financial_statements(
        self,
        corp_codes: list[str],
        fiscal_year: int,
        quarter: int,
    ) -> list[dict[str, Any]]:
        """Fetch key financial accounts for multiple companies (up to 100)."""
        reprt_code = REPRT_CODE_MAP.get(quarter)
        if not reprt_code:
            raise ValueError(f"Invalid quarter: {quarter}. Must be 1, 2, 3, or 4.")

        url = f"{self.base_url}/fnlttMultiAcnt.json"
        params = {
            "crtfc_key": self.api_key,
            "corp_code": ",".join(corp_codes),
            "bsns_year": str(fiscal_year),
            "reprt_code": reprt_code,
        }

        response = self.session.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        status = data.get("status")
        if status == "013":
            return []
        if status != "000":
            msg = data.get("message", "Unknown error")
            raise RuntimeError(f"OpenDART API error: {msg} (status: {status})")

        return data.get("list", [])

    def parse_financial_accounts(
        self,
        items: list[dict[str, Any]],
        corp_code: str,
        fiscal_year: int,
        quarter: int,
        fs_type: str = "CFS",
    ) -> dict[str, Any] | None:
        """Parse raw OpenDART items into standardized 7-metric record for financials table."""
        if not items:
            return None

        # Extract rcept_dt
        rcept_dt = None
        for item in items:
            rcept_no = item.get("rcept_no", "")
            if rcept_no and len(rcept_no) >= 8:
                rcept_dt = rcept_no[:8]
                break
            if item.get("rcept_dt"):
                rcept_dt = item["rcept_dt"]
                break

        revenue: float | None = None
        gross_profit: float | None = None
        op_income: float | None = None
        net_income_owner: float | None = None
        fallback_net_income: float | None = None
        total_liabilities: float | None = None
        total_equity: float | None = None
        capital_stock: float | None = None

        for item in items:
            sj_div = item.get("sj_div", "").upper()
            acc_id = item.get("account_id", "")
            acc_nm = item.get("account_nm", "").strip()
            norm_nm = re.sub(r"\s+", "", acc_nm)
            amount = _clean_amount(item.get("thstrm_amount"))

            if amount is None:
                continue

            # 1. 매출액
            if (
                acc_id in ("ifrs-full_Revenue", "ifrs_Revenue", "dart_Revenue")
                or "매출액" in norm_nm
                or "수익(매출액)" in norm_nm
            ) and sj_div in ("IS", "CIS", ""):
                if revenue is None:
                    revenue = amount

            # 2. 매출총이익
            if (
                acc_id in ("ifrs-full_GrossProfit", "dart_GrossProfit") or "매출총이익" in norm_nm
            ) and sj_div in ("IS", "CIS", ""):
                if gross_profit is None:
                    gross_profit = amount

            # 3. 영업이익
            if (
                acc_id
                in (
                    "dart_OperatingIncomeLoss",
                    "ifrs-full_OperatingProfit",
                    "ifrs-full_OperatingIncomeLoss",
                )
                or ("영업이익" in norm_nm and "영업외" not in norm_nm and "기타영업" not in norm_nm)
            ) and sj_div in ("IS", "CIS", ""):
                if op_income is None:
                    op_income = amount

            # 4. 순이익 / 당기순이익-지배주주
            # General fallback net income
            if (
                acc_id in ("ifrs-full_ProfitLoss", "dart_ProfitLoss")
                or norm_nm in ("당기순이익", "당기순손익", "당기순이익(손실)")
            ) and sj_div in ("IS", "CIS", ""):
                if fallback_net_income is None:
                    fallback_net_income = amount

            if fs_type == "CFS":
                if (
                    acc_id
                    in (
                        "ifrs-full_ProfitLossAttributableToOwnersOfParent",
                        "dart_ProfitLossAttributableToOwnersOfParent",
                    )
                    or (
                        "지배" in norm_nm
                        and any(
                            k in norm_nm
                            for k in ("순이익", "당기순이익", "소유주지분", "지분순이익")
                        )
                    )
                ) and sj_div in ("IS", "CIS", ""):
                    if net_income_owner is None:
                        net_income_owner = amount
            else:
                # In OFS (별도), owner profit is the entire net income
                if (
                    acc_id
                    in ("ifrs-full_ProfitLoss", "ifrs-full_ProfitLossAttributableToOwnersOfParent")
                    or norm_nm in ("당기순이익", "당기순손익", "당기순이익(손실)")
                ) and sj_div in ("IS", "CIS", ""):
                    if net_income_owner is None:
                        net_income_owner = amount

            # 5. 부채총계
            if (
                acc_id in ("ifrs-full_Liabilities", "ifrs_Liabilities") or "부채총계" in norm_nm
            ) and sj_div in ("BS", ""):
                if total_liabilities is None:
                    total_liabilities = amount

            # 6. 자본총계
            if (
                acc_id in ("ifrs-full_Equity", "ifrs_Equity") or "자본총계" in norm_nm
            ) and sj_div in ("BS", ""):
                if total_equity is None:
                    total_equity = amount

            # 7. 자본금
            if (
                acc_id in ("ifrs-full_IssuedCapital", "ifrs_IssuedCapital")
                or norm_nm in ("자본금", "보통주자본금", "납입자본")
            ) and sj_div in ("BS", ""):
                if capital_stock is None:
                    capital_stock = amount

        # Fallback for net_income_owner if CFS didn't report separate parent profit
        if net_income_owner is None:
            net_income_owner = fallback_net_income

        return {
            "corp_code": corp_code,
            "fiscal_year": fiscal_year,
            "quarter": quarter,
            "fs_type": fs_type,
            "revenue": revenue,
            "gross_profit": gross_profit,
            "op_income": op_income,
            "net_income_owner": net_income_owner,
            "total_liabilities": total_liabilities,
            "total_equity": total_equity,
            "capital_stock": capital_stock,
            "rcept_dt": rcept_dt or "",
        }

    def fetch_and_parse_financials(
        self,
        corp_code: str,
        fiscal_year: int,
        quarter: int,
        fs_type: str = "CFS",
    ) -> dict[str, Any] | None:
        """Fetch statements from OpenDART and return parsed financial metrics record."""
        items = self.fetch_financial_statements(
            corp_code=corp_code,
            fiscal_year=fiscal_year,
            quarter=quarter,
            fs_type=fs_type,
        )
        if not items:
            return None
        return self.parse_financial_accounts(
            items=items,
            corp_code=corp_code,
            fiscal_year=fiscal_year,
            quarter=quarter,
            fs_type=fs_type,
        )
