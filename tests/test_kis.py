from unittest.mock import MagicMock, patch

import pytest

from quant_ko.broker.kis import Balance, KisClient, OrderResult, Position


@pytest.fixture
def kis_client(tmp_path):
    client = KisClient(
        app_key="test_app_key",
        app_secret="test_app_secret",
        account_no="12345678-01",
        is_mock=True,
    )
    client.token_cache_file = str(tmp_path / "test_token.json")
    return client


def test_kis_init_base_urls():
    mock_client = KisClient("key", "secret", "12345678-01", is_mock=True)
    assert mock_client.base_url == "https://openapivts.koreainvestment.com:29443"
    assert mock_client.account_prefix == "12345678"
    assert mock_client.account_suffix == "01"

    real_client = KisClient("key", "secret", "12345678-01", is_mock=False)
    assert real_client.base_url == "https://openapi.koreainvestment.com:9443"


def test_kis_token_issuance_and_caching(kis_client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "access_token": "mock_token_12345",
        "token_type": "Bearer",
        "expires_in": 3600,
    }

    with patch.object(kis_client.session, "post", return_value=mock_resp) as mock_post:
        token1 = kis_client.get_access_token()
        assert token1 == "mock_token_12345"
        mock_post.assert_called_once()

        # Call again; should return cached token without network request
        token2 = kis_client.get_access_token()
        assert token2 == "mock_token_12345"
        assert mock_post.call_count == 1


def test_kis_fetch_current_price(kis_client):
    kis_client._access_token = "cached_token"
    kis_client._token_expires_at = 9999999999.0

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "rt_cd": "0",
        "msg_cd": "MCA00000",
        "output": {
            "stck_prpr": "55000",
            "prdy_vrss": "500",
            "prdy_ctrt": "0.92",
        },
    }

    with patch.object(kis_client.session, "get", return_value=mock_resp) as mock_get:
        price = kis_client.fetch_current_price("005930")
        assert price == 55000.0
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        assert kwargs["headers"]["tr_id"] == "FHKST01010100"
        assert kwargs["params"]["FID_INPUT_ISCD"] == "005930"


def test_kis_fetch_balance(kis_client):
    kis_client._access_token = "cached_token"
    kis_client._token_expires_at = 9999999999.0

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "rt_cd": "0",
        "output1": [
            {
                "pdno": "005930",
                "prdt_name": "삼성전자",
                "hld_qty": "10",
                "prpr": "55000",
                "evlu_amt": "550000",
                "pchs_avg_pric": "50000",
            }
        ],
        "output2": [
            {
                "dnca_tot_amt": "1000000",  # 예수금
                "tot_evlu_amt": "1550000",  # 총평가금액
            }
        ],
    }

    with patch.object(kis_client.session, "get", return_value=mock_resp):
        balance: Balance = kis_client.fetch_balance()
        assert balance.cash == 1000000.0
        assert balance.total_eval_amount == 1550000.0
        assert len(balance.positions) == 1
        pos: Position = balance.positions[0]
        assert pos.ticker == "005930"
        assert pos.name == "삼성전자"
        assert pos.qty == 10
        assert pos.current_price == 55000.0
        assert pos.eval_amount == 550000.0


