"""Backend-only Slack notification delivery client."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from backend.integrations.base import IntegrationError, MissingCredentialError
from backend.integrations.provider_profiles import PROVIDER_PROFILES

logger = logging.getLogger(__name__)


class SlackNotificationClient:
    """Send normalized notifications to a Slack incoming webhook."""

    provider = PROVIDER_PROFILES["slack_notifications"]
    timeout_seconds = 8.0

    def __init__(self) -> None:
        self._webhook_url = os.getenv("SLACK_WEBHOOK_URL", "").strip()
        self._client = httpx.Client(
            timeout=httpx.Timeout(self.timeout_seconds),
            headers={"User-Agent": "hermes-agent/notifications"},
        )

    @property
    def configured(self) -> bool:
        return bool(self._webhook_url)

    def require_credentials(self) -> None:
        if self.configured:
            return
        raise MissingCredentialError(
            "Slack notifications are not configured. Set the following backend env vars: SLACK_WEBHOOK_URL"
        )

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, IntegrationError)),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def send_message(self, text: str, *, blocks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        self.require_credentials()
        body: dict[str, Any] = {"text": text}
        if blocks:
            body["blocks"] = blocks
        try:
            response = self._client.post(self._webhook_url, json=body)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning("Slack notification request failed with status %s", exc.response.status_code)
            raise IntegrationError(f"Slack notification failed with status {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            logger.warning("Slack notification transport error: %s", exc.__class__.__name__)
            raise

        if response.text.strip().lower() != "ok":
            logger.warning("Slack notification rejected by upstream webhook endpoint")
            raise IntegrationError("Slack notification was rejected by the upstream webhook endpoint.")
        return {"ok": True, "request_id": response.headers.get("x-slack-req-id")}
