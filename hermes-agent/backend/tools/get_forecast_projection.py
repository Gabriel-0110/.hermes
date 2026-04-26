"""Research-owned time-series projection tool.

Uses Amazon Chronos-2 (installed in .venv) for ML-grade probabilistic forecasts.
Falls back to a deterministic drift+volatility projection if Chronos is unavailable.
"""

from __future__ import annotations

import logging
from statistics import mean, pstdev

from pydantic import BaseModel, Field

from backend.tools._helpers import envelope, provider_ok, run_tool, validate
from backend.tools.get_ohlcv import get_ohlcv

logger = logging.getLogger(__name__)

# Chronos model to use — tiny is fast on CPU, mini is more accurate
CHRONOS_MODEL = "amazon/chronos-t5-tiny"


class GetForecastProjectionInput(BaseModel):
    symbol: str
    interval: str = "1d"
    history_limit: int = Field(default=90, ge=20, le=500)
    horizon: int = Field(default=12, ge=1, le=60)


def _chronos_projection(closes: list[float], horizon: int) -> list[dict[str, float | int]]:
    """Run Chronos-2 probabilistic forecast. Returns low/median/high scenarios."""
    import torch
    from chronos import BaseChronosPipeline

    pipeline = BaseChronosPipeline.from_pretrained(
        CHRONOS_MODEL,
        device_map="cpu",
        dtype=torch.float32,
    )
    context = torch.tensor(closes, dtype=torch.float32).unsqueeze(0)
    # num_samples=20 for fast CPU inference; increase for more accuracy
    forecast = pipeline.predict(context, prediction_length=horizon, num_samples=20)
    samples = forecast[0].numpy()  # shape: (num_samples, horizon)

    scenarios = []
    for step in range(horizon):
        step_samples = samples[:, step]
        scenarios.append({
            "step": step + 1,
            "low": round(float(max(float(import_np_quantile(step_samples, 0.1)), 0.0)), 8),
            "median": round(float(max(float(import_np_quantile(step_samples, 0.5)), 0.0)), 8),
            "high": round(float(max(float(import_np_quantile(step_samples, 0.9)), 0.0)), 8),
        })
    return scenarios


def import_np_quantile(arr, q):
    import numpy as np
    return np.quantile(arr, q)


def _deterministic_projection(closes: list[float], horizon: int) -> list[dict[str, float | int]]:
    """Fallback: simple drift + volatility projection."""
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
        scenarios.append({
            "step": step,
            "low": round(max(low, 0.0), 8),
            "median": round(max(median, 0.0), 8),
            "high": round(max(high, 0.0), 8),
        })
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

        # Try Chronos-2 first, fall back to deterministic
        chronos_available = False
        projections = None
        warnings = []

        try:
            projections = _chronos_projection(closes, args.horizon)
            chronos_available = True
            logger.info("get_forecast_projection: Chronos-2 inference succeeded for %s", args.symbol)
        except Exception as exc:
            logger.warning("get_forecast_projection: Chronos-2 failed (%s), using deterministic fallback", exc)
            warnings.append(f"Chronos-2 inference failed ({exc}); using deterministic fallback.")

        if not chronos_available or projections is None:
            projections = _deterministic_projection(closes, args.horizon)

        provider = "amazon_chronos_2" if chronos_available else "deterministic_research_projection"
        final_projection = projections[-1] if projections else {"low": None, "median": None, "high": None}

        return envelope(
            "get_forecast_projection",
            [provider_ok(provider)],
            {
                "symbol": args.symbol.upper(),
                "interval": args.interval,
                "history_points": len(closes),
                "last_close": closes[-1],
                "horizon": args.horizon,
                "forecast_model": provider,
                "forecast_is_trade_signal": False,
                "final_low": final_projection.get("low"),
                "final_median": final_projection.get("median"),
                "final_high": final_projection.get("high"),
                "scenarios": projections,
            },
            warnings=warnings,
        )

    return run_tool("get_forecast_projection", _run)
