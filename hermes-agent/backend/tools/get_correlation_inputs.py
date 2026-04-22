from __future__ import annotations

from pydantic import BaseModel, Field

from backend.tools._helpers import envelope, run_tool, validate
from backend.tools.get_ohlcv import get_ohlcv


class GetCorrelationInputsInput(BaseModel):
    symbols: list[str] = Field(min_length=2, max_length=5)
    interval: str = "1d"
    limit: int = 30


def get_correlation_inputs(payload: dict) -> dict:
    def _run() -> dict:
        args = validate(GetCorrelationInputsInput, payload)
        series = {}
        providers = []
        for symbol in args.symbols:
            bars_payload = get_ohlcv({"symbol": symbol, "interval": args.interval, "limit": args.limit})
            providers.extend(bars_payload["meta"]["providers"])
            series[symbol] = [row["close"] for row in bars_payload["data"]]
        return envelope("get_correlation_inputs", providers, {"interval": args.interval, "series": series})

    return run_tool("get_correlation_inputs", _run)

