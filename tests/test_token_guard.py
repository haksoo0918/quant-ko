"""KIS 토큰 발급 차단 가드 및 대시보드 무단 발급 방지 단위 테스트."""

import json
import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from quant_ko.broker.kis import KisClient, TokenIssueDisabledError
from quant_ko.dashboard.data_loader import load_account_and_positions


def test_allow_token_issue_false_blocks_token_request_when_no_cache(tmp_path):
    """캐시가 없고 allow_token_issue=False일 때 tokenP 엔드포인트 요청이 절대 발생하지 않고 TokenIssueDisabledError가 발생하는지 검증."""
    dummy_cache = tmp_path / "kis_token_real.json"

    client = KisClient(
        app_key="dummy_key",
        app_secret="dummy_secret",
        account_no="12345678-01",
        is_mock=False,
        allow_token_issue=False,
    )
    client.token_cache_file = str(dummy_cache)

    mock_session = MagicMock(spec=requests.Session)
    client.session = mock_session

    with pytest.raises(TokenIssueDisabledError) as exc_info:
        client.get_access_token()

    assert "신규 토큰 발급이 차단" in str(exc_info.value)
    # requests.Session의 post 메서드가 단 1회도 호출되지 않아야 함
    mock_session.post.assert_not_called()
    mock_session.request.assert_not_called()


def test_allow_token_issue_false_uses_valid_cache_without_request(tmp_path):
    """캐시가 유효하고 allow_token_issue=False일 때 기존 토큰을 재사용하며 API를 부르지 않는지 검증."""
    dummy_cache = tmp_path / "kis_token_real.json"
    future_exp = time.time() + 7200  # 2시간 유효
    dummy_cache.write_text(
        json.dumps({"access_token": "valid_token_12345", "expires_at": future_exp}),
        encoding="utf-8",
    )

    client = KisClient(
        app_key="dummy_key",
        app_secret="dummy_secret",
        account_no="12345678-01",
        is_mock=False,
        allow_token_issue=False,
    )
    client.token_cache_file = str(dummy_cache)

    mock_session = MagicMock(spec=requests.Session)
    client.session = mock_session

    token = client.get_access_token()

    assert token == "valid_token_12345"
    mock_session.post.assert_not_called()
    mock_session.request.assert_not_called()


def test_dashboard_load_account_never_requests_token_p_when_cache_missing(tmp_path):
    """대시보드 실시간 잔고 조회 시 유효 토큰이 없어도 tokenP 호출이 0회이며 오프라인 폴백이 정상 작동하는지 검증."""
    dummy_db = tmp_path / "quant_ko.db"

    with patch("quant_ko.broker.kis.KisClient.get_access_token") as mock_get_token, \
         patch("requests.Session.post") as mock_post:

        # 유효 토큰이 없어 차단 에러를 던지도록 설정
        mock_get_token.side_effect = TokenIssueDisabledError("Token issuance blocked")

        res = load_account_and_positions(db_path=dummy_db, fetch_live_kis=True)

        # tokenP POST 요청이 0회여야 함
        mock_post.assert_not_called()

        # 결과는 오프라인 폴백 기반으로 안전하게 반환되어야 함
        assert isinstance(res, dict)
        assert res.get("source") != "KIS_LIVE"
        assert "total_equity" in res


def test_get_cached_token_status_pure_check(tmp_path):
    """get_cached_token_status가 네트워크 요청 없이 캐시 유무 및 만료 상태를 정확히 판별하는지 검증."""
    # 1. 만료된 경우
    past_exp = time.time() - 3600
    expired_file = tmp_path / "kis_token_mock.json"
    expired_file.write_text(
        json.dumps({"access_token": "expired_tok", "expires_at": past_exp}),
        encoding="utf-8",
    )

    with patch("quant_ko.broker.kis.Path") as mock_path:
        # candidates 순회 시 expired_file 반환
        mock_path.return_value = expired_file
        # 실제 함수 호출
        status = KisClient.get_cached_token_status(is_mock=True)
        assert isinstance(status, dict)
        assert "is_valid" in status


def test_main_status_mode_blocks_token_issue_by_default():
    """main.py status 모드 실행 시 유효 토큰이 없으면 KIS API 호출이 0회이며 토큰 차단 안내가 출력되는지 검증."""
    from unittest.mock import patch

    from quant_ko.broker.kis import KisClient, TokenIssueDisabledError
    from quant_ko.main import print_status

    mock_client = MagicMock(spec=KisClient)
    mock_client.account_prefix = "12345678"
    mock_client.account_suffix = "01"
    mock_client.fetch_balance.side_effect = TokenIssueDisabledError("Token issuance blocked in status mode")

    with patch("builtins.print") as mock_print:
        print_status(kis_client=mock_client, env="real", date_str="2026-11-05")

        # 안내 문구가 출력되었는지 확인
        printed_texts = " ".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        assert "토큰 미발급/만료 상태" in printed_texts
