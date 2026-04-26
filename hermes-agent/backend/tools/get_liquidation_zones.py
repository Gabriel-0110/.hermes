"""get_liquidation_zones — Open interest + liquidation-pressure proxy via BitMart public futures API (no key required)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.integrations.derivatives.bitmart_public_client import BitMartPublicClient
from backend.tools._helpers import envelope, provider_ok, run_tool, validate


class GetLiquidationZonesInput(BaseModel):
    symbol: str = Field(default="BTCUSDT", description="Futures symbol e.g. 'BTCUSDT'")
    limit: int = Field(default=10, ge=1, le=200)


def get_liquidation_zones(payload: dict) -> dict:
    def _run() -> dict:
        args = validate(GetLiquidationZonesInput, payload)
        client = BitMartPublicClient()
        snapshot = client.get_liquidation_pressure(args.symbol, limit=args.limit)
        return envelope(
            "get_liquidation_zones",
            [provider_ok(client.provider.name)],
            snapshot.model_dump(mode="json"),
        )

    return run_tool("get_liquidation_zones", _run)
