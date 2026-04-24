from __future__ import annotations

from types import SimpleNamespace

from backend.event_bus.models import TradingEvent, TradingEventEnvelope
from backend.trading import dispatch_trade_proposal, normalize_trade_proposal
from backend.trading.models import ExecutionRequest, PolicyDecision, RiskRejectionReason
from backend.trading.policy_engine import evaluate_trade_proposal


def _proposal_payload() -> dict[str, object]:
    return {
        "source_agent": "strategy_agent",
        "symbol": "btcusdt",
        "side": "buy",
        "order_type": "market",
        "requested_size_usd": 1500.0,
        "rationale": "Structured breakout continuation with bounded risk.",
        "strategy_id": "breakout_v1",
        "strategy_template_id": "momentum_breakout",
        "timeframe": "15m",
    }


def test_proposal_normalization_uppercases_symbol_and_validates_shape() -> None:
    proposal = normalize_trade_proposal(_proposal_payload())

    assert proposal.symbol == "BTCUSDT"
    assert proposal.side == "buy"
    assert proposal.requested_size_usd == 1500.0


def test_policy_decision_is_typed_and_deterministic(monkeypatch) -> None:
    monkeypatch.setattr("backend.trading.policy_engine._portfolio_warnings", lambda: [])
    monkeypatch.setattr(
        "backend.trading.policy_engine.get_kill_switch_state",
        lambda: {"active": False, "reason": None},
    )
    monkeypatch.setattr("backend.trading.policy_engine.live_trading_blockers", lambda: [])
    monkeypatch.setattr("backend.trading.policy_engine.current_trading_mode", lambda: "paper")
    monkeypatch.setattr(
        "backend.trading.policy_engine.get_risk_approval",
        lambda payload: {
            "data": {
                "approved": True,
                "max_size_usd": payload["proposed_size_usd"],
                "confidence": 0.72,
                "reasons": ["volatility_ok"],
                "stop_guidance": "Use the defined invalidation.",
            }
        },
    )

    decision = evaluate_trade_proposal(_proposal_payload())

    assert isinstance(decision, PolicyDecision)
    assert decision.status == "approved"
    assert decision.approved is True
    assert decision.execution_mode == "paper"
    assert decision.rejection_reasons == []
    assert decision.approved_size_usd == 1500.0


def test_policy_decision_marks_live_blocker_rejections(monkeypatch) -> None:
    monkeypatch.setattr("backend.trading.policy_engine._portfolio_warnings", lambda: [])
    monkeypatch.setattr(
        "backend.trading.policy_engine.get_kill_switch_state",
        lambda: {"active": False, "reason": None},
    )
    monkeypatch.setattr(
        "backend.trading.policy_engine.live_trading_blockers",
        lambda: ["HERMES_ENABLE_LIVE_TRADING=true is required."],
    )
    monkeypatch.setattr("backend.trading.policy_engine.current_trading_mode", lambda: "live")
    monkeypatch.setattr(
        "backend.trading.policy_engine.get_risk_approval",
        lambda payload: {
            "data": {
                "approved": True,
                "max_size_usd": payload["proposed_size_usd"],
                "confidence": 0.8,
                "reasons": [],
                "stop_guidance": "Use the defined invalidation.",
            }
        },
    )

    decision = evaluate_trade_proposal(_proposal_payload())

    assert decision.status == "rejected"
    assert RiskRejectionReason.LIVE_TRADING_DISABLED in decision.rejection_reasons


def test_dispatch_records_manual_review_when_approval_required(monkeypatch) -> None:
    published: list[TradingEvent] = []
    decisions: list[tuple[str, str]] = []
    recorded_events: list[dict[str, object]] = []

    monkeypatch.setattr(
        "backend.trading.execution_service.publish_trading_event",
        lambda event: published.append(event),
    )
    monkeypatch.setattr(
        "backend.trading.execution_service.get_observability_service",
        lambda: SimpleNamespace(
            record_agent_decision=lambda **kwargs: decisions.append((kwargs["agent_name"], kwargs["status"])),
            record_execution_event=lambda **kwargs: recorded_events.append(kwargs),
        ),
    )
    monkeypatch.setattr(
        "backend.trading.execution_service.evaluate_trade_proposal",
        lambda proposal: PolicyDecision(
            proposal_id=proposal.proposal_id,
            status="manual_review",
            execution_mode="paper",
            approved=True,
            approved_size_usd=proposal.requested_size_usd,
            requires_operator_approval=True,
            policy_trace=["approval=required"],
            rejection_reasons=[RiskRejectionReason.APPROVAL_REQUIRED],
        ),
    )

    result = dispatch_trade_proposal(_proposal_payload())

    assert result.status == "manual_review"
    assert result.approval_required is True
    assert result.dispatch_payload.request_id
    assert result.dispatch_payload.idempotency_key
    assert len(published) == 1
    assert published[0].event_type == "execution_requested"
    request = ExecutionRequest.model_validate(published[0].payload)
    assert request.request_id == result.dispatch_payload.request_id
    assert decisions == [("risk_manager", "manual_review")]


