"""TwelveData client normalizing OHLCV and indicator responses."""

from __future__ import annotations

from backend.integrations.base import BaseIntegrationClient
from backend.integrations.provider_profiles import PROVIDER_PROFILES
from backend.models import IndicatorSnapshot, OHLCVBar


class TwelveDataClient(BaseIntegrationClient):
    provider = PROVIDER_PROFILES["twelvedata"]
    base_url = "https://api.twelvedata.com"

    def auth_params(self) -> dict[str, str]:
        return {"apikey": self._api_key}

    def get_ohlcv(self, symbol: str, interval: str, outputsize: int = 50) -> list[OHLCVBar]:
        payload = self.request(
            "GET",
            "/time_series",
            params={"symbol": symbol, "interval": interval, "outputsize": outputsize, "format": "JSON"},
        )
        return [
            OHLCVBar(
                timestamp=row["datetime"],
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]) if row.get("volume") is not None else None,
            )
            for row in payload.get("values", [])
        ]

    def get_indicator_snapshot(self, symbol: str, interval: str) -> IndicatorSnapshot:
        bars = self.get_ohlcv(symbol, interval, outputsize=30)
        closes = [bar.close for bar in reversed(bars)]
        sma_20 = sum(closes[-20:]) / min(len(closes[-20:]), 20) if closes else None
        ema_20 = sma_20
        return IndicatorSnapshot(symbol=symbol, interval=interval, sma_20=sma_20, ema_20=ema_20)

