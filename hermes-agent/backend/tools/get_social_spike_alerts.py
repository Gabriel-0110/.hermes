from __future__ import annotations

from backend.tools._helpers import envelope, run_tool
from backend.tools.get_social_sentiment import get_social_sentiment


def get_social_spike_alerts(payload: dict) -> dict:
    def _run() -> dict:
        sentiment = get_social_sentiment(payload)
        data = sentiment["data"]
        spike = (data.get("engagement") or 0) > 5
        return envelope("get_social_spike_alerts", sentiment["meta"]["providers"], {"symbol": data.get("symbol"), "spike_detected": spike, "snapshot": data})

    return run_tool("get_social_spike_alerts", _run)

