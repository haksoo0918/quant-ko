"""한국투자증권(KIS) Open API 클라이언트 모듈 (모의투자 및 실전 매매 지원)."""

import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from quant_ko.data.krx import normalize_date

load_dotenv()

logger = logging.getLogger(__name__)

MOCK_BASE_URL = "https://openapivts.koreainvestment.com:29443"
REAL_BASE_URL = "https://openapi.koreainvestment.com:9443"


class TokenIssueDisabledError(RuntimeError):
    """신규 KIS 토큰 발급이 비활성화(allow_token_issue=False)된 상태에서 유효한 캐시 토큰이 없을 때 발생하는 예외."""
    pass


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
    """계좌 보유 주식 포지션 정보 (종목코드, 종목명, 보유수량, 현재가, 평가금액, 매입평균가)."""

    ticker: str
    name: str
    qty: int
    current_price: float
    eval_amount: float
    purchase_price: float = 0.0


@dataclass
class Balance:
    """계좌 잔고 및 보유 포지션 내역 (예수금, 총평가금액, 보유종목 목록)."""

    cash: float
    total_eval_amount: float
    positions: list[Position] = field(default_factory=list)


@dataclass
class OrderResult:
    """주문 접수 결과 (주문번호, 종목코드, 매매구분, 주문수량, 주문단가, 성공여부, 응답메시지)."""

    order_no: str
    ticker: str
    side: str
    qty: int
    price: float
    success: bool
    message: str = ""


