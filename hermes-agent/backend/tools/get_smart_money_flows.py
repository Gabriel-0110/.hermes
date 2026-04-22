from __future__ import annotations

from pydantic import BaseModel

from backend.integrations import NansenClient
from backend.tools._helpers import envelope, provider_error, provider_ok, run_tool, validate


class GetSmartMoneyFlowsInput(BaseModel):
    asset: str
    timeframe: str = "24h"


def get_smart_money_flows(payload: dict) -> dict:
    def _run() -> dict:
        args = validate(GetSmartMoneyFlowsInput, payload)
        client = NansenClient()
        if not client.configured:
            return envelope("get_smart_money_flows", [provider_error(client.provider.name, f"Missing {client.provider.env_var}")], {}, ok=False)
        flow = client.get_smart_money_flows(args.asset, args.timeframe)
        return envelope("get_smart_money_flows", [provider_ok(client.provider.name)], flow.model_dump(mode="json"))

    return run_tool("get_smart_money_flows", _run)

