"""Workflow-safe adapters around existing Hermes internal tools."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field

from backend.tools.get_event_risk_summary import get_event_risk_summary
from backend.tools.get_macro_regime_summary import get_macro_regime_summary
from backend.tools.get_market_overview import get_market_overview
from backend.tools.get_onchain_signal_summary import get_onchain_signal_summary
from backend.tools.get_portfolio_state import get_portfolio_state
from backend.tools.get_risk_approval import get_risk_approval
from backend.tools.get_tradingview_alert_context import get_tradingview_alert_context
from backend.tools.get_volatility_metrics import get_volatility_metrics


class WorkflowToolResult(BaseModel):
    name: str
    ok: bool = True
    data: Any = None
    providers: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    detail: str | None = None


def normalize_tool_response(name: str, payload: dict[str, Any]) -> WorkflowToolResult:
    meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
    data = payload.get("data") if isinstance(payload, dict) else None
    if meta.get("ok", True):
        return WorkflowToolResult(
            name=name,
            ok=True,
            data=data,
            providers=meta.get("providers", []),
            warnings=meta.get("warnings", []),
        )
    return WorkflowToolResult(
        name=name,
        ok=False,
        data=data,
        providers=meta.get("providers", []),
        warnings=meta.get("warnings", []),
        error=(data or {}).get("error") if isinstance(data, dict) else "tool_error",
        detail=(data or {}).get("detail") if isinstance(data, dict) else None,
    )


class TradingWorkflowToolset(Protocol):
    def get_tradingview_alert_context(self, payload: dict[str, Any]) -> WorkflowToolResult: ...

    def get_market_overview(self, payload: dict[str, Any] | None = None) -> WorkflowToolResult: ...

    def get_macro_regime_summary(self, payload: dict[str, Any] | None = None) -> WorkflowToolResult: ...

    def get_event_risk_summary(self, payload: dict[str, Any] | None = None) -> WorkflowToolResult: ...

    def get_onchain_signal_summary(self, payload: dict[str, Any]) -> WorkflowToolResult: ...

    def get_volatility_metrics(self, payload: dict[str, Any]) -> WorkflowToolResult: ...

    def get_portfolio_state(self, payload: dict[str, Any] | None = None) -> WorkflowToolResult: ...

    def get_risk_approval(self, payload: dict[str, Any]) -> WorkflowToolResult: ...


class HermesWorkflowTools:
    """Adapter that reuses existing Hermes tool wrappers as workflow inputs."""

    def get_tradingview_alert_context(self, payload: dict[str, Any]) -> WorkflowToolResult:
        return normalize_tool_response("get_tradingview_alert_context", get_tradingview_alert_context(payload))

    def get_market_overview(self, payload: dict[str, Any] | None = None) -> WorkflowToolResult:
        return normalize_tool_response("get_market_overview", get_market_overview(payload))

    def get_macro_regime_summary(self, payload: dict[str, Any] | None = None) -> WorkflowToolResult:
        return normalize_tool_response("get_macro_regime_summary", get_macro_regime_summary(payload))

    def get_event_risk_summary(self, payload: dict[str, Any] | None = None) -> WorkflowToolResult:
        return normalize_tool_response("get_event_risk_summary", get_event_risk_summary(payload))

    def get_onchain_signal_summary(self, payload: dict[str, Any]) -> WorkflowToolResult:
        return normalize_tool_response("get_onchain_signal_summary", get_onchain_signal_summary(payload))

    def get_volatility_metrics(self, payload: dict[str, Any]) -> WorkflowToolResult:
        return normalize_tool_response("get_volatility_metrics", get_volatility_metrics(payload))

    def get_portfolio_state(self, payload: dict[str, Any] | None = None) -> WorkflowToolResult:
        return normalize_tool_response("get_portfolio_state", get_portfolio_state(payload))

    def get_risk_approval(self, payload: dict[str, Any]) -> WorkflowToolResult:
        return normalize_tool_response("get_risk_approval", get_risk_approval(payload))
