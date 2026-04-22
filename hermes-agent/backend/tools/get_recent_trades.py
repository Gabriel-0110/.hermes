"""get_recent_trades — fetch recent public trades (tape/time-and-sales) for a futures symbol."""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.integrations.derivatives.bitmart_public_client import BitMartPublicClient
from backend.tools._helpers import envelope, provider_ok, run_tool, validate


class GetRecentTradesInput(BaseModel):
    symbol: str = Field(..., description="Futures symbol (e.g. 'BTCUSDT').")
    limit: int = Field(default=50, ge=5, le=100, description="Number of recent trades to fetch (5–100).")


def get_recent_trades(payload: dict) -> dict:
    def _run() -> dict:
        args = validate(GetRecentTradesInput, payload)
        client = BitMartPublicClient()
        snapshot = client.get_recent_trades(args.symbol, limit=args.limit)
        return envelope(
            "get_recent_trades",
            [provider_ok(client.provider.name)],
            snapshot.model_dump(mode="json"),
        )

    return run_tool("get_recent_trades", _run)
