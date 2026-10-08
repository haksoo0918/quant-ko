"""Discord Webhook notification service."""

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

DISCORD_MAX_CONTENT_LENGTH = 2000
DISCORD_MAX_EMBED_DESCRIPTION_LENGTH = 4096


class DiscordNotifier:
    """Sends notifications and embeds to a Discord channel via Webhook."""

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
        """Truncate text to fit within maximum allowed characters."""
        if len(text) <= max_length:
            return text
        suffix = "... (truncated)"
        return text[: max_length - len(suffix)] + suffix

    def send_text(self, content: str) -> bool:
        """Send plain text content to Discord webhook."""
        truncated_content = self._truncate_text(content, DISCORD_MAX_CONTENT_LENGTH)
        payload = {"content": truncated_content}
        return self._send_payload(payload)

    def send_embed(
        self,
        title: str,
        description: str = "",
        fields: list[dict[str, Any]] | None = None,
        color: int = 0x3498DB,  # Blue default
        footer_text: str | None = None,
    ) -> bool:
        """Send a rich embed message to Discord webhook."""
        truncated_desc = self._truncate_text(description, DISCORD_MAX_EMBED_DESCRIPTION_LENGTH)
        embed: dict[str, Any] = {
            "title": title[:256],
            "description": truncated_desc,
            "color": color,
        }
        if fields:
            embed["fields"] = fields[:25]  # Discord allows up to 25 fields
        if footer_text:
            embed["footer"] = {"text": footer_text[:2048]}

        payload = {"embeds": [embed]}
        return self._send_payload(payload)

    def _send_payload(self, payload: dict[str, Any]) -> bool:
        """Send payload or record in mock mode."""
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
