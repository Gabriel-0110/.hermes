"""Base client and provider profile primitives for shared trading integrations."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class IntegrationError(RuntimeError):
    """Raised when an upstream provider cannot satisfy a normalized request."""


class MissingCredentialError(IntegrationError):
    """Raised when a provider client is used without its backend-only credential."""


@dataclass(frozen=True)
class ProviderProfile:
    name: str
    category: str
    purpose: str
    auth_method: str
    env_var: str
    internal_tools: list[str]
    benefiting_agents: list[str]
    fallback_overlap: list[str] = field(default_factory=list)


class BaseIntegrationClient:
    """Shared retrying HTTP client for backend-only third-party integrations."""

    provider: ProviderProfile
    base_url: str
    timeout_seconds: float = 10.0

    def __init__(self) -> None:
        self._api_key = os.getenv(self.provider.env_var, "").strip()
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout_seconds),
            headers={"User-Agent": "hermes-agent/trading-integrations"},
        )

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def require_api_key(self) -> None:
        if not self.configured:
            raise MissingCredentialError(
                f"{self.provider.name} is not configured. Set {self.provider.env_var} in the backend environment."
            )

    def auth_headers(self) -> dict[str, str]:
        return {}

    def auth_params(self) -> dict[str, str]:
        return {}

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, IntegrationError)),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        self.require_api_key()
        merged_headers = {**self.auth_headers(), **(headers or {})}
        merged_params = {**self.auth_params(), **(params or {})}
        response = self._client.request(method, path, params=merged_params, headers=merged_headers)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning("%s request failed with status %s", self.provider.name, exc.response.status_code)
            raise IntegrationError(f"{self.provider.name} request failed with status {exc.response.status_code}") from exc
        return response.json()

