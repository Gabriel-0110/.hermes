"""CryptoPanic client normalizing crypto-native news data."""

from __future__ import annotations

from backend.integrations.base import BaseIntegrationClient
from backend.integrations.provider_profiles import PROVIDER_PROFILES
from backend.models import NewsItem


class CryptoPanicClient(BaseIntegrationClient):
    provider = PROVIDER_PROFILES["cryptopanic"]
    base_url = "https://cryptopanic.com/api/free/v1"

    def auth_params(self) -> dict[str, str]:
        return {"auth_token": self._api_key}

    def get_news(self, currencies: list[str] | None = None, limit: int = 10) -> list[NewsItem]:
        payload = self.request(
            "GET",
            "/posts/",
            params={
                "currencies": ",".join(currencies or []),
                "public": "true",
                "kind": "news",
                "regions": "en",
                "filter": "important",
            },
        )
        items: list[NewsItem] = []
        for row in payload.get("results", [])[:limit]:
            votes = row.get("votes") or {}
            sentiment = "neutral"
            if (votes.get("positive") or 0) > (votes.get("negative") or 0):
                sentiment = "positive"
            elif (votes.get("negative") or 0) > (votes.get("positive") or 0):
                sentiment = "negative"
            items.append(
                NewsItem(
                    title=row.get("title", ""),
                    url=row.get("url"),
                    published_at=row.get("published_at"),
                    source=(row.get("source") or {}).get("title"),
                    sentiment=sentiment,
                    summary=row.get("slug"),
                    assets=[c.get("code") for c in row.get("currencies", []) if c.get("code")],
                )
            )
        return items

