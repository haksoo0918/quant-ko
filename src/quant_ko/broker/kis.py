"""Korea Investment & Securities (한국투자증권 Open API) Client."""

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

MOCK_BASE_URL = "https://openapivts.koreainvestment.com:29443"
REAL_BASE_URL = "https://openapi.koreainvestment.com:9443"


def get_krx_tick_size(price: float, is_etf: bool = False) -> int:
    """KRX 호가 단위를 반환합니다 (일반 주식 통합 호가 단위 및 ETF 호가 단위 적용)."""
    if is_etf:
        return 5 if price >= 2000 else 1
    if price < 2000:
        return 1
    if price < 5000:
        return 5
    if price < 20000:
        return 10
    if price < 50000:
        return 50
    if price < 200000:
        return 100
    if price < 500000:
        return 500
    return 1000


def round_to_krx_tick(price: float, is_etf: bool = False, mode: str = "floor") -> float:
    """주어진 가격을 KRX 호가 단위에 맞춰 내림(floor), 올림(ceil), 반올림(round)합니다."""
    import math

    if price <= 0:
        return 0.0
    tick = get_krx_tick_size(price, is_etf=is_etf)
    if mode == "ceil":
        return float(math.ceil(price / tick) * tick)
    if mode == "round":
        return float(round(price / tick) * tick)
    return float(math.floor(price / tick) * tick)


