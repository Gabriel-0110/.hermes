from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from backend.integrations.execution import VenueExecutionClient, select_order_venue
from backend.tools._helpers import envelope, provider_error, provider_ok, run_tool, validate


class PlaceOrderInput(BaseModel):
    symbol: str = Field(min_length=3, max_length=32)
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit", "stop", "stop_limit"] = "market"
    amount: float = Field(gt=0)
    price: float | None = Field(default=None, gt=0)
    client_order_id: str | None = Field(default=None, min_length=1, max_length=64)
    time_in_force: Literal["GTC", "IOC", "FOK"] | None = None
    post_only: bool = False
    venue: str | None = Field(default=None, min_length=2, max_length=32)
    venues: list[str] | None = None

    @model_validator(mode="after")
    def _validate_price_requirements(self) -> "PlaceOrderInput":
        if self.order_type in {"limit", "stop", "stop_limit"} and self.price is None:
            raise ValueError("price is required for limit and stop-style orders")
        if self.order_type == "market" and self.post_only:
            raise ValueError("post_only is not supported for market orders")
        return self


def place_order(payload: dict | None = None) -> dict:
    def _run() -> dict:
        args = validate(PlaceOrderInput, payload or {})
        routing = select_order_venue(
            symbol=args.symbol,
            side=args.side,
            amount=args.amount,
            order_type=args.order_type,
            price=args.price,
            venue=args.venue,
            venues=args.venues,
        )
        client = VenueExecutionClient(routing["selected_venue"])
        if not client.configured:
            missing = ", ".join(client.credential_env_names)
            return envelope(
                "place_order",
                [provider_error(client.provider.name, f"Missing {missing}")],
                {"error": "provider_not_configured", "detail": f"{client.provider.name} credentials are not configured in the backend environment."},
                warnings=[f"{client.provider.name} credentials are not configured in the backend environment."],
                ok=False,
            )
        order = client.place_order(
            symbol=args.symbol,
            side=args.side,
            order_type=args.order_type,
            amount=args.amount,
            price=args.price,
            client_order_id=args.client_order_id,
            time_in_force=args.time_in_force,
            post_only=args.post_only,
        )
        data = order.model_dump(mode="json")
        data["routing"] = routing
        return envelope("place_order", [provider_ok(client.provider.name)], data, warnings=routing.get("warnings") or [])

    return run_tool("place_order", _run)