from __future__ import annotations

from pydantic import BaseModel, Field

from backend.tools._helpers import envelope, run_tool, validate
from backend.tradingview.store import TradingViewStore


class PendingSignalEventsInput(BaseModel):
    limit: int = Field(default=20, ge=1, le=200)
    symbol: str | None = None


def get_pending_signal_events(args: dict | None = None) -> dict:
    def _run() -> dict:
        params = validate(PendingSignalEventsInput, args or {})
        rows = TradingViewStore().list_internal_events(
            limit=params.limit,
            event_type="tradingview_signal_ready",
            delivery_status="pending",
            symbol=params.symbol.upper() if params.symbol else None,
        )
        return envelope("get_pending_signal_events", [], {"events": rows, "count": len(rows)})

    return run_tool("get_pending_signal_events", _run)
