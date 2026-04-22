"""Core typed trading graph for Hermes."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Annotated, Any

from pydantic_graph import BaseNode, Edge, End, Graph, GraphRunContext

from backend.observability import AuditContext, derived_audit_context, use_audit_context
from backend.observability.service import get_observability_service

from .agents import run_typed_agent
from .deps import TradingWorkflowDeps
from .models import (
    EvidenceItem,
    ExecutionIntent,
    OrchestratorOutput,
    ResearcherOutput,
    RiskOutput,
    StrategyOutput,
    TradingBranchDecision,
    TradingInputEvent,
    TradingWorkflowState,
    WorkflowStage,
)

logger = logging.getLogger(__name__)


def _safe_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, default=str)


def _publish_execution_requested(state: TradingWorkflowState, output: OrchestratorOutput) -> None:
    """Publish an execution_requested event to the Redis trading stream.

    This triggers the execution worker which will route the order through
    CCXTExecutionClient (paper-mode safe via HERMES_PAPER_MODE env var).
    """
    try:
        from backend.event_bus.publisher import publish_trading_event
        from backend.event_bus.models import TradingEvent
        from backend.trading.models import ExecutionRequest

        intent = output.execution_intent
        if intent is None:
            return

        request = ExecutionRequest(
            symbol=intent.symbol or state.input_event.symbol or "",
            side=intent.action.lower() if intent.action.lower() in {"buy", "sell"} else "buy",
            order_type="market",
            size_usd=intent.size_usd,
            amount=intent.size_usd,
            rationale=intent.rationale,
            timeframe=intent.timeframe,
            stop_guidance=intent.stop_guidance,
            source_agent="trading_workflow_graph",
            metadata={
                "workflow_id": state.workflow_id,
                "signal_event_id": state.input_event.event_id,
                "input_correlation_id": state.input_event.correlation_id,
            },
        )

        event = TradingEvent(
            event_type="execution_requested",
            symbol=state.input_event.symbol,
            alert_id=state.input_event.alert_id,
            correlation_id=state.input_event.correlation_id or state.workflow_id,
            causation_id=state.workflow_id,
            producer="trading_workflow_graph",
            workflow_id=state.workflow_id,
            payload=request.model_dump(mode="json"),
            metadata={"execution_request_id": request.request_id, "idempotency_key": request.idempotency_key},
        )
        publish_trading_event(event)
        logger.info(
            "workflow: published execution_requested for symbol=%s side=%s workflow_id=%s request_id=%s",
            event.symbol,
            intent.side,
            state.workflow_id,
            request.request_id,
        )
    except Exception as exc:
        logger.warning("workflow: failed to publish execution_requested: %s", exc)


def _record_stage(state: TradingWorkflowState, stage: WorkflowStage, detail: str) -> None:
    state.current_stage = stage
    state.execution_trace.append(f"{stage.value}:{detail}")


def _step_id(state: TradingWorkflowState, stage: WorkflowStage) -> str:
    return f"{state.workflow_id}:{stage.value}"


def _record_step_start(
    state: TradingWorkflowState,
    *,
    workflow_step: str,
    summarized_input: Any = None,
    agent_name: str | None = None,
) -> None:
    get_observability_service().record_workflow_step(
        step_id=_step_id(state, state.current_stage),
        workflow_run_id=state.workflow_id,
        workflow_name="trading_workflow_graph",
        workflow_step=workflow_step,
        status="started",
        agent_name=agent_name,
        summarized_input=summarized_input,
    )


def _record_step_finish(
    state: TradingWorkflowState,
    *,
    workflow_step: str,
    status: str,
    summarized_output: Any = None,
    error_message: str | None = None,
    agent_name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    get_observability_service().record_workflow_step(
        step_id=_step_id(state, state.current_stage),
        workflow_run_id=state.workflow_id,
        workflow_name="trading_workflow_graph",
        workflow_step=workflow_step,
        status=status,
        agent_name=agent_name,
        summarized_output=summarized_output,
        error_message=error_message,
        metadata=metadata,
    )


def _collect_warning_messages(tool_payloads: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    for name, result in tool_payloads.items():
        if not result.ok:
            detail = result.detail or result.error or "tool returned ok=false"
            warnings.append(f"{name}: {detail}")
        warnings.extend(f"{name}: {warning}" for warning in result.warnings)
    return warnings


def _infer_action(direction: str | None, signal: str | None) -> str:
    normalized = (direction or signal or "").lower()
    if normalized in {"buy", "long", "entry_long"}:
        return "long"
    if normalized in {"sell", "short", "entry_short"}:
        return "short"
    return "watch"


async def _gather_research_context(event: TradingInputEvent, deps: TradingWorkflowDeps) -> dict[str, Any]:
    async def _call(func_name: str, payload: dict[str, Any] | None = None) -> Any:
        tool = getattr(deps.tools, func_name)
        return await asyncio.to_thread(tool, payload or {})

    tasks = {
        "alert_context": asyncio.create_task(
            _call(
                "get_tradingview_alert_context",
                {"alert_id": event.alert_id, "symbol": event.symbol, "limit": 5},
            )
        ),
        "market_overview": asyncio.create_task(_call("get_market_overview")),
        "macro_regime": asyncio.create_task(_call("get_macro_regime_summary")),
        "event_risk": asyncio.create_task(_call("get_event_risk_summary", {"query": event.symbol or "crypto"})),
        "onchain_signal": asyncio.create_task(
            _call("get_onchain_signal_summary", {"asset": event.symbol or "BTC", "symbol": event.symbol or "BTC"})
        ),
        "volatility": asyncio.create_task(
            _call("get_volatility_metrics", {"symbol": event.symbol or "BTC", "interval": "1d", "limit": 30})
        ),
        "portfolio_state": asyncio.create_task(_call("get_portfolio_state")),
    }
    return {name: await task for name, task in tasks.items()}


def _draft_research_output(event: TradingInputEvent, tool_payloads: dict[str, Any]) -> ResearcherOutput:
    warnings = _collect_warning_messages(tool_payloads)
    market_data = tool_payloads["market_overview"].data or {}
    macro_data = tool_payloads["macro_regime"].data or {}
    volatility_data = tool_payloads["volatility"].data or {}
    event_risk_data = tool_payloads["event_risk"].data or {}
    onchain_data = tool_payloads["onchain_signal"].data or {}

    catalysts = []
    catalysts.extend(event_risk_data.get("catalysts", [])[:3] if isinstance(event_risk_data, dict) else [])
    if summary := onchain_data.get("summary") if isinstance(onchain_data, dict) else None:
        catalysts.append(summary)

    realized_vol = volatility_data.get("realized_volatility") if isinstance(volatility_data, dict) else None
    if realized_vol is None:
        volatility_regime = "unknown"
    elif realized_vol >= 0.08:
        volatility_regime = "elevated"
    elif realized_vol <= 0.03:
        volatility_regime = "contained"
    else:
        volatility_regime = "normal"

    decision = TradingBranchDecision.CONTINUE
    confidence = 0.68
    if not event.symbol:
        decision = TradingBranchDecision.REJECT
        confidence = 0.1
        warnings.append("input event is missing symbol")
    elif (event_risk_data.get("severity") if isinstance(event_risk_data, dict) else None) == "high":
        confidence = 0.45
    elif market_data.get("regime") == "risk_off":
        confidence = 0.52

    evidence = [
        EvidenceItem(
            source="market_overview",
            tool_name="get_market_overview",
            summary=f"Market regime={market_data.get('regime', 'unknown')}",
            detail=market_data if isinstance(market_data, dict) else {},
        ),
        EvidenceItem(
            source="macro_regime",
            tool_name="get_macro_regime_summary",
            summary=macro_data.get("summary", "Macro regime unavailable") if isinstance(macro_data, dict) else "Macro regime unavailable",
            detail=macro_data if isinstance(macro_data, dict) else {},
        ),
        EvidenceItem(
            source="event_risk",
            tool_name="get_event_risk_summary",
            summary=event_risk_data.get("summary", "Event risk unavailable") if isinstance(event_risk_data, dict) else "Event risk unavailable",
            detail=event_risk_data if isinstance(event_risk_data, dict) else {},
        ),
    ]

    return ResearcherOutput(
        decision=decision,
        confidence=confidence,
        summary=(
            f"Research package for {event.symbol or 'unknown'} synthesized from market, macro, volatility, "
            "news-risk, and onchain context."
        ),
        market_regime=market_data.get("regime", "unknown") if isinstance(market_data, dict) else "unknown",
        risk_bias=macro_data.get("risk_bias", "unknown") if isinstance(macro_data, dict) else "unknown",
        volatility_regime=volatility_regime,
        catalysts=catalysts[:5],
        warnings=warnings,
        evidence=evidence,
        raw_context={name: result.model_dump(mode="json") for name, result in tool_payloads.items()},
    )


def _draft_strategy_output(state: TradingWorkflowState, portfolio_state: dict[str, Any]) -> StrategyOutput:
    event = state.input_event
    research = state.research_output
    action = _infer_action(event.direction, event.signal)
    total_equity = portfolio_state.get("total_equity_usd") if isinstance(portfolio_state, dict) else None
    proposed_size = round((total_equity or 50_000) * 0.02, 2)
    decision = TradingBranchDecision.CONTINUE if research and research.decision != TradingBranchDecision.REJECT else TradingBranchDecision.REJECT
    confidence = min(0.85, max(0.35, (research.confidence if research else 0.35) + (0.1 if action != "watch" else -0.1)))

    return StrategyOutput(
        decision=decision,
        confidence=confidence,
        strategy_name=event.strategy or "workflow_v1",
        action=action,
        thesis=(
            f"{event.symbol or 'Unknown asset'} {action} setup derived from TradingView signal, "
            f"research confidence {research.confidence if research else 0.0:.2f}, "
            f"and market regime {research.market_regime if research else 'unknown'}."
        ),
        timeframe=event.timeframe,
        proposed_size_usd=proposed_size,
        entry_plan=f"Use staged {action} entry aligned to {event.timeframe or 'workflow default'} confirmation.",
        invalidation="Exit if price action invalidates the alert direction or risk bias flips materially.",
        reasons=[
            f"signal={event.signal or 'unknown'}",
            f"direction={event.direction or 'unknown'}",
            f"market_regime={research.market_regime if research else 'unknown'}",
        ],
        warnings=list(research.warnings if research else []),
    )


def _draft_risk_output(state: TradingWorkflowState, approval_payload: dict[str, Any]) -> RiskOutput:
    approval = approval_payload if isinstance(approval_payload, dict) else {}
    approved = bool(approval.get("approved"))
    blocking_reasons = [] if approved else list(approval.get("reasons", []))
    decision = TradingBranchDecision.EXECUTE if approved else TradingBranchDecision.REJECT
    confidence = float(approval.get("confidence") or (0.75 if approved else 0.3))
    risk_score = round(1.0 - confidence, 2)

    return RiskOutput(
        decision=decision,
        approved=approved,
        confidence=confidence,
        summary="Risk layer validated proposed size against volatility and event-risk context.",
        max_size_usd=approval.get("max_size_usd"),
        risk_score=risk_score,
        blocking_reasons=blocking_reasons,
        required_actions=[] if approved else ["Reduce size or wait for lower volatility / event-risk confirmation."],
        stop_guidance=approval.get("stop_guidance"),
        warnings=[],
    )


def _draft_orchestrator_output(state: TradingWorkflowState, route_hint: TradingBranchDecision) -> OrchestratorOutput:
    event = state.input_event
    strategy = state.strategy_output
    risk = state.risk_output
    if route_hint == TradingBranchDecision.REJECT:
        return OrchestratorOutput(
            decision=TradingBranchDecision.REJECT,
            status="rejected",
            summary="Workflow halted before execution because one of the gating nodes rejected the trade.",
            should_execute=False,
            notifications=["send_risk_alert"],
            audit={"branch_history": [branch.value for branch in state.branch_history]},
        )

    if route_hint == TradingBranchDecision.EXECUTE and strategy is not None and risk is not None:
        return OrchestratorOutput(
            decision=TradingBranchDecision.EXECUTE,
            status="approved",
            summary="Trade approved for execution handoff. Durable execution remains intentionally out of scope in v1.",
            should_execute=True,
            execution_intent=ExecutionIntent(
                symbol=event.symbol or "UNKNOWN",
                action=strategy.action,
                size_usd=min(strategy.proposed_size_usd or 0.0, risk.max_size_usd or strategy.proposed_size_usd or 0.0),
                timeframe=event.timeframe,
                stop_guidance=risk.stop_guidance,
                rationale=strategy.thesis,
            ),
            notifications=["send_trade_alert", "send_execution_update"],
            audit={"branch_history": [branch.value for branch in state.branch_history]},
        )

    return OrchestratorOutput(
        decision=TradingBranchDecision.CONTINUE,
        status="manual_review",
        summary="Workflow completed with a continue decision; operator review is required before execution.",
        should_execute=False,
        notifications=["send_trade_alert"],
        audit={"branch_history": [branch.value for branch in state.branch_history]},
    )


@dataclass
class RejectTerminalNode(BaseNode[TradingWorkflowState, TradingWorkflowDeps, OrchestratorOutput]):
    reason: str

    async def run(self, ctx: GraphRunContext[TradingWorkflowState, TradingWorkflowDeps]) -> End[OrchestratorOutput]:
        with derived_audit_context(
            workflow_run_id=ctx.state.workflow_id,
            workflow_name="trading_workflow_graph",
            workflow_step=WorkflowStage.COMPLETED.value,
            agent_name="orchestrator_trader",
        ):
            logger.info("workflow reject terminal workflow_id=%s reason=%s", ctx.state.workflow_id, self.reason)
            ctx.state.branch_history.append(TradingBranchDecision.REJECT)
            _record_stage(ctx.state, WorkflowStage.COMPLETED, f"reject:{self.reason}")
            output = _draft_orchestrator_output(ctx.state, TradingBranchDecision.REJECT)
            output.summary = f"{output.summary} reason={self.reason}"
            ctx.state.orchestrator_output = output
            get_observability_service().record_execution_event(
                status="rejected",
                event_type="workflow_terminal_reject",
                summarized_output=output.model_dump(mode="json"),
                metadata={"reason": self.reason},
            )
            return End(output)


@dataclass
class FinalOrchestrationDecisionNode(BaseNode[TradingWorkflowState, TradingWorkflowDeps, OrchestratorOutput]):
    route_hint: TradingBranchDecision

    async def run(self, ctx: GraphRunContext[TradingWorkflowState, TradingWorkflowDeps]) -> End[OrchestratorOutput]:
        with derived_audit_context(
            workflow_run_id=ctx.state.workflow_id,
            workflow_name="trading_workflow_graph",
            workflow_step=WorkflowStage.FINAL_ORCHESTRATION_DECISION.value,
            agent_name="orchestrator_trader",
        ):
            logger.info(
                "workflow final orchestration workflow_id=%s route_hint=%s",
                ctx.state.workflow_id,
                self.route_hint,
            )
            _record_stage(ctx.state, WorkflowStage.FINAL_ORCHESTRATION_DECISION, self.route_hint.value)
            _record_step_start(
                ctx.state,
                workflow_step=WorkflowStage.FINAL_ORCHESTRATION_DECISION.value,
                summarized_input={"route_hint": self.route_hint.value},
                agent_name="orchestrator_trader",
            )
            draft = _draft_orchestrator_output(ctx.state, self.route_hint)
            prompt = (
                "You are orchestrator_trader. Produce the final typed orchestration decision for the trade pipeline.\n\n"
                f"Route hint: {self.route_hint.value}\n"
                f"State:\n{_safe_json(ctx.state.model_dump(mode='json'))}"
            )
            output = await run_typed_agent(
                name="orchestrator_trader",
                system_prompt=(
                    "You are Hermes orchestrator_trader. Validate the final workflow state and return a typed "
                    "orchestration decision. Do not invent execution side effects that are not present in the state."
                ),
                prompt=prompt,
                output_model=OrchestratorOutput,
                deps=ctx.deps,
                fallback_output=draft,
            )
            ctx.state.orchestrator_output = output
            ctx.state.branch_history.append(output.decision)
            _record_stage(ctx.state, WorkflowStage.COMPLETED, output.decision.value)
            _record_step_finish(
                ctx.state,
                workflow_step=WorkflowStage.FINAL_ORCHESTRATION_DECISION.value,
                status=output.status,
                summarized_output=output.model_dump(mode="json"),
                agent_name="orchestrator_trader",
            )
            if output.should_execute:
                get_observability_service().record_execution_event(
                    status="approved",
                    event_type="execution_handoff_ready",
                    summarized_output=output.model_dump(mode="json"),
                    metadata={"notifications": output.notifications},
                )
                _publish_execution_requested(ctx.state, output)
            return End(output)


@dataclass
class RiskDecisionNode(BaseNode[TradingWorkflowState, TradingWorkflowDeps, OrchestratorOutput]):
    async def run(
        self,
        ctx: GraphRunContext[TradingWorkflowState, TradingWorkflowDeps],
    ) -> (
        Annotated[RejectTerminalNode, Edge(label="reject")]
        | Annotated[FinalOrchestrationDecisionNode, Edge(label="continue")]
        | Annotated[FinalOrchestrationDecisionNode, Edge(label="execute")]
    ):
        risk = ctx.state.risk_output
        assert risk is not None, "Risk output must exist before RiskDecisionNode"
        logger.info(
            "workflow risk decision workflow_id=%s decision=%s approved=%s",
            ctx.state.workflow_id,
            risk.decision,
            risk.approved,
        )
        if risk.decision == TradingBranchDecision.REJECT:
            return RejectTerminalNode(reason="risk_review_rejected")
        if risk.decision == TradingBranchDecision.EXECUTE:
            return FinalOrchestrationDecisionNode(route_hint=TradingBranchDecision.EXECUTE)
        return FinalOrchestrationDecisionNode(route_hint=TradingBranchDecision.CONTINUE)


@dataclass
class RiskReviewNode(BaseNode[TradingWorkflowState, TradingWorkflowDeps, OrchestratorOutput]):
    async def run(self, ctx: GraphRunContext[TradingWorkflowState, TradingWorkflowDeps]) -> RiskDecisionNode:
        with derived_audit_context(
            workflow_run_id=ctx.state.workflow_id,
            workflow_name="trading_workflow_graph",
            workflow_step=WorkflowStage.RISK_REVIEW.value,
            agent_name="risk_manager",
        ):
            _record_stage(ctx.state, WorkflowStage.RISK_REVIEW, "start")
            event = ctx.state.input_event
            strategy = ctx.state.strategy_output
            assert strategy is not None, "Strategy output must exist before risk review"
            logger.info(
                "workflow risk review workflow_id=%s symbol=%s proposed_size_usd=%s",
                ctx.state.workflow_id,
                event.symbol,
                strategy.proposed_size_usd,
            )
            _record_step_start(
                ctx.state,
                workflow_step=WorkflowStage.RISK_REVIEW.value,
                summarized_input={"event": event.model_dump(mode="json"), "strategy": strategy.model_dump(mode="json")},
                agent_name="risk_manager",
            )

            approval_result = await asyncio.to_thread(
                ctx.deps.tools.get_risk_approval,
                {"symbol": event.symbol or "BTC", "proposed_size_usd": strategy.proposed_size_usd or 0.0},
            )
            draft = _draft_risk_output(ctx.state, approval_result.data or {})
            prompt = (
                "You are risk_manager. Review the proposed trade and return typed risk output.\n\n"
                f"Event:\n{_safe_json(event.model_dump(mode='json'))}\n\n"
                f"Strategy:\n{_safe_json(strategy.model_dump(mode='json'))}\n\n"
                f"Risk approval tool:\n{_safe_json(approval_result.model_dump(mode='json'))}"
            )
            output = await run_typed_agent(
                name="risk_manager",
                system_prompt=(
                    "You are Hermes risk_manager. Keep outputs conservative, validated, and aligned to the input evidence. "
                    "Reject when the size or event-risk context is not supportable."
                ),
                prompt=prompt,
                output_model=RiskOutput,
                deps=ctx.deps,
                fallback_output=draft,
            )
            ctx.state.risk_output = output
            ctx.state.branch_history.append(output.decision)
            _record_step_finish(
                ctx.state,
                workflow_step=WorkflowStage.RISK_REVIEW.value,
                status=output.decision.value,
                summarized_output=output.model_dump(mode="json"),
                agent_name="risk_manager",
            )
            if output.decision == TradingBranchDecision.REJECT:
                get_observability_service().record_execution_event(
                    status="rejected",
                    event_type="risk_rejection",
                    summarized_output=output.model_dump(mode="json"),
                    metadata={"blocking_reasons": output.blocking_reasons},
                )
            return RiskDecisionNode()


@dataclass
class StrategyDecisionNode(BaseNode[TradingWorkflowState, TradingWorkflowDeps, OrchestratorOutput]):
    async def run(
        self,
        ctx: GraphRunContext[TradingWorkflowState, TradingWorkflowDeps],
    ) -> Annotated[RejectTerminalNode, Edge(label="reject")] | Annotated[RiskReviewNode, Edge(label="continue")]:
        strategy = ctx.state.strategy_output
        assert strategy is not None, "Strategy output must exist before StrategyDecisionNode"
        logger.info(
            "workflow strategy decision workflow_id=%s decision=%s action=%s",
            ctx.state.workflow_id,
            strategy.decision,
            strategy.action,
        )
        if strategy.decision == TradingBranchDecision.REJECT:
            return RejectTerminalNode(reason="strategy_planning_rejected")
        return RiskReviewNode()


@dataclass
class StrategyPlanningNode(BaseNode[TradingWorkflowState, TradingWorkflowDeps, OrchestratorOutput]):
    async def run(self, ctx: GraphRunContext[TradingWorkflowState, TradingWorkflowDeps]) -> StrategyDecisionNode:
        with derived_audit_context(
            workflow_run_id=ctx.state.workflow_id,
            workflow_name="trading_workflow_graph",
            workflow_step=WorkflowStage.STRATEGY_PLANNING.value,
            agent_name="strategy_agent",
        ):
            _record_stage(ctx.state, WorkflowStage.STRATEGY_PLANNING, "start")
            event = ctx.state.input_event
            research = ctx.state.research_output
            assert research is not None, "Research output must exist before strategy planning"
            logger.info("workflow strategy planning workflow_id=%s symbol=%s", ctx.state.workflow_id, event.symbol)
            _record_step_start(
                ctx.state,
                workflow_step=WorkflowStage.STRATEGY_PLANNING.value,
                summarized_input={"event": event.model_dump(mode="json"), "research": research.model_dump(mode="json")},
                agent_name="strategy_agent",
            )

            portfolio_result = await asyncio.to_thread(ctx.deps.tools.get_portfolio_state, {})
            draft = _draft_strategy_output(ctx.state, portfolio_result.data or {})
            prompt = (
                "You are strategy_agent. Turn the workflow research package into a typed strategy plan.\n\n"
                f"Event:\n{_safe_json(event.model_dump(mode='json'))}\n\n"
                f"Research:\n{_safe_json(research.model_dump(mode='json'))}\n\n"
                f"Portfolio:\n{_safe_json(portfolio_result.model_dump(mode='json'))}"
            )
            output = await run_typed_agent(
                name="strategy_agent",
                system_prompt=(
                    "You are Hermes strategy_agent. Produce a concrete but safe trade plan with explicit size, thesis, "
                    "and invalidation. Reject when the signal is too weak or underspecified."
                ),
                prompt=prompt,
                output_model=StrategyOutput,
                deps=ctx.deps,
                fallback_output=draft,
            )
            ctx.state.strategy_output = output
            ctx.state.branch_history.append(output.decision)
            _record_step_finish(
                ctx.state,
                workflow_step=WorkflowStage.STRATEGY_PLANNING.value,
                status=output.decision.value,
                summarized_output=output.model_dump(mode="json"),
                agent_name="strategy_agent",
            )
            return StrategyDecisionNode()


@dataclass
class ResearchDecisionNode(BaseNode[TradingWorkflowState, TradingWorkflowDeps, OrchestratorOutput]):
    async def run(
        self,
        ctx: GraphRunContext[TradingWorkflowState, TradingWorkflowDeps],
    ) -> Annotated[RejectTerminalNode, Edge(label="reject")] | Annotated[StrategyPlanningNode, Edge(label="continue")]:
        research = ctx.state.research_output
        assert research is not None, "Research output must exist before ResearchDecisionNode"
        logger.info(
            "workflow research decision workflow_id=%s decision=%s confidence=%.2f",
            ctx.state.workflow_id,
            research.decision,
            research.confidence,
        )
        if research.decision == TradingBranchDecision.REJECT:
            return RejectTerminalNode(reason="market_research_rejected")
        return StrategyPlanningNode()


@dataclass
class MarketResearchNode(BaseNode[TradingWorkflowState, TradingWorkflowDeps, OrchestratorOutput]):
    async def run(self, ctx: GraphRunContext[TradingWorkflowState, TradingWorkflowDeps]) -> ResearchDecisionNode:
        with derived_audit_context(
            workflow_run_id=ctx.state.workflow_id,
            workflow_name="trading_workflow_graph",
            workflow_step=WorkflowStage.MARKET_RESEARCH.value,
            agent_name="market_researcher",
        ):
            _record_stage(ctx.state, WorkflowStage.MARKET_RESEARCH, "start")
            event = ctx.state.input_event
            logger.info("workflow market research workflow_id=%s symbol=%s", ctx.state.workflow_id, event.symbol)
            _record_step_start(
                ctx.state,
                workflow_step=WorkflowStage.MARKET_RESEARCH.value,
                summarized_input=event.model_dump(mode="json"),
                agent_name="market_researcher",
            )

            tool_payloads = await _gather_research_context(event, ctx.deps)
            draft = _draft_research_output(event, tool_payloads)
            prompt = (
                "You are market_researcher. Synthesize the signal context and produce typed research output.\n\n"
                f"Event:\n{_safe_json(event.model_dump(mode='json'))}\n\n"
                f"Research context:\n{_safe_json({name: result.model_dump(mode='json') for name, result in tool_payloads.items()})}"
            )
            output = await run_typed_agent(
                name="market_researcher",
                system_prompt=(
                    "You are Hermes market_researcher. Use the provided tool context only, surface uncertainty clearly, "
                    "and reject low-integrity or underspecified signals."
                ),
                prompt=prompt,
                output_model=ResearcherOutput,
                deps=ctx.deps,
                fallback_output=draft,
            )
            ctx.state.research_output = output
            ctx.state.warnings.extend(output.warnings)
            ctx.state.branch_history.append(output.decision)
            _record_step_finish(
                ctx.state,
                workflow_step=WorkflowStage.MARKET_RESEARCH.value,
                status=output.decision.value,
                summarized_output=output.model_dump(mode="json"),
                agent_name="market_researcher",
            )
            return ResearchDecisionNode()


@dataclass
class IngestSignalNode(BaseNode[TradingWorkflowState, TradingWorkflowDeps, OrchestratorOutput]):
    async def run(
        self,
        ctx: GraphRunContext[TradingWorkflowState, TradingWorkflowDeps],
    ) -> Annotated[RejectTerminalNode, Edge(label="reject")] | Annotated[MarketResearchNode, Edge(label="continue")]:
        with derived_audit_context(
            workflow_run_id=ctx.state.workflow_id,
            workflow_name="trading_workflow_graph",
            workflow_step=WorkflowStage.INGEST_SIGNAL.value,
            agent_name="orchestrator_trader",
        ):
            _record_stage(ctx.state, WorkflowStage.INGEST_SIGNAL, "validate_input")
            event = ctx.state.input_event
            logger.info(
                "workflow ingest signal workflow_id=%s symbol=%s alert_id=%s",
                ctx.state.workflow_id,
                event.symbol,
                event.alert_id,
            )
            _record_step_start(
                ctx.state,
                workflow_step=WorkflowStage.INGEST_SIGNAL.value,
                summarized_input=event.model_dump(mode="json"),
                agent_name="orchestrator_trader",
            )
            if not event.symbol or not (event.signal or event.direction):
                reason = "missing_symbol_or_signal"
                ctx.state.warnings.append(reason)
                _record_step_finish(
                    ctx.state,
                    workflow_step=WorkflowStage.INGEST_SIGNAL.value,
                    status="rejected",
                    error_message=reason,
                    agent_name="orchestrator_trader",
                )
                return RejectTerminalNode(reason=reason)
            _record_step_finish(
                ctx.state,
                workflow_step=WorkflowStage.INGEST_SIGNAL.value,
                status="completed",
                summarized_output={"symbol": event.symbol, "signal": event.signal, "direction": event.direction},
                agent_name="orchestrator_trader",
            )
            return MarketResearchNode()


def build_trading_workflow_graph() -> Graph[TradingWorkflowState, TradingWorkflowDeps, OrchestratorOutput]:
    return Graph(
        name="trading_workflow_graph",
        nodes=(
            IngestSignalNode,
            MarketResearchNode,
            ResearchDecisionNode,
            StrategyPlanningNode,
            StrategyDecisionNode,
            RiskReviewNode,
            RiskDecisionNode,
            FinalOrchestrationDecisionNode,
            RejectTerminalNode,
        ),
        state_type=TradingWorkflowState,
        run_end_type=OrchestratorOutput,
    )


trading_workflow_graph = build_trading_workflow_graph()


async def run_trading_workflow(
    event: TradingInputEvent,
    deps: TradingWorkflowDeps | None = None,
) -> Any:
    deps = deps or TradingWorkflowDeps()
    state = TradingWorkflowState.from_event(event)
    correlation_id = event.correlation_id or event.alert_id or state.workflow_id
    observability = get_observability_service()
    audit = AuditContext(
        event_id=event.event_id,
        correlation_id=correlation_id,
        workflow_run_id=state.workflow_id,
        workflow_name="trading_workflow_graph",
        workflow_step=WorkflowStage.INGEST_SIGNAL.value,
        agent_name="orchestrator_trader",
        metadata={"symbol": event.symbol, "source": event.source, "alert_id": event.alert_id},
    )
    with use_audit_context(audit):
        observability.record_workflow_run(
            workflow_run_id=state.workflow_id,
            workflow_name="trading_workflow_graph",
            status="running",
            summarized_input=event.model_dump(mode="json"),
            metadata={"symbol": event.symbol, "source": event.source, "alert_id": event.alert_id},
        )
        logger.info("workflow run start workflow_id=%s symbol=%s", state.workflow_id, event.symbol)
        try:
            async with trading_workflow_graph.iter(IngestSignalNode(), state=state, deps=deps) as graph_run:
                async for node in graph_run:
                    logger.info(
                        "workflow node completed workflow_id=%s node=%s stage=%s",
                        state.workflow_id,
                        type(node).__name__,
                        state.current_stage,
                    )

            result = graph_run.result
            assert result is not None, "Graph run should produce a result"
            observability.record_workflow_run(
                workflow_run_id=state.workflow_id,
                workflow_name="trading_workflow_graph",
                status=result.output.status,
                summarized_output=result.output.model_dump(mode="json"),
                metadata={"branch_history": [item.value for item in state.branch_history]},
            )
            logger.info(
                "workflow run complete workflow_id=%s decision=%s status=%s",
                state.workflow_id,
                result.output.decision,
                result.output.status,
            )
            return result
        except Exception as exc:
            observability.record_workflow_run(
                workflow_run_id=state.workflow_id,
                workflow_name="trading_workflow_graph",
                status="failed",
                error_message=str(exc),
                metadata={"branch_history": [item.value for item in state.branch_history]},
            )
            observability.record_system_error(
                status="workflow_failed",
                error_message=str(exc),
                error_type=exc.__class__.__name__,
                summarized_input=event.model_dump(mode="json"),
                metadata={"workflow_run_id": state.workflow_id},
            )
            raise
