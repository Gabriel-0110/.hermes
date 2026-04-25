from __future__ import annotations

import json
from types import SimpleNamespace

from backend.db import HermesTimeSeriesRepository, ensure_time_series_schema, session_scope
from backend.db.session import get_engine
from backend.evaluation import ReplayStorage
from backend.event_bus.models import TradingEvent, TradingEventEnvelope
from backend.trading.models import ExecutionDispatchResult, ExecutionRequest, PolicyDecision
from backend.tradingview.service import TradingViewIngestionService


class _FakePublisher:
    def __init__(self) -> None:
        self.events: list[TradingEvent] = []

    def publish(self, event: TradingEvent):
        self.events.append(event)
        return TradingEventEnvelope(stream="trading", redis_id=f"{len(self.events)}-0", event=event)


def _fake_observability(*, execution_events: list[dict] | None = None, decisions: list[dict] | None = None):
    execution_events = execution_events if execution_events is not None else []
    decisions = decisions if decisions is not None else []
    return SimpleNamespace(
        record_execution_event=lambda **kwargs: execution_events.append(kwargs),
        record_agent_decision=lambda **kwargs: decisions.append(kwargs),
        record_system_error=lambda **kwargs: execution_events.append({"system_error": kwargs}),
    )


def _seed_signal_ready_alert(database_url: str) -> ReplayStorage:
    ensure_time_series_schema(get_engine(database_url=database_url))
    with session_scope(database_url=database_url) as session:
        repo = HermesTimeSeriesRepository(session)
        repo.insert_tradingview_alert(
            alert_id="tv_alert_pipeline_1",
            source="tradingview",
            symbol="BTCUSDT",
            timeframe="15m",
            alert_name="Momentum Breakout",
            signal="entry",
            direction="buy",
            strategy="momentum_v1",
            price=65000.0,
            payload={"raw_payload": {"symbol": "BTCUSDT"}, "correlation_id": "corr_tv_pipeline_1"},
            processing_status="signal_ready",
            processing_error=None,
        )
        repo.insert_internal_event(
            event_id="tv_evt_pipeline_1",
            event_type="tradingview_signal_ready",
            alert_event_id="tv_alert_pipeline_1",
            symbol="BTCUSDT",
            payload={
                "alert_id": "tv_alert_pipeline_1",
                "symbol": "BTCUSDT",
                "signal": "entry",
                "direction": "buy",
                "strategy": "momentum_v1",
                "timeframe": "15m",
                "alert_name": "Momentum Breakout",
                "price": 65000.0,
                "correlation_id": "corr_tv_pipeline_1",
            },
        )

    return ReplayStorage(database_url=database_url)


def test_ingestion_publishes_signal_ready_stream_event(tmp_path, monkeypatch) -> None:
    publisher = _FakePublisher()
    monkeypatch.setattr(
        "backend.tradingview.service.get_observability_service",
        lambda: _fake_observability(),
    )

    service = TradingViewIngestionService(
        db_path=tmp_path / "tradingview_state.db",
        event_publisher=publisher,
    )
    body = json.dumps(
        {
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "alert_name": "Momentum Breakout",
            "strategy": "momentum_v1",
            "signal": "entry",
            "direction": "buy",
            "price": 65000.0,
        }
    ).encode("utf-8")

    result = service.ingest(body=body, content_type="application/json")

    assert result.alert.processing_status == "signal_ready"
    assert [event.event_type for event in publisher.events] == [
        "tradingview_alert_received",
        "tradingview_signal_ready",
    ]
    signal_event = publisher.events[-1]
    assert signal_event.payload["alert_name"] == "Momentum Breakout"
    assert signal_event.payload["strategy"] == "momentum_v1"
    assert signal_event.payload["timeframe"] == "15m"
    assert signal_event.payload["price"] == 65000.0


def test_signal_ready_worker_dispatches_replay_case_proposal(tmp_path, monkeypatch) -> None:
    from backend.event_bus.workers import _handle_signal_ready
    from backend.strategies.registry import ScoredCandidate

    database_url = f"sqlite:///{tmp_path / 'signal_pipeline.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    storage = _seed_signal_ready_alert(database_url)
    replay_case = storage.load_tradingview_alert_case(alert_id="tv_alert_pipeline_1")
    storage.save_replay_case(replay_case)

    with session_scope(database_url=database_url) as session:
        repo = HermesTimeSeriesRepository(session)
        stored_cases = repo.list_replay_cases(limit=10)
    assert len(stored_cases) == 1
    assert stored_cases[0].source_alert_id == "tv_alert_pipeline_1"

    captured_proposals = []
    execution_events: list[dict] = []
    decisions: list[dict] = []

    monkeypatch.setattr(
        "backend.observability.service.get_observability_service",
        lambda: _fake_observability(execution_events=execution_events, decisions=decisions),
    )
    monkeypatch.setattr(
        "backend.event_bus.workers._score_tradingview_candidate",
        lambda **kwargs: ScoredCandidate(
            symbol="BTCUSDT",
            direction="long",
            confidence=0.67,
            rationale="Momentum aligned with breakout signal.",
            strategy_name="momentum",
            strategy_version="1.1.0",
        ),
    )
    monkeypatch.setattr(
        "backend.event_bus.workers._default_size_usd_for_strategy",
        lambda strategy_name: 75.0,
    )

    def _dispatch(proposal):
        captured_proposals.append(proposal)
        return ExecutionDispatchResult(
            proposal_id=proposal.proposal_id,
            status="queued",
            execution_mode="paper",
            correlation_id=proposal.proposal_id,
            workflow_id=f"proposal::{proposal.proposal_id}",
            approval_required=False,
            policy_decision=PolicyDecision(
                proposal_id=proposal.proposal_id,
                status="approved",
                execution_mode="paper",
                approved=True,
                approved_size_usd=proposal.requested_size_usd,
                requires_operator_approval=False,
                policy_trace=["approval=not_required"],
                rejection_reasons=[],
            ),
            dispatch_payload=ExecutionRequest(
                proposal_id=proposal.proposal_id,
                symbol=proposal.symbol,
                side=proposal.side,
                order_type=proposal.order_type,
                size_usd=proposal.requested_size_usd,
                amount=proposal.requested_size_usd,
                rationale=proposal.rationale,
                strategy_id=proposal.strategy_id,
                strategy_template_id=proposal.strategy_template_id,
                timeframe=proposal.timeframe,
            ),
            warnings=[],
        )

    monkeypatch.setattr("backend.trading.dispatch_trade_proposal", _dispatch)

    input_event = replay_case.input_event
    envelope = TradingEventEnvelope(
        event=TradingEvent(
            event_id=input_event.event_id,
            event_type=input_event.event_type,
            source=input_event.source,
            symbol=input_event.symbol,
            alert_id=input_event.alert_id,
            correlation_id=input_event.correlation_id,
            workflow_id=input_event.workflow_id,
            payload=input_event.payload,
            metadata=input_event.metadata,
        )
    )

    handled = _handle_signal_ready(envelope)

    assert handled is True
    assert len(captured_proposals) == 1
    proposal = captured_proposals[0]
    assert proposal.symbol == "BTCUSDT"
    assert proposal.side == "buy"
    assert proposal.requested_size_usd == 75.0
    assert proposal.timeframe == "15m"
    assert proposal.strategy_template_id == "momentum"
    assert proposal.metadata["source_alert_id"] == "tv_alert_pipeline_1"
    assert proposal.metadata["alert_strategy"] == "momentum_v1"
    assert any(event.get("event_type") == "tradingview_signal_dispatched" for event in execution_events)
    assert len(decisions) == 1