def test_kis_place_order_buy_and_sell(kis_client):
    kis_client._access_token = "cached_token"
    kis_client._token_expires_at = 9999999999.0

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "rt_cd": "0",
        "output": {
            "ODNO": "0000123456",
            "KRX_FWDG_ORD_ORGNO": "91252",
        },
        "msg1": "주문 전송 완료",
    }

    with patch.object(kis_client.session, "post", return_value=mock_resp) as mock_post:
        # BUY (Default Market Order "01")
        res_buy: OrderResult = kis_client.place_order(
            ticker="005930",
            side="BUY",
            qty=10,
            price=55000,
            order_type="01",
        )
        assert res_buy.success is True
        assert res_buy.order_no == "0000123456"
        assert res_buy.side == "BUY"
        assert res_buy.qty == 10
        assert res_buy.price == 55000.0

        # Check TR_ID and Body for Market Order
        args, kwargs = mock_post.call_args
        assert kwargs["headers"]["tr_id"] == "VTTC0802U"
        assert kwargs["json"]["ORD_DVSN"] == "01"
        assert kwargs["json"]["ORD_UNPR"] == "0"

        # SELL (Limit Order "00")
        res_sell: OrderResult = kis_client.place_order(
            ticker="005930",
            side="SELL",
            qty=5,
            price=56000,
            order_type="00",
        )
        assert res_sell.success is True
        assert res_sell.side == "SELL"
        args, kwargs = mock_post.call_args
        assert kwargs["headers"]["tr_id"] == "VTTC0801U"
        assert kwargs["json"]["ORD_DVSN"] == "00"
        assert kwargs["json"]["ORD_UNPR"] == "56000"


def test_kis_fetch_orders(kis_client):
    kis_client._access_token = "cached_token"
    kis_client._token_expires_at = 9999999999.0

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "rt_cd": "0",
        "output1": [
            {
                "odno": "0000123456",
                "pdno": "005930",
                "sll_buy_dvsn_cd": "02",  # BUY
                "ord_qty": "10",
                "ord_unpr": "55000",
                "tot_ccld_qty": "10",
                "prcs_stat_name": "체결",
            }
        ],
    }

    with patch.object(kis_client.session, "get", return_value=mock_resp):
        orders = kis_client.fetch_orders(date="2026-04-01")
        assert len(orders) == 1
        assert orders[0]["order_no"] == "0000123456"
        assert orders[0]["ticker"] == "005930"
        assert orders[0]["filled_qty"] == 10
        assert orders[0]["status"] == "FILLED"


def test_kis_request_retry_success(kis_client):
    """일시적 네트워크 에러 후 재시도로 성공하는 케이스 검증."""
    import requests

    success_resp = MagicMock()
    success_resp.status_code = 200

    # 1회차, 2회차 ConnectionError -> 3회차 성공
    with (
        patch.object(
            kis_client.session,
            "get",
            side_effect=[
                requests.ConnectionError("Connection reset"),
                requests.Timeout("Read timeout"),
                success_resp,
            ],
        ) as mock_get,
        patch("time.sleep") as mock_sleep,
    ):
        resp = kis_client._request("GET", "https://mock.url", max_retries=3, backoff_factor=0.01)
        assert resp == success_resp
        assert mock_get.call_count == 3
        assert mock_sleep.call_count == 2


def test_kis_request_retry_exhausted(kis_client):
    """최대 재시도(3회) 초과 시 예외를 전파하는지 검증."""
    import requests

    with (
        patch.object(
            kis_client.session,
            "post",
            side_effect=requests.ConnectionError("Network down"),
        ) as mock_post,
        patch("time.sleep"),
    ):
        import pytest

        with pytest.raises(requests.ConnectionError):
            kis_client._request("POST", "https://mock.url", max_retries=3, backoff_factor=0.01)
        assert mock_post.call_count == 3


def test_kis_request_no_retry_on_4xx(kis_client):
    """4xx 클라이언트 에러는 재시도 없이 즉시 raise하는지 검증."""
    import requests

    mock_resp = MagicMock()
    mock_resp.status_code = 400
    err = requests.HTTPError(response=mock_resp)

    with (
        patch.object(kis_client.session, "get", side_effect=err) as mock_get,
        patch("time.sleep") as mock_sleep,
    ):
        import pytest

        with pytest.raises(requests.HTTPError):
            kis_client._request("GET", "https://mock.url", max_retries=3)
        assert mock_get.call_count == 1
        mock_sleep.assert_not_called()


