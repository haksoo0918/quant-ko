"""Korea Investment & Securities (한국투자증권 Open API) Client."""

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import requests

logger = logging.getLogger(__name__)

MOCK_BASE_URL = "https://openapivts.koreainvestment.com:29443"
REAL_BASE_URL = "https://openapi.koreainvestment.com:9443"


@dataclass
class Position:
    """Represents a held stock position."""

    ticker: str
    name: str
    qty: int
    current_price: float
    eval_amount: float
    purchase_price: float = 0.0


@dataclass
class Balance:
    """Represents account balance and positions."""

    cash: float
    total_eval_amount: float
    positions: list[Position] = field(default_factory=list)


@dataclass
class OrderResult:
    """Represents an order placement outcome."""

    order_no: str
    ticker: str
    side: str
    qty: int
    price: float
    success: bool
    message: str = ""


class KisClient:
    """Korea Investment & Securities REST API client for mock and real trading."""

    def __init__(
        self,
        app_key: str | None = None,
        app_secret: str | None = None,
        account_no: str | None = None,
        is_mock: bool | None = None,
        session: requests.Session | None = None,
    ) -> None:
        # Determine mode if not explicitly passed
        if is_mock is None:
            mode = os.getenv("KIS_MODE", "MOCK").strip().upper()
            self.is_mock = mode != "REAL"
        else:
            self.is_mock = is_mock

        # Prefix for dual env vars: KIS_MOCK_* vs KIS_REAL_*
        prefix = "KIS_MOCK_" if self.is_mock else "KIS_REAL_"

        self.app_key = app_key or os.getenv(f"{prefix}APP_KEY") or os.getenv("KIS_APP_KEY", "")
        self.app_secret = (
            app_secret or os.getenv(f"{prefix}APP_SECRET") or os.getenv("KIS_APP_SECRET", "")
        )

        acc = (
            account_no
            or os.getenv(f"{prefix}CANO")
            or os.getenv(f"{prefix}ACCOUNT_NO")
            or os.getenv("KIS_CANO")
            or os.getenv("KIS_ACCOUNT_NO", "")
        )
        prdt = os.getenv(f"{prefix}ACNT_PRDT_CD") or os.getenv("KIS_ACNT_PRDT_CD", "01")

        # Parse account number (e.g. "12345678-01" or "1234567801" or "12345678")
        clean_acc = acc.replace("-", "").strip()
        if len(clean_acc) >= 10:
            self.account_prefix = clean_acc[:8]
            self.account_suffix = clean_acc[8:10]
        else:
            self.account_prefix = clean_acc
            self.account_suffix = prdt.strip() or "01"

        self.base_url = MOCK_BASE_URL if self.is_mock else REAL_BASE_URL
        self.session = session or requests.Session()
        self.token_cache_file = f"data/kis_token_{'mock' if self.is_mock else 'real'}.json"

        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

    def get_access_token(self) -> str:
        """Fetch or return cached OAuth access token (in-memory and file persistence)."""
        now = time.time()
        # 1. Check in-memory cache
        if self._access_token and now < self._token_expires_at - 60:
            return self._access_token

        # 2. Check file cache (KIS token is valid for 24 hours, limited to 1 request per minute)
        import json

        if os.path.exists(self.token_cache_file):
            try:
                with open(self.token_cache_file, encoding="utf-8") as f:
                    cache_data = json.load(f)
                cached_token = cache_data.get("access_token")
                cached_expires = float(cache_data.get("expires_at", 0))
                if cached_token and now < cached_expires - 60:
                    self._access_token = cached_token
                    self._token_expires_at = cached_expires
                    return self._access_token
            except Exception:
                pass

        # 3. Request new token from KIS API
        url = f"{self.base_url}/oauth2/tokenP"
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
        resp = self.session.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()

        self._access_token = data["access_token"]
        expires_in = float(data.get("expires_in", 86400))
        self._token_expires_at = now + expires_in

        # Persist to disk
        try:
            with open(self.token_cache_file, "w", encoding="utf-8") as f:
                json.dump(
                    {"access_token": self._access_token, "expires_at": self._token_expires_at},
                    f,
                )
        except Exception:
            pass

        return self._access_token

    def _get_headers(self, tr_id: str) -> dict[str, str]:
        """Construct standard API request headers."""
        token = self.get_access_token()
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
        }

    def fetch_current_price(self, ticker: str) -> float:
        """Inquire current stock price."""
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = self._get_headers(tr_id="FHKST01010100")
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker,
        }
        resp = self.session.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()

        output = data.get("output", {})
        price_str = output.get("stck_prpr", "0")
        return float(price_str)

    def fetch_balance(self) -> Balance:
        """Inquire account balance and current held stock positions."""
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        tr_id = "VTTC8434R" if self.is_mock else "TTTC8434R"
        headers = self._get_headers(tr_id=tr_id)
        params = {
            "CANO": self.account_prefix,
            "ACNT_PRDT_CD": self.account_suffix,
            "AFHR_FLG": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        resp = self.session.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()

        # Parse positions (output1)
        positions: list[Position] = []
        for item in data.get("output1", []):
            qty = int(item.get("hld_qty", 0))
            if qty <= 0:
                continue
            positions.append(
                Position(
                    ticker=str(item.get("pdno", "")).strip(),
                    name=str(item.get("prdt_name", "")).strip(),
                    qty=qty,
                    current_price=float(item.get("prpr", 0.0)),
                    eval_amount=float(item.get("evlu_amt", 0.0)),
                    purchase_price=float(item.get("pchs_avg_pric", 0.0)),
                )
            )

        # Parse totals (output2)
        output2 = data.get("output2", [{}])
        tot_summary = output2[0] if output2 else {}
        cash = float(tot_summary.get("dnca_tot_amt", 0.0))
        total_eval = float(tot_summary.get("tot_evlu_amt", 0.0))

        return Balance(cash=cash, total_eval_amount=total_eval, positions=positions)

    def place_order(
        self,
        ticker: str,
        side: str,
        qty: int,
        price: float = 0.0,
        order_type: str = "01",  # "01": 시장가 (15:20 동시호가 100% 체결), "00": 지정가
    ) -> OrderResult:
        """Place cash BUY / SELL order (01: 시장가, 00: 지정가)."""
        side_upper = side.upper()
        if side_upper == "BUY":
            tr_id = "VTTC0802U" if self.is_mock else "TTTC0802U"
        elif side_upper == "SELL":
            tr_id = "VTTC0801U" if self.is_mock else "TTTC0801U"
        else:
            raise ValueError(f"Invalid order side: {side}. Must be 'BUY' or 'SELL'.")

        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-cash"
        headers = self._get_headers(tr_id=tr_id)
        order_price_str = "0" if order_type == "01" else str(int(price))
        body = {
            "CANO": self.account_prefix,
            "ACNT_PRDT_CD": self.account_suffix,
            "PDNO": ticker,
            "ORD_DVSN": order_type,
            "ORD_QTY": str(qty),
            "ORD_UNPR": order_price_str,
        }
        resp = self.session.post(url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()

        is_success = data.get("rt_cd") == "0"
        output = data.get("output", {})
        order_no = output.get("ODNO", "")
        msg = data.get("msg1", "")

        return OrderResult(
            order_no=order_no,
            ticker=ticker,
            side=side_upper,
            qty=qty,
            price=float(price),
            success=is_success,
            message=msg,
        )

    def fetch_orders(self, date: str | None = None) -> list[dict[str, Any]]:
        """Inquire daily executed and unexecuted orders."""
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
        tr_id = "VTTC8001R" if self.is_mock else "TTTC8001R"
        headers = self._get_headers(tr_id=tr_id)

        target_date = (date or time.strftime("%Y%m%d")).replace("-", "")
        params = {
            "CANO": self.account_prefix,
            "ACNT_PRDT_CD": self.account_suffix,
            "INQR_STRT_DT": target_date,
            "INQR_END_DT": target_date,
            "SLL_BUY_DVSN_CD": "00",
            "INQR_DVSN": "00",
            "PDNO": "",
            "CCLD_DVSN": "00",
            "ORD_GNO_BRNO": "",
            "ODNO": "",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        resp = self.session.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()

        orders: list[dict[str, Any]] = []
        for item in data.get("output1", []):
            ord_qty = int(item.get("ord_qty", 0))
            filled_qty = int(item.get("tot_ccld_qty", 0))
            stat_name = item.get("prcs_stat_name", "")

            if filled_qty == ord_qty and ord_qty > 0:
                status = "FILLED"
            elif filled_qty > 0:
                status = "PARTIAL"
            elif "취소" in stat_name:
                status = "CANCELLED"
            else:
                status = "UNFILLED"

            orders.append(
                {
                    "order_no": item.get("odno", ""),
                    "ticker": item.get("pdno", ""),
                    "side": "BUY" if item.get("sll_buy_dvsn_cd") in ("02", "BUY") else "SELL",
                    "order_qty": ord_qty,
                    "filled_qty": filled_qty,
                    "order_price": float(item.get("ord_unpr", 0.0)),
                    "status": status,
                    "raw_status": stat_name,
                }
            )

        return orders