class KisClient:
    """한국투자증권 REST API 통신 클라이언트 (모의투자 및 실전투자 자동 전환 및 토큰 캐싱)."""

    # 프로세스 전체 공유 토큰 캐시 (동일 파이썬 프로세스 내 모든 인스턴스/스레드에서 토큰 재사용)
    _shared_token_cache: dict[str, tuple[str, float]] = {}

    def __init__(
        self,
        app_key: str | None = None,
        app_secret: str | None = None,
        account_no: str | None = None,
        is_mock: bool | None = None,
        session: requests.Session | None = None,
        allow_token_issue: bool = True,
    ) -> None:
        # 명시적으로 지정되지 않은 경우 KIS_MODE 환경변수로부터 모드 판별
        if is_mock is None:
            mode = os.getenv("KIS_MODE", "MOCK").strip().upper()
            self.is_mock = mode != "REAL"
        else:
            self.is_mock = is_mock

        # 환경변수 접두사 설정: KIS_MOCK_* 또는 KIS_REAL_*
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

        # 계좌번호 파싱 (예: "12345678-01", "1234567801", "12345678")
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
        self.allow_token_issue = allow_token_issue

    def get_upper_limit(self, ticker: str) -> int | None:
        """종목의 캐싱된 당일 상한가(stck_mxpr)를 반환합니다."""
        return self._upper_limits.get(ticker)

    @classmethod
    def get_cached_token_status(
        cls, is_mock: bool | None = None
    ) -> dict[str, Any]:
        """캐시된 KIS 토큰의 상태를 발급 API 호출 없이 순수 검사합니다."""
        if is_mock is None:
            mode = os.getenv("KIS_MODE", "MOCK").strip().upper()
            is_mock = mode != "REAL"
        mode_str = "mock" if is_mock else "real"
        now = time.time()

        home_dir = os.path.expanduser("~")
        candidates = [
            str(Path(__file__).resolve().parents[3] / "data" / f"kis_token_{mode_str}.json"),
            str(Path("data") / f"kis_token_{mode_str}.json"),
            os.path.join(tempfile.gettempdir(), f"kis_token_{mode_str}.json"),
            os.path.join(home_dir, ".kis", f"kis_token_{mode_str}.json"),
        ]

        for p_str in candidates:
            if os.path.exists(p_str):
                try:
                    with open(p_str, encoding="utf-8") as f:
                        data = json.load(f)
                    tok = data.get("access_token")
                    exp = float(data.get("expires_at", 0))
                    rem = exp - now
                    if tok and rem > 60:
                        return {
                            "is_valid": True,
                            "expires_at": exp,
                            "remaining_seconds": rem,
                            "remaining_hours": round(rem / 3600.0, 1),
                            "file_path": p_str,
                            "mode": mode_str,
                        }
                    elif tok:
                        return {
                            "is_valid": False,
                            "expires_at": exp,
                            "remaining_seconds": 0.0,
                            "remaining_hours": 0.0,
                            "file_path": p_str,
                            "mode": mode_str,
                            "reason": "expired",
                        }
                except Exception:
                    pass
        return {
            "is_valid": False,
            "expires_at": 0.0,
            "remaining_seconds": 0.0,
            "remaining_hours": 0.0,
            "file_path": None,
            "mode": mode_str,
            "reason": "not_found",
        }

    def get_access_token(
        self, force_refresh: bool = False, allow_issue: bool | None = None
    ) -> str:
        """OAuth 2.0 접근 토큰을 발급받거나 캐시된 토큰을 반환합니다 (메모리 및 파일 영구 캐싱).

        Args:
            force_refresh: 캐시 무시하고 신규 토큰 강제 발급 여부 (기본값: False).

        Returns:
            유효한 OAuth 접근 토큰 문자열.
        """
        effective_allow_issue = (
            self.allow_token_issue if allow_issue is None else allow_issue
        )
        now = time.time()
        mode_str = "mock" if self.is_mock else "real"
        cache_key = f"{mode_str}_{self.app_key}_{os.path.abspath(self.token_cache_file)}"
        default_file = f"data/kis_token_{mode_str}.json"
        is_default_file = os.path.abspath(self.token_cache_file) == os.path.abspath(default_file)
        temp_cache = (
            os.path.join(tempfile.gettempdir(), f"kis_token_{mode_str}.json")
            if is_default_file
            else None
        )

        if force_refresh:
            if not effective_allow_issue:
                raise TokenIssueDisabledError(
                    "KIS 신규 토큰 발급이 비활성화되어 있어 force_refresh를 수행할 수 없습니다."
                )
            self._access_token = None
            self._token_expires_at = 0.0
            KisClient._shared_token_cache.pop(cache_key, None)
            if os.path.exists(self.token_cache_file):
                try:
                    os.remove(self.token_cache_file)
                except Exception as exc:
                    logger.warning(
                        "Failed to remove KIS token cache file %s: %s", self.token_cache_file, exc
                    )
            if temp_cache and os.path.exists(temp_cache):
                try:
                    os.remove(temp_cache)
                except Exception:
                    pass

        # 1. 인스턴스 인메모리 캐시 유효성 확인
        if not force_refresh and self._access_token and now < self._token_expires_at - 60:
            remaining_h = (self._token_expires_at - now) / 3600.0
            logger.info(
                "Reusing cached KIS OAuth token from %s (valid for another %.1f hours)",
                "memory",
                remaining_h,
            )
            return self._access_token

        # 2. 파일 캐시 확인 (data/ 폴더 및 기본 경로 시 OS 임시 디렉터리 다중 경로 확인)
        candidate_files = [self.token_cache_file]
        home_dir = os.path.expanduser("~")
        user_home_cache = os.path.join(home_dir, ".kis", f"kis_token_{mode_str}.json")
        if user_home_cache not in candidate_files:
            candidate_files.append(user_home_cache)
        if temp_cache and temp_cache != self.token_cache_file:
            candidate_files.append(temp_cache)

        if not force_refresh:
            for c_file in candidate_files:
                if os.path.exists(c_file):
                    try:
                        with open(c_file, encoding="utf-8") as f:
                            cache_data = json.load(f)
                        cached_token = cache_data.get("access_token")
                        cached_expires = float(cache_data.get("expires_at", 0))
                        if cached_token and now < cached_expires - 60:
                            self._access_token = cached_token
                            self._token_expires_at = cached_expires
                            KisClient._shared_token_cache[cache_key] = (cached_token, cached_expires)
                            remaining_h = (cached_expires - now) / 3600.0
                            logger.info(
                                "Reusing cached KIS OAuth token from %s (valid for another %.1f hours)",
                                c_file,
                                remaining_h,
                            )
                            return self._access_token
                    except Exception as exc:
                        if c_file == self.token_cache_file:
                            logger.warning(
                                "Failed to read KIS token cache file %s: %s", self.token_cache_file, exc
                            )

        # 3. 프로세스 클래스 레벨 공유 메모리 캐시 확인 (대시보드 세션 재시작/새로고침 시 파일 부재 대비)
        if not force_refresh and cache_key in KisClient._shared_token_cache:
            tok, exp = KisClient._shared_token_cache[cache_key]
            if now < exp - 60:
                self._access_token = tok
                self._token_expires_at = exp
                remaining_h = (exp - now) / 3600.0
                logger.info(
                    "Reusing cached KIS OAuth token from %s (valid for another %.1f hours)",
                    "memory",
                    remaining_h,
                )
                return tok

        # 4. 신규 토큰 발급 허용 여부 물리적 가드 확인
        if not effective_allow_issue:
            logger.warning(
                "KIS OAuth token issue is blocked (allow_token_issue=False). "
                "No valid token found in cache. Rejecting token issuance to prevent unwanted notifications."
            )
            raise TokenIssueDisabledError(
                "유효한 KIS OAuth 캐시 토큰이 없으며, 신규 토큰 발급이 차단(allow_token_issue=False)되어 있습니다."
            )

        # 5. KIS API 서버에 신규 토큰 발급 요청
        logger.info(
            "Requesting new KIS OAuth token from API (force_refresh=%s, cache_file=%s)...",
            force_refresh,
            self.token_cache_file,
        )
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
        KisClient._shared_token_cache[cache_key] = (self._access_token, self._token_expires_at)

        # 안전한 권한으로 파일에 원자적(atomic) 기록
        targets = [self.token_cache_file]
        if temp_cache and temp_cache != self.token_cache_file:
            targets.append(temp_cache)

        for target_p in targets:
            tmp_file = f"{target_p}.tmp"
            try:
                target_dir = os.path.dirname(target_p)
                if target_dir:
                    os.makedirs(target_dir, exist_ok=True)
                with open(tmp_file, "w", encoding="utf-8") as f:
                    json.dump(
                        {"access_token": self._access_token, "expires_at": self._token_expires_at},
                        f,
                    )
                if os.name != "nt":
                    try:
                        os.chmod(tmp_file, 0o600)
                    except Exception:
                        pass
                os.replace(tmp_file, target_p)
            except Exception as exc:
                if target_p == self.token_cache_file:
                    logger.error(
                        "Failed to write KIS token cache file %s: %s", self.token_cache_file, exc
                    )
                else:
                    logger.warning("Failed to write KIS token backup file %s: %s", target_p, exc)
                if os.path.exists(tmp_file):
                    try:
                        os.remove(tmp_file)
                    except Exception:
                        pass

        return self._access_token
    def _is_token_expired(self, resp: requests.Response) -> bool:
        """API 응답이 토큰 만료 또는 유효하지 않은 토큰 에러인지 확인합니다."""
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
        """지수 백오프 재시도 및 토큰 자동 갱신을 적용하여 HTTP 요청을 실행합니다.

        네트워크 단절, 5xx 서버 오류, 일시적 초당 거래건수 초과(EGW00201) 시 재시도합니다.
        401 또는 토큰 만료 응답 시 토큰을 자동 갱신하고 1회 재요청합니다.

        Args:
            method: HTTP 메서드 ("GET", "POST" 등).
            url: 요청 대상 전체 URL.
            max_retries: 최대 재시도 횟수 (기본값: 3).
            backoff_factor: 재시도 대기 시간 배수 (초 단위).
            auth_retry: 토큰 만료 시 자동 재발급 및 재시도 허용 여부.
            **kwargs: requests 라이브러리에 전달할 추가 인자.

        Returns:
            HTTP 응답 객체(requests.Response).
        """
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

                # 토큰 만료 여부 확인 및 자동 갱신 복구
                if auth_retry and self._is_token_expired(resp):
                    if not self.allow_token_issue:
                        logger.warning(
                            "KIS token expired/invalid, but token issuance is disabled (allow_token_issue=False). Aborting request."
                        )
                        resp.raise_for_status()
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
                # 4xx 클라이언트 에러는 재시도하지 않음 (위에서 처리된 토큰 만료 제외)
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
        """KIS API 표준 요청 헤더 딕셔너리를 구성합니다."""
        token = self.get_access_token()
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
        }

    def fetch_current_price(self, ticker: str) -> float:
        """주식 종목의 현재가를 조회합니다.

        Args:
            ticker: 6자리 종목코드.

        Returns:
            현재가(체결가) float.
        """
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
        """계좌의 예수금 및 현재 보유 주식 잔고 내역을 조회합니다.

        Returns:
            계좌 잔고 객체(Balance).
        """
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

        # 보유 종목 목록 파싱 (output1)
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

        # 계좌 총 평가 및 예수금 요약 파싱 (output2)
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
        """현금 매수 또는 매도 주문을 발주합니다.

        Args:
            ticker: 6자리 종목코드.
            side: 매매 구분 ("BUY" 또는 "SELL").
            qty: 주문 수량.
            price: 주문 단가 (지정가인 경우 필수, 시장가인 경우 0).
            order_type: 주문 구분 ("01": 시장가 - 15:20 동시호가 100% 체결 보장, "00": 지정가).

        Returns:
            주문 결과 객체(OrderResult).
        """
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
        """당일 체결 및 미체결 주문 내역을 조회합니다.

        Args:
            date: 조회 대상 일자 (YYYY-MM-DD 또는 YYYYMMDD, 미지정 시 당일).

        Returns:
            주문 내역 딕셔너리 목록.
        """
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

            ord_dt = str(item.get("ord_dt") or "").strip() or target_date
            norm_ord_dt = normalize_date(ord_dt)
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
                    "rebalance_date": norm_ord_dt,
                    "date": norm_ord_dt,
                }
            )

        return orders
