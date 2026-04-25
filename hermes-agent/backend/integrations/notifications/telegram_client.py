"""Backend-only Telegram notification delivery client."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from backend.integrations.base import IntegrationError, MissingCredentialError
from backend.integrations.provider_profiles import PROVIDER_PROFILES

logger = logging.getLogger(__name__)


class TelegramNotificationClient:
    """Send normalized notifications to Telegram without exposing bot credentials."""

    provider = PROVIDER_PROFILES["telegram_notifications"]
    base_url = "https://api.telegram.org"
    timeout_seconds = 8.0

    def __init__(self) -> None:
        self._bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self._chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout_seconds),
            headers={"User-Agent": "hermes-agent/notifications"},
        )

    @property
    def configured(self) -> bool:
        return bool(self._bot_token and self._chat_id)

    def require_credentials(self) -> None:
        if self.configured:
            return
        missing = [
            name
            for name, value in (
                ("TELEGRAM_BOT_TOKEN", self._bot_token),
                ("TELEGRAM_CHAT_ID", self._chat_id),
            )
            if not value
        ]
        raise MissingCredentialError(
            "Telegram notifications are not configured. Set the following backend env vars: "
            + ", ".join(missing)
        )

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, IntegrationError)),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def send_message(
        self,
        text: str,
        *,
        reply_markup: dict[str, Any] | None = None,
        parse_mode: str | None = None,
        chat_id: str | None = None,
    ) -> dict[str, Any]:
        self.require_credentials()
        payload: dict[str, Any] = {
            "chat_id": chat_id or self._chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        if parse_mode:
            payload["parse_mode"] = parse_mode
        try:
            response = self._client.post(
                f"/bot{self._bot_token}/sendMessage",
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning("Telegram notification request failed with status %s", exc.response.status_code)
            raise IntegrationError(f"Telegram notification failed with status {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            logger.warning("Telegram notification transport error: %s", exc.__class__.__name__)
            raise

        payload = response.json()
        if not payload.get("ok"):
            logger.warning("Telegram notification rejected by upstream API")
            raise IntegrationError("Telegram notification was rejected by the upstream API.")
        return payload.get("result") or {}