def calc_buy_limit_price(
    current_price: float,
    buffer_pct: float = 0.05,
    is_etf: bool = False,
    upper_limit: float | None = None,
) -> float:
    """장마감 동시호가(15:20) 매수 체결 보장 및 상한가(+30%) 증거금 잠김 방지를 위한 지정가를 산출합니다."""
    if current_price <= 0:
        return 0.0
    raw_target = current_price * (1.0 + buffer_pct)
    if isinstance(upper_limit, (int, float)) and upper_limit > 0:
        raw_target = min(raw_target, float(upper_limit))
    return round_to_krx_tick(raw_target, is_etf=is_etf, mode="floor")


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
        self.token_cache_file = str(
            Path(__file__).resolve().parents[3]
            / "data"
            / f"kis_token_{'mock' if self.is_mock else 'real'}.json"
        )

        self._access_token: str | None = None
        self._token_expires_at: float = 0.0
        self._upper_limits: dict[str, int] = {}

    def get_upper_limit(self, ticker: str) -> int | None:
        """종목의 캐싱된 당일 상한가(stck_mxpr)를 반환합니다."""
        return self._upper_limits.get(ticker)

    def get_access_token(self, force_refresh: bool = False) -> str:
        """Fetch or return cached OAuth access token (in-memory and file persistence)."""
        now = time.time()
        import json

        if force_refresh:
            self._access_token = None
            self._token_expires_at = 0.0
            if os.path.exists(self.token_cache_file):
                try:
                    os.remove(self.token_cache_file)
                except Exception:
                    pass

        # 1. Check in-memory cache
        if self._access_token and now < self._token_expires_at - 60:
            return self._access_token

        # 2. Check file cache (KIS token is valid for 24 hours, limited to 1 request per minute)
        if not force_refresh and os.path.exists(self.token_cache_file):
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
        resp = self._request("POST", url, json=payload, auth_retry=False)
        resp.raise_for_status()
        data = resp.json()

        self._access_token = data["access_token"]
        expires_in = float(data.get("expires_in", 86400))
        self._token_expires_at = now + expires_in

        # Persist to disk
        try:
            token_dir = os.path.dirname(self.token_cache_file)
            if token_dir:
                os.makedirs(token_dir, exist_ok=True)
            with open(self.token_cache_file, "w", encoding="utf-8") as f:
                json.dump(
                    {"access_token": self._access_token, "expires_at": self._token_expires_at},
                    f,
                )
        except Exception:
            pass

        return self._access_token

    def _is_token_expired(self, resp: requests.Response) -> bool:
        """Check if response indicates an expired or invalid OAuth access token."""
        if resp.status_code == 401:
            return True
        try:
            data = resp.json()
            msg_cd = str(data.get("msg_cd") or "").strip()
            # EGW00121: 유효하지 않은 token, EGW00123: 기간이 만료된 token, EGW00122: appkey 불일치
            if msg_cd in {"EGW00121", "EGW00122", "EGW00123"}:
                return True
        except Exception:
            pass
        return False

    def _request(
        self,
        method: str,
        url: str,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
        auth_retry: bool = True,
        **kwargs: Any,
    ) -> requests.Response:
        """Execute HTTP request with exponential backoff retry on network/server errors and auto token refresh."""
        attempt = 0
        while True:
            attempt += 1
            try:
                m = method.upper()
                if m == "GET":
                    resp = self.session.get(url, **kwargs)
                elif m == "POST":
                    resp = self.session.post(url, **kwargs)
                else:
                    resp = self.session.request(method=m, url=url, **kwargs)

                # Check for token expiration and auto-recover if enabled
                if auth_retry and self._is_token_expired(resp):
                    logger.warning(
                        "KIS token expired/invalid (status=%d, msg=%s). Forcing token refresh and retrying request...",
                        resp.status_code,
                        resp.text[:120],
                    )
                    new_token = self.get_access_token(force_refresh=True)
                    if "headers" in kwargs and isinstance(kwargs["headers"], dict):
                        kwargs["headers"]["authorization"] = f"Bearer {new_token}"
                    return self._request(
                        method=method,
                        url=url,
                        max_retries=max_retries,
                        backoff_factor=backoff_factor,
                        auth_retry=False,
                        **kwargs,
                    )

                if resp.status_code >= 500:
                    resp.raise_for_status()
                if resp.status_code == 200 and attempt < max_retries:
                    try:
                        body_json = resp.json()
                        if isinstance(body_json, dict) and str(body_json.get("msg_cd") or "").strip() == "EGW00201":
                            sleep_sec = max(0.3, backoff_factor * (2 ** (attempt - 1)))
                            logger.warning(
                                "KIS API rate limit exceeded (EGW00201, attempt %d/%d). Sleeping %.2fs...",
                                attempt,
                                max_retries,
                                sleep_sec,
                            )
                            time.sleep(sleep_sec)
                            continue
                    except Exception:
                        pass
                return resp
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
                # Do not retry 4xx client errors (except token expiration handled above)
                if (
                    isinstance(e, requests.HTTPError)
                    and e.response is not None
                    and 400 <= e.response.status_code < 500
                ):
                    raise
                if attempt >= max_retries:
                    logger.error(
                        "KIS API request failed after %d attempts: %s %s - %s",
                        attempt,
                        method,
                        url,
                        e,
                    )
                    raise
                sleep_sec = backoff_factor * (2 ** (attempt - 1))
                logger.warning(
                    "KIS API request failed (attempt %d/%d): %s. Retrying in %.1fs...",
                    attempt,
                    max_retries,
                    e,
                    sleep_sec,
                )
                time.sleep(sleep_sec)

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
        resp = self._request("GET", url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()

        output = data.get("output", {})
        mxpr_str = output.get("stck_mxpr")
        if mxpr_str:
            try:
                mxpr_val = int(float(mxpr_str))
                if mxpr_val > 0:
                    self._upper_limits[ticker] = mxpr_val
            except (ValueError, TypeError):
                pass
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
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        resp = self._request("GET", url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()

        if data.get("rt_cd") != "0":
            msg = data.get("msg1", "Unknown broker error")
            logger.error("KIS balance inquiry failed: rt_cd=%s, msg=%s", data.get("rt_cd"), msg)
            raise RuntimeError(f"KIS balance inquiry error: {msg}")

        # Parse positions (output1)
        positions: list[Position] = []
        for item in data.get("output1", []):
            qty = int(item.get("hldg_qty") or item.get("hld_qty") or 0)
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
        dnca = float(tot_summary.get("dnca_tot_amt") or 0.0)
        prvs = float(tot_summary.get("prvs_rcdl_excc_amt") or 0.0)
        cash = prvs if prvs > 0 else dnca
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
        resp = self._request("POST", url, headers=headers, json=body)
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
            "INQR_DVSN_3": "00",
            "INQR_DVSN_1": "",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        resp = self._request("GET", url, headers=headers, params=params)
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
