"""Nansen client normalizing smart-money and wallet-label outputs."""

from __future__ import annotations

from backend.integrations.base import BaseIntegrationClient
from backend.integrations.provider_profiles import PROVIDER_PROFILES
from backend.models import SmartMoneyFlow


class NansenClient(BaseIntegrationClient):
    provider = PROVIDER_PROFILES["nansen"]
    base_url = "https://api.nansen.ai"

    def auth_headers(self) -> dict[str, str]:
        return {"api-key": self._api_key}

    def get_smart_money_flows(self, asset: str, timeframe: str = "24h") -> SmartMoneyFlow:
        payload = self.request("GET", "/smart-money/flow", params={"asset": asset.upper(), "timeframe": timeframe})
        data = payload.get("data", {})
        return SmartMoneyFlow(
            asset=asset.upper(),
            timeframe=timeframe,
            netflow_usd=data.get("netflow_usd"),
            smart_wallet_count=data.get("smart_wallet_count"),
            labels=data.get("labels") or [],
            summary=data.get("summary"),
        )

