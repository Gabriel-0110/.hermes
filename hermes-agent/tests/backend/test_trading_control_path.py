from __future__ import annotations

import json
from types import SimpleNamespace

from backend.event_bus.models import TradingEvent, TradingEventEnvelope
from backend.trading import dispatch_trade_proposal, normalize_trade_proposal, paired_proposal_from_legs
from backend.trading.models import ExecutionRequest, PolicyDecision, RiskRejectionReason, TradeProposalLeg
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


def test_policy_decision_resizes_to_symbol_notional_cap(monkeypatch) -> None:
    monkeypatch.setattr("backend.trading.policy_engine.current_trading_mode", lambda: "paper")
    monkeypatch.setattr("backend.trading.policy_engine.live_trading_blockers", lambda: [])
    monkeypatch.setattr(
        "backend.trading.policy_engine.get_kill_switch_state",
        lambda: {"active": False, "reason": None},
    )
    monkeypatch.setattr(
        "backend.trading.policy_engine.get_portfolio_state",
        lambda payload=None: {
            "meta": {"ok": True, "warnings": []},
            "data": {
                "updated_at": "2026-04-25T00:00:00+00:00",
                "positions": [{"symbol": "BTC", "notional_usd": 1800.0}],
            },
        },
    )
    monkeypatch.setattr(
        "backend.trading.policy_engine.get_risk_state",
        lambda payload=None: {
            "meta": {"ok": True, "warnings": []},
            "data": {
                "max_position_usd": 5000.0,
                "max_leverage": 10.0,
                "symbol_limits": {"BTCUSDT": {"max_notional_usd": 2000.0, "max_leverage": 5.0}},
            },
        },
    )
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

    proposal = {**_proposal_payload(), "requested_size_usd": 500.0, "leverage": 3.0}
    decision = evaluate_trade_proposal(proposal)

    assert decision.status == "approved"
    assert decision.approved_size_usd == 200.0
    assert RiskRejectionReason.POSITION_LIMIT_EXCEEDED not in decision.rejection_reasons
    assert any("configured position cap" in warning for warning in decision.warnings)


def test_policy_decision_blocks_when_requested_leverage_exceeds_cap(monkeypatch) -> None:
    monkeypatch.setattr("backend.trading.policy_engine.current_trading_mode", lambda: "paper")
    monkeypatch.setattr("backend.trading.policy_engine.live_trading_blockers", lambda: [])
    monkeypatch.setattr(
        "backend.trading.policy_engine.get_kill_switch_state",
        lambda: {"active": False, "reason": None},
    )
    monkeypatch.setattr(
        "backend.trading.policy_engine.get_portfolio_state",
        lambda payload=None: {
            "meta": {"ok": True, "warnings": []},
            "data": {
                "updated_at": "2026-04-25T00:00:00+00:00",
                "positions": [{"symbol": "BTCUSDT", "notional_usd": 500.0}],
            },
        },
    )
    monkeypatch.setattr(
        "backend.trading.policy_engine.get_risk_state",
        lambda payload=None: {
            "meta": {"ok": True, "warnings": []},
            "data": {
                "max_position_usd": 5000.0,
                "symbol_limits": {"BTCUSDT": {"max_notional_usd": 2500.0, "max_leverage": 3.0}},
            },
        },
    )
    monkeypatch.setattr(
        "backend.trading.policy_engine.get_risk_approval",
        lambda payload: {
            "data": {
                "approved": True,
                "max_size_usd": payload["proposed_size_usd"],
                "confidence": 0.9,
                "reasons": [],
                "stop_guidance": "Use the defined invalidation.",
            }
        },
    )

    proposal = {**_proposal_payload(), "requested_size_usd": 300.0, "leverage": 8.0}
    decision = evaluate_trade_proposal(proposal)

    assert decision.status == "rejected"
    assert decision.approved is False
    assert RiskRejectionReason.LEVERAGE_LIMIT_EXCEEDED in decision.rejection_reasons


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


