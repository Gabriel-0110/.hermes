"""Coingecko client normalizing price and market overview responses."""

from __future__ import annotations

from backend.integrations.base import BaseIntegrationClient
from backend.integrations.provider_profiles import PROVIDER_PROFILES
from backend.models import MarketOverview, PriceQuote


class CoinGeckoClient(BaseIntegrationClient):
    provider = PROVIDER_PROFILES["coingecko"]
    base_url = "https://api.coingecko.com/api/v3"

    def auth_headers(self) -> dict[str, str]:
        return {"x-cg-pro-api-key": self._api_key}

    def get_prices(self, symbols: list[str], currency: str = "usd") -> list[PriceQuote]:
        payload = self.request(
            "GET",
            "/simple/price",
            params={
                "ids": ",".join(s.lower() for s in symbols),
                "vs_currencies": currency.lower(),
                "include_market_cap": "true",
                "include_24hr_vol": "true",
                "include_24hr_change": "true",
                "include_last_updated_at": "true",
            },
        )
        quotes: list[PriceQuote] = []
        for symbol in symbols:
            row = payload.get(symbol.lower(), {})
            quotes.append(
                PriceQuote(
                    symbol=symbol.upper(),
                    price=row.get(currency.lower()),
                    currency=currency.upper(),
                    market_cap=row.get(f"{currency.lower()}_market_cap"),
                    volume_24h=row.get(f"{currency.lower()}_24h_vol"),
                    change_24h_pct=row.get(f"{currency.lower()}_24h_change"),
                    as_of=str(row.get("last_updated_at")) if row.get("last_updated_at") is not None else None,
                )
            )
        return quotes

    def get_market_overview(self) -> MarketOverview:
        payload = self.request("GET", "/global")
        data = payload.get("data", {})
        return MarketOverview(
            regime="risk_on" if (data.get("market_cap_change_percentage_24h_usd") or 0) >= 0 else "risk_off",
            btc_dominance=(data.get("market_cap_percentage") or {}).get("btc"),
            total_market_cap=(data.get("total_market_cap") or {}).get("usd"),
            total_volume_24h=(data.get("total_volume") or {}).get("usd"),
            narrative_summary="Global crypto market snapshot normalized from CoinGecko.",
        )

