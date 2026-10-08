from unittest.mock import patch

import requests

from quant_ko.notify.discord import DiscordNotifier


def test_discord_mock_mode_records_messages():
    notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/mock", mock_mode=True)
    success = notifier.send_text("Hello, test!")
    assert success is True
    assert len(notifier.sent_messages) == 1
    assert notifier.sent_messages[0]["content"] == "Hello, test!"


def test_discord_truncates_long_content():
    notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/mock", mock_mode=True)
    long_msg = "A" * 2500
    notifier.send_text(long_msg)
    assert len(notifier.sent_messages) == 1
    sent_content = notifier.sent_messages[0]["content"]
    assert len(sent_content) <= 2000
    assert sent_content.endswith("... (truncated)")


def test_discord_send_embed():
    notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/mock", mock_mode=True)
    fields = [
        {"name": "종목", "value": "삼성전자 (005930)", "inline": True},
        {"name": "수량", "value": "10주", "inline": True},
    ]
    success = notifier.send_embed(
        title="리밸런싱 완료",
        description="2026-04-01 정기 리밸런싱 주문 체결 완료",
        fields=fields,
        color=0x00FF00,
    )
    assert success is True
    assert len(notifier.sent_messages) == 1
    payload = notifier.sent_messages[0]
    assert "embeds" in payload
    embed = payload["embeds"][0]
    assert embed["title"] == "리밸런싱 완료"
    assert len(embed["fields"]) == 2
    assert embed["color"] == 0x00FF00


def test_discord_real_network_success():
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 204
        notifier = DiscordNotifier(
            webhook_url="https://discord.com/api/webhooks/test", mock_mode=False
        )
        success = notifier.send_text("Live message")
        assert success is True
        mock_post.assert_called_once()


def test_discord_network_error_handled_gracefully():
    with patch("requests.post", side_effect=requests.RequestException("Connection error")):
        notifier = DiscordNotifier(
            webhook_url="https://discord.com/api/webhooks/test", mock_mode=False
        )
        success = notifier.send_text("Fail message")
        assert success is False
