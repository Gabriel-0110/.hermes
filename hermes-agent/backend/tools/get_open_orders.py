from __future__ import annotations

from pydantic import BaseModel, Field

from backend.integrations.execution import VenueExecutionClient
from backend.tools._helpers import envelope, provider_error, provider_ok, run_tool, validate


class GetOpenOrdersInput(BaseModel):
    symbol: str | None = Field(default=None, min_length=3, max_length=32)
    limit: int = Field(default=50, ge=1, le=200)
    venue: str | None = Field(default=None, min_length=2, max_length=32)


def get_open_orders(payload: dict | None = None) -> dict:
    def _run() -> dict:
        args = validate(GetOpenOrdersInput, payload or {})
        client = VenueExecutionClient(args.venue or "bitmart")
        if not client.configured:
            missing = ", ".join(client.credential_env_names)
            return envelope(
                "get_open_orders",
                [provider_error(client.provider.name, f"Missing {missing}")],
                {"error": "provider_not_configured", "detail": f"{client.provider.name} credentials are not configured in the backend environment."},
                warnings=[f"{client.provider.name} credentials are not configured in the backend environment."],
                ok=False,
            )
        orders = client.get_open_orders(symbol=args.symbol, limit=args.limit)
        return envelope(
            "get_open_orders",
            [provider_ok(client.provider.name)],
            {
                "exchange": client.provider.name,
                "symbol": args.symbol,
                "count": len(orders),
                "orders": [order.model_dump(mode="json") for order in orders],
            },
        )

    return run_tool("get_open_orders", _run)