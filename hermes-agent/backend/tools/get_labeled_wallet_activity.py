from __future__ import annotations

from backend.tools._helpers import envelope, run_tool
from backend.tools.get_smart_money_flows import get_smart_money_flows


def get_labeled_wallet_activity(payload: dict) -> dict:
    def _run() -> dict:
        flow = get_smart_money_flows(payload)
        data = flow["data"]
        return envelope("get_labeled_wallet_activity", flow["meta"]["providers"], {"asset": data.get("asset"), "labels": data.get("labels", []), "summary": data.get("summary")})

    return run_tool("get_labeled_wallet_activity", _run)

