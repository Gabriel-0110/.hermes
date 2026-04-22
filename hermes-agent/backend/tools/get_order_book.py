"""get_order_book — Level-2 order book depth, spread, and imbalance via Binance public API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.integrations.derivatives.bitmart_public_client import BitMartPublicClient
from backend.tools._helpers import envelope, provider_ok, run_tool, validate


class GetOrderBookInput(BaseModel):
    symbol: str
    limit: int = Field(default=20, ge=5, le=100)


def get_order_book(payload: dict) -> dict:
    def _run() -> dict:
        args = validate(GetOrderBookInput, payload)
        client = BitMartPublicClient()
        snapshot = client.get_order_book(args.symbol, limit=args.limit)
        return envelope(
            "get_order_book",
            [provider_ok(client.provider.name)],
            snapshot.model_dump(mode="json"),
        )

    return run_tool("get_order_book", _run)
