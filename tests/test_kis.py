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
