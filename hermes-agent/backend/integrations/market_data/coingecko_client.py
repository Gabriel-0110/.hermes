"""Coingecko client normalizing price and market overview responses."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.integrations.base import BaseIntegrationClient
from backend.integrations.provider_profiles import PROVIDER_PROFILES
from backend.models import MarketOverview, OHLCVBar, PriceQuote


_SYMBOL_TO_COINGECKO_ID = {
    "ADA": "cardano",
    "AVAX": "avalanche-2",
    "BNB": "binancecoin",
    "BTC": "bitcoin",
    "DOGE": "dogecoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "XRP": "ripple",
}


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

    def get_ohlcv_range(
        self,
        symbol: str,
        start_at: datetime,
        end_at: datetime,
    ) -> list[OHLCVBar]:
        coin_id = _coingecko_id_for_symbol(symbol)
        payload = self.request(
            "GET",
            f"/coins/{coin_id}/market_chart/range",
            params={
                "vs_currency": "usd",
                "from": int(start_at.astimezone(timezone.utc).timestamp()),
                "to": int(end_at.astimezone(timezone.utc).timestamp()),
            },
        )
        prices = payload.get("prices") or []
        volumes = payload.get("total_volumes") or []
        volume_map = {
            int(point[0]): float(point[1])
            for point in volumes
            if isinstance(point, list | tuple) and len(point) >= 2
        }

        bars: list[OHLCVBar] = []
        previous_close: float | None = None
        for point in prices:
            if not isinstance(point, list | tuple) or len(point) < 2:
                continue
            ts_ms = int(point[0])
            close = float(point[1])
            open_price = previous_close if previous_close is not None else close
            bars.append(
                OHLCVBar(
                    timestamp=datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat(),
                    open=open_price,
                    high=max(open_price, close),
                    low=min(open_price, close),
                    close=close,
                    volume=volume_map.get(ts_ms),
                )
            )
            previous_close = close
        return bars


def _coingecko_id_for_symbol(symbol: str) -> str:
    clean = str(symbol or "").upper().replace("/USD", "").replace("/USDT", "")
    return _SYMBOL_TO_COINGECKO_ID.get(clean, clean.lower())

