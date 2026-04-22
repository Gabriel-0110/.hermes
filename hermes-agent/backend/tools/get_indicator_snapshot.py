from __future__ import annotations

from pydantic import BaseModel

from backend.integrations import TwelveDataClient
from backend.tools._helpers import envelope, provider_error, provider_ok, run_tool, validate


class GetIndicatorSnapshotInput(BaseModel):
    symbol: str
    interval: str = "1h"


def get_indicator_snapshot(payload: dict) -> dict:
    def _run() -> dict:
        args = validate(GetIndicatorSnapshotInput, payload)
        client = TwelveDataClient()
        if not client.configured:
            return envelope("get_indicator_snapshot", [provider_error(client.provider.name, f"Missing {client.provider.env_var}")], {}, ok=False)
        snapshot = client.get_indicator_snapshot(args.symbol, args.interval)
        return envelope("get_indicator_snapshot", [provider_ok(client.provider.name)], snapshot.model_dump(mode="json"))

    return run_tool("get_indicator_snapshot", _run)

