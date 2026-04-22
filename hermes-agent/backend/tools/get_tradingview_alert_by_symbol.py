from __future__ import annotations

from pydantic import BaseModel, Field

from backend.tools._helpers import envelope, run_tool, validate
from backend.tradingview.store import TradingViewStore


class TradingViewAlertBySymbolInput(BaseModel):
    symbol: str
    limit: int = Field(default=10, ge=1, le=100)


def get_tradingview_alert_by_symbol(args: dict | None = None) -> dict:
    def _run() -> dict:
        params = validate(TradingViewAlertBySymbolInput, args or {})
        rows = TradingViewStore().list_alerts(limit=params.limit, symbol=params.symbol.upper())
        return envelope(
            "get_tradingview_alert_by_symbol",
            [],
            {"symbol": params.symbol.upper(), "alerts": rows, "count": len(rows)},
        )

    return run_tool("get_tradingview_alert_by_symbol", _run)
