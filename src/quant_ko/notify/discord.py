"""디스코드(Discord) 웹훅 기반 실시간 알림 서비스 모듈."""

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

DISCORD_MAX_CONTENT_LENGTH = 2000
DISCORD_MAX_EMBED_DESCRIPTION_LENGTH = 4096


class DiscordNotifier:
    """웹훅(Webhook)을 통해 디스코드 채널로 텍스트 메시지 및 임베드(Embed) 알림을 전송하는 클래스."""

    def __init__(
        self,
        webhook_url: str | None = None,
        mock_mode: bool = False,
        timeout: float = 5.0,
    ) -> None:
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "")
        self.mock_mode = mock_mode or not bool(self.webhook_url)
        self.timeout = timeout
        self.sent_messages: list[dict[str, Any]] = []

    def _truncate_text(self, text: str, max_length: int = DISCORD_MAX_CONTENT_LENGTH) -> str:
        """메시지가 디스코드 본문 최대 허용 길이를 초과하지 않도록 말줄임표(...) 처리하여 자릅니다."""
        if len(text) <= max_length:
            return text
        suffix = "... (truncated)"
        return text[: max_length - len(suffix)] + suffix

    def send_text(self, content: str) -> bool:
        """디스코드 웹훅으로 일반 텍스트 메시지를 전송합니다."""
        truncated_content = self._truncate_text(content, DISCORD_MAX_CONTENT_LENGTH)
        payload = {"content": truncated_content}
        return self._send_payload(payload)

    def send_embed(
        self,
        title: str,
        description: str = "",
        fields: list[dict[str, Any]] | None = None,
        color: int = 0x3498DB,  # 기본 색상: 파란색(0x3498DB)
        footer_text: str | None = None,
    ) -> bool:
        """디스코드 웹훅으로 구조화된 서식의 리치 임베드(Embed) 메시지를 전송합니다."""
        truncated_desc = self._truncate_text(description, DISCORD_MAX_EMBED_DESCRIPTION_LENGTH)
        embed: dict[str, Any] = {
            "title": title[:256],
            "description": truncated_desc,
            "color": color,
        }
        if fields:
            embed["fields"] = fields[:25]  # 디스코드 임베드 필드 최대 25개 제한
        if footer_text:
            embed["footer"] = {"text": footer_text[:2048]}

        payload = {"embeds": [embed]}
        return self._send_payload(payload)

    def _send_payload(self, payload: dict[str, Any]) -> bool:
        """HTTP POST로 페이로드를 전송하거나 모의(Mock) 모드에서 전송 내역을 기록합니다."""
        self.sent_messages.append(payload)

        if self.mock_mode or not self.webhook_url:
            return True

        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error("Failed to send Discord webhook message: %s", e)
            return False
