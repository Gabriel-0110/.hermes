from __future__ import annotations

from pydantic import BaseModel, Field

from backend.integrations.execution import VenueExecutionClient
from backend.tools._helpers import envelope, provider_error, provider_ok, run_tool, validate


class GetExecutionStatusInput(BaseModel):
    order_id: str | None = Field(default=None, min_length=1, max_length=128)
    symbol: str | None = Field(default=None, min_length=3, max_length=32)
    venue: str | None = Field(default=None, min_length=2, max_length=32)


def get_execution_status(payload: dict | None = None) -> dict:
    def _run() -> dict:
        args = validate(GetExecutionStatusInput, payload or {})
        client = VenueExecutionClient(args.venue or "bitmart")
        status = client.get_execution_status(order_id=args.order_id, symbol=args.symbol)
        providers = [provider_ok(client.provider.name)] if status.configured else [provider_error(client.provider.name, status.detail or "Not configured")]
        return envelope("get_execution_status", providers, status.model_dump(mode="json"), ok=status.configured)

    return run_tool("get_execution_status", _run)

