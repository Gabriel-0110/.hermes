from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from backend.tools._helpers import envelope, run_tool, validate
from backend.tradingview.store import TradingViewStore


class TradingViewAlertContextInput(BaseModel):
    alert_id: str | None = None
    symbol: str | None = None
    limit: int = Field(default=10, ge=1, le=50)

    @model_validator(mode="after")
    def _require_lookup_target(self):
        if not self.alert_id and not self.symbol:
            raise ValueError("Provide either alert_id or symbol.")
        return self


def get_tradingview_alert_context(args: dict | None = None) -> dict:
    def _run() -> dict:
        params = validate(TradingViewAlertContextInput, args or {})
        context = TradingViewStore().get_alert_context(
            alert_id=params.alert_id,
            symbol=params.symbol.upper() if params.symbol else None,
            limit=params.limit,
        )
        return envelope("get_tradingview_alert_context", [], context)

    return run_tool("get_tradingview_alert_context", _run)