def test_kis_get_access_token_force_refresh(kis_client):
    """force_refresh=True 시 기존 캐시를 파기하고 새 토큰을 즉시 재발급하는지 검증."""
    kis_client._access_token = "old_token"
    kis_client._token_expires_at = 9999999999.0

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "access_token": "new_refreshed_token",
        "token_type": "Bearer",
        "expires_in": 86400,
    }

    with patch.object(kis_client.session, "post", return_value=mock_resp) as mock_post:
        token = kis_client.get_access_token(force_refresh=True)
        assert token == "new_refreshed_token"
        assert kis_client._access_token == "new_refreshed_token"
        mock_post.assert_called_once()


def test_kis_request_auto_recovers_on_401(kis_client):
    """API 호출 중 401 토큰 만료 발생 시 토큰을 재발급받고 1회 재시도하여 성공하는지 검증."""
    kis_client._access_token = "expired_token"
    kis_client._token_expires_at = 9999999999.0

    # 1st call: 401 Unauthorized
    resp_401 = MagicMock()
    resp_401.status_code = 401
    resp_401.text = '{"msg_cd": "EGW00123", "msg1": "기간이 만료된 token 입니다."}'
    resp_401.json.return_value = {"msg_cd": "EGW00123", "msg1": "기간이 만료된 token 입니다."}

    # Token refresh response
    resp_token = MagicMock()
    resp_token.status_code = 200
    resp_token.json.return_value = {
        "access_token": "new_valid_token",
        "expires_in": 86400,
    }

    # 2nd call: 200 OK
    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.json.return_value = {
        "rt_cd": "0",
        "msg_cd": "MCA00000",
        "output": {"stck_prpr": "70000"},
    }

    # session.get: 1st returns resp_401, 2nd returns resp_200
    # session.post: used by token refresh
    with (
        patch.object(kis_client.session, "get", side_effect=[resp_401, resp_200]) as mock_get,
        patch.object(kis_client.session, "post", return_value=resp_token) as mock_token_post,
    ):
        price = kis_client.fetch_current_price("005930")
        assert price == 70000.0
        assert mock_get.call_count == 2
        mock_token_post.assert_called_once()
        assert kis_client._access_token == "new_valid_token"


def test_kis_request_auto_recovers_on_egw00123_error_code(kis_client):
    """200 OK 또는 400 등 본문 JSON에 EGW00123 토큰 만료 에러 코드가 왔을 때 자동 갱신 및 재시도 검증."""
    kis_client._access_token = "stale_token"
    kis_client._token_expires_at = 9999999999.0

    resp_stale = MagicMock()
    resp_stale.status_code = 200
    resp_stale.json.return_value = {
        "rt_cd": "1",
        "msg_cd": "EGW00123",
        "msg1": "기간이 만료된 token 입니다.",
    }

    resp_token = MagicMock()
    resp_token.status_code = 200
    resp_token.json.return_value = {
        "access_token": "fresh_token",
        "expires_in": 86400,
    }

    resp_success = MagicMock()
    resp_success.status_code = 200
    resp_success.json.return_value = {
        "rt_cd": "0",
        "msg_cd": "MCA00000",
        "output": {"stck_prpr": "50000"},
    }

    with (
        patch.object(kis_client.session, "get", side_effect=[resp_stale, resp_success]) as mock_get,
        patch.object(kis_client.session, "post", return_value=resp_token) as mock_token_post,
    ):
        price = kis_client.fetch_current_price("000660")
        assert price == 50000.0
        assert mock_get.call_count == 2
        mock_token_post.assert_called_once()



