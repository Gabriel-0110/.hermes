"""Proposal-driven execution dispatch."""

from __future__ import annotations

from backend.event_bus.models import TradingEvent
from backend.event_bus.publisher import publish_trading_event
from backend.observability.service import get_observability_service

from .lifecycle_notifications import (
    notify_approval_required,
    notify_proposal_blocked,
    notify_proposal_created,
)
from .models import ExecutionDispatchResult, ExecutionRequest, TradeProposal
from .policy_engine import evaluate_trade_proposal, normalize_trade_proposal


def dispatch_trade_proposal(proposal: TradeProposal) -> ExecutionDispatchResult:
    """Evaluate a proposal and, if allowed, dispatch it to the execution stream."""

    proposal = normalize_trade_proposal(proposal)
    decision = evaluate_trade_proposal(proposal)
    workflow_id = f"proposal::{proposal.proposal_id}"
    correlation_id = proposal.proposal_id

    notify_proposal_created(
        proposal_id=proposal.proposal_id,
        symbol=proposal.symbol,
        side=proposal.side,
        size_usd=proposal.requested_size_usd,
        source_agent=proposal.source_agent or "unknown",
        execution_mode=decision.execution_mode,
    )

    get_observability_service().record_agent_decision(
        agent_name="risk_manager",
        status=decision.status,
        decision="approve" if decision.approved else "reject",
        summarized_input=proposal.model_dump(mode="json"),
        summarized_output=decision.model_dump(mode="json"),
        metadata={"proposal_id": proposal.proposal_id},
    )

    request = ExecutionRequest(
        proposal_id=proposal.proposal_id,
        symbol=proposal.symbol,
        side=proposal.side,
        order_type=proposal.order_type,
        size_usd=decision.approved_size_usd,
        amount=decision.approved_size_usd,
        price=proposal.limit_price,
        rationale=proposal.rationale,
        strategy_id=proposal.strategy_id,
        strategy_template_id=proposal.strategy_template_id,
        timeframe=proposal.timeframe,
        stop_loss_price=proposal.stop_loss_price,
        take_profit_price=proposal.take_profit_price,
        source_agent=proposal.source_agent,
        policy_trace=decision.policy_trace,
        stop_guidance=decision.stop_guidance,
        metadata=proposal.metadata,
    )

    if decision.status == "rejected":
        get_observability_service().record_execution_event(
            event_type="trade_proposal_rejected",
            status="blocked",
            symbol=proposal.symbol,
            correlation_id=correlation_id,
            workflow_run_id=workflow_id,
            payload={
                "proposal": proposal.model_dump(mode="json"),
                "policy_decision": decision.model_dump(mode="json"),
                "execution_request": request.model_dump(mode="json"),
            },
        )
        notify_proposal_blocked(
            proposal_id=proposal.proposal_id,
            symbol=proposal.symbol,
            execution_mode=decision.execution_mode,
            blocking_reasons=decision.blocking_reasons,
        )
        return ExecutionDispatchResult(
            proposal_id=proposal.proposal_id,
            status="blocked",
            execution_mode=decision.execution_mode,
            correlation_id=correlation_id,
            workflow_id=workflow_id,
            approval_required=decision.requires_operator_approval,
            policy_decision=decision,
            dispatch_payload=request,
            warnings=decision.warnings,
        )

    event = TradingEvent(
        event_type="execution_requested",
        symbol=proposal.symbol,
        correlation_id=correlation_id,
        causation_id=proposal.proposal_id,
        producer="proposal_execution_service",
        workflow_id=workflow_id,
        payload=request.model_dump(mode="json"),
        metadata={
            "policy_decision": decision.model_dump(mode="json"),
            "requires_operator_approval": decision.requires_operator_approval,
            "execution_request_id": request.request_id,
            "idempotency_key": request.idempotency_key,
        },
    )
    publish_trading_event(event)

    event_type = "trade_proposal_manual_review" if decision.status == "manual_review" else "trade_proposal_dispatched"
    status = "manual_review" if decision.status == "manual_review" else "queued"
    get_observability_service().record_execution_event(
        event_type=event_type,
        status=status,
        symbol=proposal.symbol,
        correlation_id=correlation_id,
        workflow_run_id=workflow_id,
        payload={
            "proposal": proposal.model_dump(mode="json"),
            "policy_decision": decision.model_dump(mode="json"),
            "execution_request": request.model_dump(mode="json"),
        },
    )

    if decision.requires_operator_approval:
        notify_approval_required(
            proposal_id=proposal.proposal_id,
            symbol=proposal.symbol,
            side=proposal.side,
            size_usd=decision.approved_size_usd,
            execution_mode=decision.execution_mode,
        )

    return ExecutionDispatchResult(
        proposal_id=proposal.proposal_id,
        status="manual_review" if decision.status == "manual_review" else "queued",
        execution_mode=decision.execution_mode,
        correlation_id=correlation_id,
        workflow_id=workflow_id,
        approval_required=decision.requires_operator_approval,
        policy_decision=decision,
        dispatch_payload=request,
        warnings=decision.warnings,
    )