def test_dispatch_preserves_paired_execution_legs(monkeypatch) -> None:
    published: list[TradingEvent] = []

    monkeypatch.setattr(
        "backend.trading.execution_service.publish_trading_event",
        lambda event: published.append(event),
    )
    monkeypatch.setattr(
        "backend.trading.execution_service.get_observability_service",
        lambda: SimpleNamespace(
            record_agent_decision=lambda **kwargs: None,
            record_execution_event=lambda **kwargs: None,
        ),
    )
    monkeypatch.setattr(
        "backend.trading.execution_service.evaluate_trade_proposal",
        lambda proposal: PolicyDecision(
            proposal_id=proposal.proposal_id,
            status="approved",
            execution_mode="paper",
            approved=True,
            approved_size_usd=proposal.requested_size_usd,
            requires_operator_approval=False,
            policy_trace=["approval=not_required"],
            rejection_reasons=[],
        ),
    )

    proposal = paired_proposal_from_legs(
        symbol="ETHUSDT",
        source_agent="delta_neutral_carry_bot",
        requested_size_usd=200.0,
        rationale="Pair spot long with perp short to capture negative funding.",
        strategy_id="delta_neutral_carry/v1.0",
        strategy_template_id="delta_neutral_carry",
        legs=[
            TradeProposalLeg(
                symbol="ETH/USDT",
                side="buy",
                requested_size_usd=200.0,
                amount=0.1,
                account_type="spot",
            ),
            TradeProposalLeg(
                symbol="ETHUSDT",
                side="sell",
                requested_size_usd=200.0,
                amount=0.1,
                account_type="swap",
                position_side="short",
            ),
        ],
        metadata={"carry_trade": True},
    )

    result = dispatch_trade_proposal(proposal)

    assert result.status == "queued"
    assert len(published) == 1
    request = ExecutionRequest.model_validate(published[0].payload)
    assert request.execution_style == "paired"
    assert len(request.legs) == 2
    assert request.legs[0].account_type == "spot"
    assert request.legs[1].account_type == "swap"
    assert request.legs[1].position_side == "short"


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


def test_worker_rolls_back_paired_execution_when_second_leg_fails(monkeypatch) -> None:
    recorded: list[object] = []
    call_log: list[tuple[str, str, str]] = []
    from backend.event_bus.workers import _place_live_order

    class FakeClient:
        configured = True

        def __init__(self, venue: str = "bitmart", *, account_type: str | None = None) -> None:
            self.venue = venue
            self.account_type = account_type or "spot"

        def place_order(self, **kwargs):
            call_log.append((self.account_type, kwargs["symbol"], kwargs["side"]))
            if self.account_type == "swap" and kwargs["side"] == "sell":
                raise RuntimeError("swap leg failed")
            return SimpleNamespace(
                order_id=f"ord-{self.account_type}-{kwargs['side']}",
                symbol=kwargs["symbol"],
                side=kwargs["side"],
                order_type=kwargs["order_type"],
                amount=kwargs["amount"],
                status="filled",
                reduce_only=kwargs.get("reduce_only"),
                model_dump=lambda mode="json", kwargs=kwargs, self=self: {
                    "order_id": f"ord-{self.account_type}-{kwargs['side']}",
                    "exchange": "BITMART",
                    "symbol": kwargs["symbol"],
                    "side": kwargs["side"],
                    "order_type": kwargs["order_type"],
                    "status": "filled",
                    "amount": kwargs["amount"],
                    "reduce_only": kwargs.get("reduce_only"),
                },
            )

    import backend.integrations.execution as execution_module

    monkeypatch.setattr(execution_module, "VenueExecutionClient", FakeClient)
    monkeypatch.setattr(
        "backend.event_bus.workers._record_execution_event",
        lambda event, outcome: recorded.append(outcome),
    )

    envelope = TradingEventEnvelope(
        event=TradingEvent(
            event_id="evt-paired-fail",
            event_type="execution_requested",
            symbol="ETHUSDT",
            correlation_id="corr-paired-fail",
            workflow_id="wf-paired-fail",
            payload={
                "proposal_id": "proposal-paired-fail",
                "request_id": "exec_req_paired_fail",
                "execution_style": "paired",
                "symbol": "ETHUSDT",
                "side": "buy",
                "order_type": "market",
                "size_usd": 200.0,
                "amount": 200.0,
                "legs": [
                    {
                        "leg_id": "leg-spot",
                        "symbol": "ETH/USDT",
                        "side": "buy",
                        "order_type": "market",
                        "size_usd": 200.0,
                        "amount": 0.1,
                        "client_order_id": "spot-leg-1",
                        "account_type": "spot",
                        "venue": "bitmart",
                    },
                    {
                        "leg_id": "leg-perp",
                        "symbol": "ETHUSDT",
                        "side": "sell",
                        "order_type": "market",
                        "size_usd": 200.0,
                        "amount": 0.1,
                        "client_order_id": "perp-leg-1",
                        "account_type": "swap",
                        "venue": "bitmart",
                        "position_side": "short",
                    },
                ],
                "metadata": {"carry_trade": True},
            },
        )
    )

    handled = _place_live_order(envelope)

    assert handled is True
    assert len(recorded) == 1
    assert recorded[0].result.status == "failed"
    rollback = recorded[0].result.payload["rollback"]
    assert rollback[0]["rolled_back"] is True
    assert ("spot", "ETH/USDT", "buy") in call_log
    assert ("spot", "ETH/USDT", "sell") in call_log
