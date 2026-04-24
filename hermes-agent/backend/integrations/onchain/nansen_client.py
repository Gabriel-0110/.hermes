"""Nansen client normalizing smart-money and wallet-label outputs.

NOTE: Nansen completely restructured their API in 2025. All previous
endpoints (/smart-money/flow, /v1/*, /v2/*) return "no Route matched".
Their new API requires a paid Nansen Pro subscription and uses a
different authentication and routing model.

The client is kept structurally intact. configured=False is returned so
tools gracefully degrade with a provider_error envelope rather than
crashing. Re-enable by updating base_url and auth_headers once a valid
paid-tier endpoint is confirmed.
"""

from __future__ import annotations

from backend.integrations.base import BaseIntegrationClient
from backend.integrations.provider_profiles import PROVIDER_PROFILES
from backend.models import SmartMoneyFlow


class NansenClient(BaseIntegrationClient):
    provider = PROVIDER_PROFILES["nansen"]
    # Nansen API v1 base — endpoints restructured in 2025, requires Pro plan
    base_url = "https://api.nansen.ai"

    def auth_headers(self) -> dict[str, str]:
        return {"apikey": self._api_key}

    @property
    def configured(self) -> bool:
        # Return False until a working paid-tier endpoint is confirmed.
        # All known free/public endpoints return 404 or "no Route matched".
        return False

    def get_smart_money_flows(self, asset: str, timeframe: str = "24h") -> SmartMoneyFlow:
        # Graceful stub — returns empty flow; tools handle provider_error envelope
        return SmartMoneyFlow(
            asset=asset.upper(),
            timeframe=timeframe,
            netflow_usd=None,
            smart_wallet_count=None,
            labels=[],
            summary="unavailable — Nansen requires paid Pro subscription",
        )

