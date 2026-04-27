from __future__ import annotations

from math import sqrt

from pydantic import BaseModel

from backend.tools._helpers import envelope, run_tool, validate
from backend.tools.get_ohlcv import get_ohlcv


class GetVolatilityMetricsInput(BaseModel):
    symbol: str
    interval: str = "1d"
    limit: int = 30


def get_volatility_metrics(payload: dict) -> dict:
    def _run() -> dict:
        args = validate(GetVolatilityMetricsInput, payload)
        bars_payload = get_ohlcv(args.model_dump())
        raw_data = bars_payload.get("data", [])
        bars = raw_data if isinstance(raw_data, list) else []
        closes = [row["close"] for row in reversed(bars) if row.get("close") is not None]
        returns = []
        for idx in range(1, len(closes)):
            prev = closes[idx - 1]
            if prev:
                returns.append((closes[idx] - prev) / prev)
        realized_vol = sqrt(sum(r * r for r in returns) / len(returns)) if returns else None
        return envelope("get_volatility_metrics", bars_payload["meta"]["providers"], {"symbol": args.symbol, "interval": args.interval, "realized_volatility": realized_vol})

    return run_tool("get_volatility_metrics", _run)

