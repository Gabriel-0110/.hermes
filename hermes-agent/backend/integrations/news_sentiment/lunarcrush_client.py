"""LunarCrush client normalizing social sentiment outputs."""

from __future__ import annotations

from backend.integrations.base import BaseIntegrationClient
from backend.integrations.provider_profiles import PROVIDER_PROFILES
from backend.models import SentimentSnapshot


class LunarCrushClient(BaseIntegrationClient):
    provider = PROVIDER_PROFILES["lunarcrush"]
    base_url = "https://lunarcrush.com/api4/public"

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    def get_sentiment(self, symbol: str) -> SentimentSnapshot:
        payload = self.request("GET", "/coins/list/v1", params={"symbol": symbol.upper()})
        row = (payload.get("data") or [{}])[0]
        return SentimentSnapshot(
            symbol=symbol.upper(),
            score=row.get("galaxy_score"),
            engagement=row.get("social_dominance"),
            contributors=row.get("contributors_active"),
            trend=row.get("sentiment_text"),
        )

