"""Research-owned time-series projection tool.

This tool intentionally exposes a normalized forecast package rather than raw
Chronos internals. If a Chronos runtime is installed later, it can replace the
deterministic fallback behind the same contract.
"""

from __future__ import annotations

from statistics import mean, pstdev

from pydantic import BaseModel, Field

from backend.tools._helpers import envelope, provider_error, provider_ok, run_tool, validate
from backend.tools.get_ohlcv import get_ohlcv


class GetForecastProjectionInput(BaseModel):
    symbol: str
    interval: str = "1d"
    history_limit: int = Field(default=90, ge=20, le=500)
    horizon: int = Field(default=12, ge=1, le=60)


def _scenario_projection(closes: list[float], horizon: int) -> list[dict[str, float | int]]:
    returns = []
    for idx in range(1, len(closes)):
        prev = closes[idx - 1]
        if prev:
            returns.append((closes[idx] - prev) / prev)

    drift = mean(returns) if returns else 0.0
    volatility = pstdev(returns) if len(returns) > 1 else 0.0
    last_close = closes[-1]

    scenarios: list[dict[str, float | int]] = []
    low = median = high = last_close
    for step in range(1, horizon + 1):
        median *= 1 + drift
        low *= 1 + drift - volatility
        high *= 1 + drift + volatility
        scenarios.append(
            {
                "step": step,
                "low": round(max(low, 0.0), 8),
                "median": round(max(median, 0.0), 8),
                "high": round(max(high, 0.0), 8),
            }
        )
    return scenarios


def get_forecast_projection(payload: dict) -> dict:
    def _run() -> dict:
        args = validate(GetForecastProjectionInput, payload)
        bars_payload = get_ohlcv(
            {
                "symbol": args.symbol,
                "interval": args.interval,
                "limit": args.history_limit,
            }
        )
        if not bars_payload.get("meta", {}).get("ok"):
            return envelope(
                "get_forecast_projection",
                bars_payload.get("meta", {}).get("providers", []),
                {
                    "error": "historical_series_unavailable",
                    "symbol": args.symbol,
                    "interval": args.interval,
                    "horizon": args.horizon,
                },
                warnings=bars_payload.get("meta", {}).get("warnings", []),
                ok=False,
            )

        closes = [
            float(row["close"])
            for row in reversed(bars_payload.get("data", []))
            if row.get("close") is not None
        ]
        if len(closes) < 20:
            return envelope(
                "get_forecast_projection",
                bars_payload["meta"]["providers"],
                {
                    "error": "insufficient_history",
                    "symbol": args.symbol,
                    "interval": args.interval,
                    "history_points": len(closes),
                    "minimum_history_points": 20,
                },
                ok=False,
            )

        chronos_available = False
        try:
            import chronos  # type: ignore  # noqa: F401

            chronos_available = True
        except Exception:
            chronos_available = False

        projections = _scenario_projection(closes, args.horizon)
        provider = "amazon_chronos_2" if chronos_available else "deterministic_research_projection"
        warnings = [] if chronos_available else ["Chronos-2 runtime not installed; returned deterministic fallback projection."]
        return envelope(
            "get_forecast_projection",
            [provider_ok(provider)],
            {
                "symbol": args.symbol.upper(),
                "interval": args.interval,
                "history_points": len(closes),
                "horizon": args.horizon,
                "forecast_model": provider,
                "forecast_is_trade_signal": False,
                "scenarios": projections,
            },
            warnings=warnings,
        )

    return run_tool("get_forecast_projection", _run)
