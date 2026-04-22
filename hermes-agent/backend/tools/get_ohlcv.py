from __future__ import annotations

from pydantic import BaseModel, Field

from backend.integrations import TwelveDataClient
from backend.tools._helpers import envelope, provider_error, provider_ok, run_tool, validate


class GetOhlcvInput(BaseModel):
    symbol: str
    interval: str = "1h"
    limit: int = Field(default=50, ge=1, le=500)


def get_ohlcv(payload: dict) -> dict:
    def _run() -> dict:
        args = validate(GetOhlcvInput, payload)
        client = TwelveDataClient()
        if not client.configured:
            return envelope("get_ohlcv", [provider_error(client.provider.name, f"Missing {client.provider.env_var}")], [], ok=False)
        bars = client.get_ohlcv(args.symbol, args.interval, args.limit)
        return envelope("get_ohlcv", [provider_ok(client.provider.name)], [bar.model_dump(mode="json") for bar in bars])

    return run_tool("get_ohlcv", _run)

