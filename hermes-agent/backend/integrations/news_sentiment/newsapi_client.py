"""NewsAPI client normalizing general macro/news responses."""

from __future__ import annotations

from backend.integrations.base import BaseIntegrationClient
from backend.integrations.provider_profiles import PROVIDER_PROFILES
from backend.models import NewsItem


class NewsApiClient(BaseIntegrationClient):
    provider = PROVIDER_PROFILES["newsapi"]
    base_url = "https://newsapi.org/v2"

    def auth_headers(self) -> dict[str, str]:
        return {"X-Api-Key": self._api_key}

    def get_news(self, query: str, limit: int = 10) -> list[NewsItem]:
        payload = self.request("GET", "/everything", params={"q": query, "pageSize": limit, "language": "en", "sortBy": "publishedAt"})
        return [
            NewsItem(
                title=row.get("title", ""),
                url=row.get("url"),
                published_at=row.get("publishedAt"),
                source=(row.get("source") or {}).get("name"),
                summary=row.get("description"),
            )
            for row in payload.get("articles", [])[:limit]
        ]

