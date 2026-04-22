from __future__ import annotations

import asyncio

from backend.workflows import TradingInputEvent, TradingWorkflowDeps, run_trading_workflow
from backend.workflows.tools import WorkflowToolResult


class StubWorkflowTools:
    def get_tradingview_alert_context(self, payload: dict) -> WorkflowToolResult:
        return WorkflowToolResult(name="get_tradingview_alert_context", data={"symbol": payload.get("symbol"), "alerts": []})

    def get_market_overview(self, payload: dict | None = None) -> WorkflowToolResult:
        return WorkflowToolResult(name="get_market_overview", data={"regime": "risk_on", "narrative_summary": "Market supports selective upside."})

    def get_macro_regime_summary(self, payload: dict | None = None) -> WorkflowToolResult:
        return WorkflowToolResult(name="get_macro_regime_summary", data={"risk_bias": "risk_on", "summary": "Macro backdrop is supportive."})

    def get_event_risk_summary(self, payload: dict | None = None) -> WorkflowToolResult:
        return WorkflowToolResult(name="get_event_risk_summary", data={"severity": "low", "summary": "No immediate event risk.", "catalysts": ["ETF inflows"]})

    def get_onchain_signal_summary(self, payload: dict) -> WorkflowToolResult:
        return WorkflowToolResult(name="get_onchain_signal_summary", data={"summary": "Onchain netflows remain constructive."})

    def get_volatility_metrics(self, payload: dict) -> WorkflowToolResult:
        return WorkflowToolResult(name="get_volatility_metrics", data={"realized_volatility": 0.04})

    def get_portfolio_state(self, payload: dict | None = None) -> WorkflowToolResult:
        return WorkflowToolResult(name="get_portfolio_state", data={"account_id": "paper", "total_equity_usd": 100000.0})

    def get_risk_approval(self, payload: dict) -> WorkflowToolResult:
        return WorkflowToolResult(
            name="get_risk_approval",
            data={
                "approved": True,
                "max_size_usd": payload["proposed_size_usd"],
                "confidence": 0.82,
                "reasons": ["realized_volatility=0.04", "event_risk_severity=low"],
                "stop_guidance": "Use a volatility-adjusted stop.",
            },
        )


def test_trading_workflow_rejects_invalid_event() -> None:
    deps = TradingWorkflowDeps(tools=StubWorkflowTools())
    event = TradingInputEvent(symbol=None, signal=None, direction=None)

    result = asyncio.run(run_trading_workflow(event, deps=deps))

    assert result.output.decision == "reject"
    assert result.output.status == "rejected"


def test_trading_workflow_executes_valid_event() -> None:
    deps = TradingWorkflowDeps(tools=StubWorkflowTools())
    event = TradingInputEvent(symbol="BTCUSDT", signal="entry", direction="buy", timeframe="15m", strategy="momentum_v1")

    result = asyncio.run(run_trading_workflow(event, deps=deps))

    assert result.output.decision == "execute"
    assert result.output.should_execute is True
    assert result.output.execution_intent is not None
