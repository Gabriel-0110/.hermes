"""get_funding_rates — Current perpetual funding rates via Binance public API (no key required)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.integrations.derivatives.bitmart_public_client import BitMartPublicClient
from backend.tools._helpers import envelope, provider_ok, run_tool, validate


class GetFundingRatesInput(BaseModel):
    symbols: list[str] | None = Field(default=None, description="Specific symbols e.g. ['BTCUSDT','ETHUSDT']. Omit for top 20 by absolute funding rate.")
    limit: int = Field(default=20, ge=1, le=100)


def get_funding_rates(payload: dict) -> dict:
    def _run() -> dict:
        args = validate(GetFundingRatesInput, payload)
        client = BitMartPublicClient()
        snapshot = client.get_funding_rates(args.symbols, limit=args.limit)
        return envelope(
            "get_funding_rates",
            [provider_ok(client.provider.name)],
            snapshot.model_dump(mode="json"),
        )

    return run_tool("get_funding_rates", _run)
