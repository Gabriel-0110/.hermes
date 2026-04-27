"""TwelveData client normalizing OHLCV and indicator responses."""

from __future__ import annotations

from datetime import datetime, timezone

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

    def get_ohlcv_range(
        self,
        symbol: str,
        interval: str,
        start_at: datetime,
        end_at: datetime,
        outputsize: int = 5000,
    ) -> list[OHLCVBar]:
        payload = self.request(
            "GET",
            "/time_series",
            params={
                "symbol": symbol,
                "interval": interval,
                "start_date": start_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "end_date": end_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "outputsize": outputsize,
                "format": "JSON",
                "order": "ASC",
            },
        )
        bars = [
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
        return sorted(bars, key=lambda bar: bar.timestamp)

    def get_indicator_snapshot(self, symbol: str, interval: str) -> IndicatorSnapshot:
        bars = self.get_ohlcv(symbol, interval, outputsize=30)
        closes = [bar.close for bar in reversed(bars)]
        sma_20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
        ema_20 = self._compute_ema(closes, 20) if len(closes) >= 20 else sma_20

        rsi_14 = self._fetch_indicator_value(symbol, interval, "rsi", 14)
        atr_14 = self._fetch_indicator_value(symbol, interval, "atr", 14)

        return IndicatorSnapshot(symbol=symbol, interval=interval, sma_20=sma_20, ema_20=ema_20, rsi_14=rsi_14, atr_14=atr_14)

    def _fetch_indicator_value(self, symbol: str, interval: str, indicator: str, period: int) -> float | None:
        try:
            payload = self.request(
                "GET",
                f"/{indicator}",
                params={"symbol": symbol, "interval": interval, "time_period": period, "outputsize": 1, "format": "JSON"},
            )
            values = payload.get("values", [])
            if values and isinstance(values, list):
                return float(values[0].get(indicator, 0))
        except Exception:
            return None
        return None

    @staticmethod
    def _compute_ema(closes: list[float], period: int) -> float | None:
        if len(closes) < period:
            return None
        multiplier = 2 / (period + 1)
        ema = sum(closes[:period]) / period
        for price in closes[period:]:
            ema = (price - ema) * multiplier + ema
        return ema

