from __future__ import annotations

from backend.tools._helpers import envelope, run_tool
from backend.tools.get_smart_money_flows import get_smart_money_flows


def get_onchain_signal_summary(payload: dict) -> dict:
    def _run() -> dict:
        flow = get_smart_money_flows(payload)
        data = flow["data"]
        bias = "bullish" if (data.get("netflow_usd") or 0) > 0 else "bearish"
        return envelope("get_onchain_signal_summary", flow["meta"]["providers"], {"asset": data.get("asset"), "timeframe": data.get("timeframe"), "bias": bias, "summary": data.get("summary")})

    return run_tool("get_onchain_signal_summary", _run)

