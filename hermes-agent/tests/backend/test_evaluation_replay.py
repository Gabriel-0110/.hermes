from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("pydantic_graph")
pytest.importorskip("pydantic_ai")

from backend.db import HermesTimeSeriesRepository, ensure_time_series_schema, session_scope
from backend.db.session import get_engine
from backend.evaluation import (
    EvaluationRuleConfig,
    ReplayRunConfig,
    ReplayRunner,
    ReplayStorage,
)
from backend.observability import service as observability_service_module
from backend.workflows import TradingWorkflowDeps
from backend.workflows.tools import WorkflowToolResult


class StubWorkflowTools:
    def get_tradingview_alert_context(self, payload: dict) -> WorkflowToolResult:
        return WorkflowToolResult(name="get_tradingview_alert_context", data={"symbol": payload.get("symbol"), "alerts": []})

    def get_market_overview(self, payload: dict | None = None) -> WorkflowToolResult:
        return WorkflowToolResult(name="get_market_overview", data={"regime": "risk_on"})

    def get_macro_regime_summary(self, payload: dict | None = None) -> WorkflowToolResult:
        return WorkflowToolResult(name="get_macro_regime_summary", data={"risk_bias": "risk_on", "summary": "Supportive."})

    def get_event_risk_summary(self, payload: dict | None = None) -> WorkflowToolResult:
        return WorkflowToolResult(
            name="get_event_risk_summary",
            data={"severity": "low", "summary": "No major event risk.", "catalysts": ["ETF flows"]},
        )

    def get_onchain_signal_summary(self, payload: dict) -> WorkflowToolResult:
        return WorkflowToolResult(name="get_onchain_signal_summary", data={"summary": "Constructive onchain trend."})

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
                "confidence": 0.81,
                "reasons": ["volatility_ok", "event_risk_low"],
                "stop_guidance": "Use volatility-adjusted stop.",
            },
        )


def _reset_observability_singleton() -> None:
    observability_service_module._SERVICE = None


def test_replay_runner_persists_replay_results_and_scores(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'evaluation.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("TRADING_PORTFOLIO_ACCOUNT_ID", "paper")
    _reset_observability_singleton()
    ensure_time_series_schema(get_engine(database_url=database_url))

    with session_scope(database_url=database_url) as session:
        repo = HermesTimeSeriesRepository(session)
        repo.insert_tradingview_alert(
            alert_id="tv_alert_1",
            source="tradingview",
            symbol="BTCUSDT",
            timeframe="15m",
            alert_name="breakout",
            signal="entry",
            direction="buy",
            strategy="momentum_v1",
            price=65000.0,
            payload={"raw_payload": {"symbol": "BTCUSDT"}, "correlation_id": "corr_tv_1"},
            processing_status="signal_ready",
            processing_error=None,
        )
        repo.insert_internal_event(
            event_id="tv_evt_1",
            event_type="tradingview_signal_ready",
            alert_event_id="tv_alert_1",
            symbol="BTCUSDT",
            payload={
                "alert_id": "tv_alert_1",
                "symbol": "BTCUSDT",
                "signal": "entry",
                "direction": "buy",
                "strategy": "momentum_v1",
                "timeframe": "15m",
                "correlation_id": "corr_tv_1",
            },
        )
        repo.insert_portfolio_snapshot(
            account_id="paper",
            total_equity_usd=90000.0,
            cash_usd=50000.0,
            exposure_usd=10000.0,
            positions=[{"symbol": "BTCUSDT", "quantity": 0.1}],
        )

    storage = ReplayStorage(database_url=database_url)
    runner = ReplayRunner(storage=storage, base_tools=StubWorkflowTools())
    replay_case = storage.load_tradingview_alert_case(alert_id="tv_alert_1")
    replay_case.expected_outcome = {"forward_return": 0.03}

    artifacts = asyncio.run(
        runner.run_case(
            replay_case,
            rules=EvaluationRuleConfig(
                approved_vs_rejected_expected="execute",
                execution_expected=True,
                min_forward_return=0.0,
                max_latency_ms=5000,
            ),
            run_config=ReplayRunConfig(workflow_version="test_workflow_v1", prompt_version="prompt_a"),
            deps=TradingWorkflowDeps(tools=StubWorkflowTools(), use_pydantic_ai=False),
        )
    )

    assert artifacts.replay_run.status.value == "completed"
    assert artifacts.replay_result.decision == "execute"
    assert artifacts.replay_result.should_execute is True
    assert artifacts.replay_result.metadata["live_execution_blocked"] is True
    assert len(artifacts.evaluation_scores) >= 4

    persisted_results = storage.list_replay_results(artifacts.replay_run.id)
    persisted_scores = storage.list_evaluation_scores(artifacts.replay_run.id)
    assert len(persisted_results) == 1
    assert persisted_results[0].workflow_run_id == artifacts.replay_result.workflow_run_id
    assert any(score.rule_name == "forward_return" for score in persisted_scores)
