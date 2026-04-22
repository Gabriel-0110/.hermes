from __future__ import annotations

from pydantic import BaseModel, Field

from backend.integrations.execution import VenueExecutionClient
from backend.tools._helpers import envelope, provider_error, provider_ok, run_tool, validate


class CancelOrderInput(BaseModel):
    order_id: str = Field(min_length=1, max_length=128)
    symbol: str | None = Field(default=None, min_length=3, max_length=32)
    venue: str | None = Field(default=None, min_length=2, max_length=32)


def cancel_order(payload: dict | None = None) -> dict:
    def _run() -> dict:
        args = validate(CancelOrderInput, payload or {})
        client = VenueExecutionClient(args.venue or "bitmart")
        if not client.configured:
            missing = ", ".join(client.credential_env_names)
            return envelope(
                "cancel_order",
                [provider_error(client.provider.name, f"Missing {missing}")],
                {"error": "provider_not_configured", "detail": f"{client.provider.name} credentials are not configured in the backend environment."},
                warnings=[f"{client.provider.name} credentials are not configured in the backend environment."],
                ok=False,
            )
        order = client.cancel_order(order_id=args.order_id, symbol=args.symbol)
        return envelope("cancel_order", [provider_ok(client.provider.name)], order.model_dump(mode="json"))

    return run_tool("cancel_order", _run)