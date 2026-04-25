"""BitMart Wallet AI client for public smart-money and wallet analytics endpoints."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from backend.integrations.base import IntegrationError

logger = logging.getLogger(__name__)


class BitMartWalletAIClient:
    """Minimal client for the public BitMart Wallet AI API.

    The Wallet AI endpoints are public and do not require an API key, but they do
    require a stable custom ``User-Agent`` header to avoid Cloudflare bot
    challenges. The payloads returned are lightly normalized by higher-level jobs.
    """

    base_url = "https://api-cloud.bitmart.com"
    timeout_seconds = 15.0
    user_agent = "bitmart-skills/wallet/v2026.3.23"

    def __init__(self) -> None:
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout_seconds),
            headers={
                "Content-Type": "application/json",
                "User-Agent": self.user_agent,
            },
        )

    @property
    def configured(self) -> bool:
        return True

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, IntegrationError)),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _post(self, path: str, payload: dict[str, Any]) -> Any:
        response = self._client.post(path, json=payload)

        body_preview = response.text[:500].lower()
        if response.status_code in {403, 503} and "cloudflare" in body_preview:
            raise IntegrationError(
                "BitMart Wallet AI request was intercepted by Cloudflare. "
                "Retry later or check network reputation/VPN settings."
            )

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise IntegrationError(
                f"BitMart Wallet AI request failed with status {exc.response.status_code}"
            ) from exc

        try:
            payload_json = response.json()
        except json.JSONDecodeError as exc:
            raise IntegrationError("BitMart Wallet AI returned a non-JSON response") from exc

        if not isinstance(payload_json, dict):
            raise IntegrationError("BitMart Wallet AI returned an unexpected response shape")

        if not payload_json.get("success"):
            message = payload_json.get("message") or payload_json.get("code") or "unknown error"
            raise IntegrationError(f"BitMart Wallet AI request failed: {message}")

        return payload_json.get("data")

    def list_smart_money_wallets(self, *, limit: int = 50) -> list[dict[str, Any]]:
        data = self._post(
            "/web3/chain-web3-smart-money/v1/api/smart-money/list",
            {
                "current": 1,
                "size": max(1, min(limit, 100)),
                "orderBy": "profit7d",
                "order": "desc",
            },
        )
        records = data.get("records") if isinstance(data, dict) else []
        return [row for row in records if isinstance(row, dict)]

    def get_smart_money_info(self, wallet_address: str) -> dict[str, Any]:
        data = self._post(
            "/web3/chain-web3-smart-money/v1/api/smart-money/info",
            {"walletAddress": wallet_address},
        )
        return data if isinstance(data, dict) else {}