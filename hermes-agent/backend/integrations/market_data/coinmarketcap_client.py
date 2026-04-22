"""CoinMarketCap client normalizing quotes and listings data."""

from __future__ import annotations

from backend.integrations.base import BaseIntegrationClient
from backend.integrations.provider_profiles import PROVIDER_PROFILES
from backend.models import MarketOverview, PriceQuote


class CoinMarketCapClient(BaseIntegrationClient):
    provider = PROVIDER_PROFILES["coinmarketcap"]
    base_url = "https://pro-api.coinmarketcap.com"

    def auth_headers(self) -> dict[str, str]:
        return {"X-CMC_PRO_API_KEY": self._api_key}

    def get_prices(self, symbols: list[str], currency: str = "USD") -> list[PriceQuote]:
        payload = self.request(
            "GET",
            "/v1/cryptocurrency/quotes/latest",
            params={"symbol": ",".join(s.upper() for s in symbols), "convert": currency.upper()},
        )
        data = payload.get("data", {})
        quotes: list[PriceQuote] = []
        for symbol in symbols:
            row = data.get(symbol.upper(), {})
            quote = (row.get("quote") or {}).get(currency.upper(), {})
            quotes.append(
                PriceQuote(
                    symbol=symbol.upper(),
                    price=quote.get("price"),
                    currency=currency.upper(),
                    change_24h_pct=quote.get("percent_change_24h"),
                    market_cap=quote.get("market_cap"),
                    volume_24h=quote.get("volume_24h"),
                    rank=row.get("cmc_rank"),
                    as_of=quote.get("last_updated"),
                )
            )
        return quotes

    def get_market_overview(self) -> MarketOverview:
        payload = self.request("GET", "/v1/global-metrics/quotes/latest", params={"convert": "USD"})
        data = payload.get("data", {})
        quote = (data.get("quote") or {}).get("USD", {})
        return MarketOverview(
            regime="risk_on" if (quote.get("btc_dominance_24h_percentage_change") or 0) <= 0 else "risk_off",
            btc_dominance=quote.get("btc_dominance"),
            total_market_cap=quote.get("total_market_cap"),
            total_volume_24h=quote.get("total_volume_24h"),
            narrative_summary="Global crypto market snapshot normalized from CoinMarketCap.",
            as_of=quote.get("last_updated"),
        )

