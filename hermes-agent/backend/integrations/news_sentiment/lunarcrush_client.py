"""LunarCrush client normalizing social sentiment outputs.

NOTE: LunarCrush discontinued their free API tier. All /coins/* endpoints
now require an active Individual subscription ($29/month+).
The client is kept structurally intact so it can be re-enabled when/if a
paid key is obtained. Until then, configured=False is returned and tools
gracefully degrade with a provider_error envelope.
"""

from __future__ import annotations

from backend.integrations.base import BaseIntegrationClient
from backend.integrations.provider_profiles import PROVIDER_PROFILES
from backend.models import SentimentSnapshot


class LunarCrushClient(BaseIntegrationClient):
    provider = PROVIDER_PROFILES["lunarcrush"]
    # LunarCrush v4 API base — requires paid Individual plan ($29/mo+)
    base_url = "https://lunarcrush.com/api4/public"

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    @property
    def configured(self) -> bool:
        # Always return False until a paid-tier key is confirmed working.
        # Free tier was removed by LunarCrush in 2025.
        return False

    def get_sentiment(self, symbol: str) -> SentimentSnapshot:
        # Graceful stub — returns empty snapshot; tools handle provider_error envelope
        return SentimentSnapshot(
            symbol=symbol.upper(),
            score=None,
            engagement=None,
            contributors=None,
            trend="unavailable — LunarCrush requires paid subscription",
        )

