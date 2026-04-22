from __future__ import annotations

from pydantic import BaseModel, Field

from backend.integrations.execution import VenueExecutionClient
from backend.tools._helpers import envelope, provider_error, provider_ok, run_tool, validate


class GetTradeHistoryInput(BaseModel):
    symbol: str | None = Field(default=None, min_length=3, max_length=32)
    since: int | None = Field(default=None, ge=0)
    limit: int = Field(default=50, ge=1, le=200)
    venue: str | None = Field(default=None, min_length=2, max_length=32)


def get_trade_history(payload: dict | None = None) -> dict:
    def _run() -> dict:
        args = validate(GetTradeHistoryInput, payload or {})
        client = VenueExecutionClient(args.venue or "bitmart")
        if not client.configured:
            missing = ", ".join(client.credential_env_names)
            return envelope(
                "get_trade_history",
                [provider_error(client.provider.name, f"Missing {missing}")],
                {"error": "provider_not_configured", "detail": f"{client.provider.name} credentials are not configured in the backend environment."},
                warnings=[f"{client.provider.name} credentials are not configured in the backend environment."],
                ok=False,
            )
        trades = client.get_trade_history(symbol=args.symbol, since=args.since, limit=args.limit)
        return envelope(
            "get_trade_history",
            [provider_ok(client.provider.name)],
            {
                "exchange": client.provider.name,
                "symbol": args.symbol,
                "count": len(trades),
                "trades": [trade.model_dump(mode="json") for trade in trades],
            },
        )

    return run_tool("get_trade_history", _run)