from __future__ import annotations

from pydantic import BaseModel, Field

from backend.tools._helpers import envelope, run_tool, validate
from backend.tradingview.store import TradingViewStore


class RecentTradingViewAlertsInput(BaseModel):
    limit: int = Field(default=20, ge=1, le=200)
    processing_status: str | None = None


def get_recent_tradingview_alerts(args: dict | None = None) -> dict:
    def _run() -> dict:
        params = validate(RecentTradingViewAlertsInput, args or {})
        rows = TradingViewStore().list_alerts(
            limit=params.limit,
            processing_status=params.processing_status,
        )
        return envelope("get_recent_tradingview_alerts", [], {"alerts": rows, "count": len(rows)})

    return run_tool("get_recent_tradingview_alerts", _run)