def test_worker_routes_approval_required_requests_into_current_queue(monkeypatch) -> None:
    approval_calls: list[dict[str, object]] = []
    from backend.event_bus.workers import _handle_execution_requested

    monkeypatch.setenv("HERMES_REQUIRE_APPROVAL", "true")
    monkeypatch.setenv("HERMES_TRADING_MODE", "live")
    monkeypatch.setenv("HERMES_ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("HERMES_LIVE_TRADING_ACK", "I_ACKNOWLEDGE_LIVE_TRADING_RISK")
    monkeypatch.setattr("backend.event_bus.workers._check_and_enforce_drawdown", lambda: False)
    monkeypatch.setattr(
        "backend.approvals.create_approval_request",
        lambda **kwargs: approval_calls.append(kwargs) or "approval-123",
    )

    envelope = TradingEventEnvelope(
        event=TradingEvent(
            event_type="execution_requested",
            symbol="BTCUSDT",
            correlation_id="corr-1",
            workflow_id="wf-1",
            payload={
                "proposal_id": "proposal-1",
                "symbol": "BTCUSDT",
                "side": "buy",
                "order_type": "market",
                "size_usd": 1000.0,
                "amount": 1000.0,
            },
        )
    )

    handled = _handle_execution_requested(envelope)

    assert handled is True
    assert len(approval_calls) == 1
    assert approval_calls[0]["correlation_id"] == "corr-1"
    assert approval_calls[0]["payload"]["symbol"] == "BTCUSDT"


def test_worker_in_paper_mode_does_not_place_live_orders(monkeypatch) -> None:
    simulated: list[str] = []
    placed: list[str] = []
    from backend.event_bus.workers import _handle_execution_requested

    monkeypatch.setenv("HERMES_REQUIRE_APPROVAL", "false")
    monkeypatch.setattr("backend.event_bus.workers._check_and_enforce_drawdown", lambda: False)
    monkeypatch.setattr(
        "backend.event_bus.workers._record_simulated_execution",
        lambda event: simulated.append(event.event.event_id),
    )
    monkeypatch.setattr(
        "backend.event_bus.workers._place_live_order",
        lambda event: placed.append(event.event.event_id) or True,
    )

    envelope = TradingEventEnvelope(
        event=TradingEvent(
            event_id="evt-paper",
            event_type="execution_requested",
            symbol="BTCUSDT",
            correlation_id="corr-paper",
            workflow_id="wf-paper",
            payload={
                "proposal_id": "proposal-paper",
                "symbol": "BTCUSDT",
                "side": "buy",
                "order_type": "market",
                "size_usd": 1000.0,
                "amount": 1000.0,
            },
        )
    )

    handled = _handle_execution_requested(envelope)

    assert handled is True
    assert simulated == ["evt-paper"]
    assert placed == []


def test_worker_live_mode_with_kill_switch_never_places_order(monkeypatch) -> None:
    recorded: list[object] = []
    placed: list[str] = []
    from backend.event_bus.workers import _handle_execution_requested

    monkeypatch.setenv("HERMES_REQUIRE_APPROVAL", "false")
    monkeypatch.setenv("HERMES_TRADING_MODE", "live")
    monkeypatch.setenv("HERMES_ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("HERMES_LIVE_TRADING_ACK", "I_ACKNOWLEDGE_LIVE_TRADING_RISK")
    monkeypatch.setattr("backend.event_bus.workers._check_and_enforce_drawdown", lambda: False)
    monkeypatch.setattr(
        "backend.trading.safety.get_kill_switch_state",
        lambda: {"active": True, "reason": "operator stop"},
    )
    monkeypatch.setattr(
        "backend.event_bus.workers._record_execution_event",
        lambda event, outcome: recorded.append(outcome),
    )
    monkeypatch.setattr(
        "backend.event_bus.workers._place_live_order",
        lambda event: placed.append(event.event.event_id) or True,
    )

    envelope = TradingEventEnvelope(
        event=TradingEvent(
            event_id="evt-kill",
            event_type="execution_requested",
            symbol="BTCUSDT",
            correlation_id="corr-kill",
            workflow_id="wf-kill",
            payload={
                "proposal_id": "proposal-kill",
                "symbol": "BTCUSDT",
                "side": "buy",
                "order_type": "market",
                "size_usd": 1000.0,
                "amount": 1000.0,
            },
        )
    )

    handled = _handle_execution_requested(envelope)

    assert handled is True
    assert placed == []
    assert len(recorded) == 1
    assert recorded[0].result.reason == RiskRejectionReason.KILL_SWITCH_ACTIVE
    assert recorded[0].result.status == "blocked"


def test_worker_live_mode_blockers_prevent_live_execution(monkeypatch) -> None:
    recorded: list[object] = []
    placed: list[str] = []
    from backend.event_bus.workers import _handle_execution_requested

    monkeypatch.setenv("HERMES_REQUIRE_APPROVAL", "false")
    monkeypatch.setenv("HERMES_TRADING_MODE", "live")
    monkeypatch.delenv("HERMES_ENABLE_LIVE_TRADING", raising=False)
    monkeypatch.delenv("HERMES_LIVE_TRADING_ACK", raising=False)
    monkeypatch.setattr("backend.event_bus.workers._check_and_enforce_drawdown", lambda: False)
    monkeypatch.setattr(
        "backend.trading.safety.get_kill_switch_state",
        lambda: {"active": False, "reason": None},
    )
    monkeypatch.setattr(
        "backend.event_bus.workers._record_execution_event",
        lambda event, outcome: recorded.append(outcome),
    )
    monkeypatch.setattr(
        "backend.event_bus.workers._place_live_order",
        lambda event, request=None: placed.append(event.event.event_id) or True,
    )

    envelope = TradingEventEnvelope(
        event=TradingEvent(
            event_id="evt-blocked-live",
            event_type="execution_requested",
            symbol="BTCUSDT",
            correlation_id="corr-blocked-live",
            workflow_id="wf-blocked-live",
            payload={
                "proposal_id": "proposal-blocked-live",
                "symbol": "BTCUSDT",
                "side": "buy",
                "order_type": "market",
                "size_usd": 1000.0,
                "amount": 1000.0,
            },
        )
    )

    handled = _handle_execution_requested(envelope)

    assert handled is True
    assert placed == []
    assert len(recorded) == 1
    assert recorded[0].result.reason == RiskRejectionReason.LIVE_TRADING_DISABLED
    assert recorded[0].result.status == "blocked"


def test_worker_records_distinct_live_execution_outcome(monkeypatch) -> None:
    recorded: list[object] = []
    from backend.event_bus.workers import _place_live_order

    class FakeClient:
        configured = True

        def __init__(self, venue: str = "bitmart") -> None:
            self.venue = venue

        def get_execution_status(self, **kwargs):
            return SimpleNamespace(
                readiness_status="api_execution_ready",
                readiness={},
                support_matrix={},
            )

        def place_order(self, **kwargs):
            return SimpleNamespace(
                order_id="ord-live-1",
                symbol=kwargs["symbol"],
                model_dump=lambda mode="json": {
                    "order_id": "ord-live-1",
                    "symbol": kwargs["symbol"],
                    "side": kwargs["side"],
                    "order_type": kwargs["order_type"],
                    "amount": kwargs["amount"],
                    "status": "open",
                },
            )

    import backend.integrations.execution as execution_module

    monkeypatch.setattr(execution_module, "VenueExecutionClient", FakeClient)
    monkeypatch.setattr(
        "backend.event_bus.workers._record_execution_event",
        lambda event, outcome: recorded.append(outcome),
    )
    monkeypatch.setattr(
        "backend.event_bus.workers._resolve_order_amount",
        lambda payload, **kwargs: 0.25,
    )
    monkeypatch.setattr(
        "backend.event_bus.workers._clamp_order_amount",
        lambda amount, symbol: amount,
    )

    envelope = TradingEventEnvelope(
        event=TradingEvent(
            event_id="evt-live",
            event_type="execution_requested",
            symbol="BTCUSDT",
            correlation_id="corr-live",
            workflow_id="wf-live",
            payload={
                "proposal_id": "proposal-live",
                "request_id": "exec_req_live",
                "idempotency_key": "proposal-live:exec_req_live:BTCUSDT:buy:market",
                "symbol": "BTCUSDT",
                "side": "buy",
                "order_type": "market",
                "size_usd": 1000.0,
                "amount": 1000.0,
            },
        )
    )

    handled = _place_live_order(envelope)

    assert handled is True
    assert len(recorded) == 1
    assert recorded[0].result.status == "filled"
    assert recorded[0].result.execution_mode == "live"
    assert recorded[0].request.request_id == "exec_req_live"