def test_krx_tick_size_and_buy_limit_price():
    """KRX 호가 단위 및 +5% 상한 지정가 산출 헬퍼 함수 검증."""
    from quant_ko.broker.kis import (
        calc_buy_limit_price,
        get_krx_tick_size,
        round_to_krx_tick,
    )

    # 일반 주식 호가 단위
    assert get_krx_tick_size(1500) == 1
    assert get_krx_tick_size(3500) == 5
    assert get_krx_tick_size(12000) == 10
    assert get_krx_tick_size(35000) == 50
    assert get_krx_tick_size(120000) == 100
    assert get_krx_tick_size(350000) == 500
    assert get_krx_tick_size(600000) == 1000

    # ETF 호가 단위 (2,000원 이상 5원, 미만 1원)
    assert get_krx_tick_size(53000, is_etf=True) == 5
    assert get_krx_tick_size(1500, is_etf=True) == 1

    # 호가 반올림/내림/올림
    assert round_to_krx_tick(12345, is_etf=False, mode="floor") == 12340.0
    assert round_to_krx_tick(12345, is_etf=False, mode="ceil") == 12350.0
    assert round_to_krx_tick(53123, is_etf=True, mode="floor") == 53120.0

    # +5% 지정가 산출 (상한가 캡 포함)
    # 10,000 * 1.05 = 10,500 (틱 10원)
    assert calc_buy_limit_price(10000, buffer_pct=0.05) == 10500.0
    # 21,350 * 1.05 = 22,417.5 -> 20,000~50,000 구간이므로 50원 단위 내림 -> 22,400
    assert calc_buy_limit_price(21350, buffer_pct=0.05) == 22400.0
    # 상한가 캡이 더 낮을 경우 상한가로 제한
    assert calc_buy_limit_price(10000, buffer_pct=0.05, upper_limit=10300.0) == 10300.0


def test_kis_request_retries_on_egw00201_rate_limit(kis_client):
    """200 OK 응답이더라도 본문에 EGW00201(초당 거래건수 초과)이 오면 대기 후 재시도하는지 검증."""
    kis_client._access_token = "valid_token"
    kis_client._token_expires_at = 9999999999.0

    resp_rate_limit = MagicMock()
    resp_rate_limit.status_code = 200
    resp_rate_limit.json.return_value = {
        "rt_cd": "1",
        "msg_cd": "EGW00201",
        "msg1": "초당 거래건수를 초과하였습니다.",
    }

    resp_ok = MagicMock()
    resp_ok.status_code = 200
    resp_ok.json.return_value = {
        "rt_cd": "0",
        "msg_cd": "MCA00000",
        "output": {"stck_prpr": "12300"},
    }

    with (
        patch.object(
            kis_client.session, "get", side_effect=[resp_rate_limit, resp_ok]
        ) as mock_get,
        patch("time.sleep") as mock_sleep,
    ):
        price = kis_client.fetch_current_price("005930")
        assert price == 12300.0
        assert mock_get.call_count == 2
        mock_sleep.assert_called_once()


def test_kis_fetch_balance_uses_prvs_rcdl_excc_amt_when_present(kis_client):
    """실전 계좌처럼 dnca_tot_amt가 0이고 prvs_rcdl_excc_amt(D+2 가수도정산금액)가 양수일 때 이를 예수금으로 사용하는지 검증."""
    kis_client._access_token = "cached_token"
    kis_client._token_expires_at = 9999999999.0

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "rt_cd": "0",
        "output1": [],
        "output2": [
            {
                "dnca_tot_amt": "0",
                "prvs_rcdl_excc_amt": "1950000",
                "tot_evlu_amt": "1950000",
            }
        ],
    }

    with patch.object(kis_client.session, "get", return_value=mock_resp):
        balance = kis_client.fetch_balance()
        assert balance.cash == 1950000.0


def test_kis_fetch_current_price_caches_upper_limit(kis_client):
    """fetch_current_price 호출 시 응답의 stck_mxpr(상한가)를 캐싱하고 get_upper_limit으로 조회할 수 있는지 검증."""
    kis_client._access_token = "cached_token"
    kis_client._token_expires_at = 9999999999.0

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "rt_cd": "0",
        "msg_cd": "MCA00000",
        "output": {
            "stck_prpr": "10000",
            "stck_mxpr": "13000",
        },
    }

    with patch.object(kis_client.session, "get", return_value=mock_resp):
        price = kis_client.fetch_current_price("005930")
        assert price == 10000.0
        assert kis_client.get_upper_limit("005930") == 13000
        assert kis_client.get_upper_limit("999999") is None
