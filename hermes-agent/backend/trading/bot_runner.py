"""Autonomous strategy bot runner — thin extension of the existing proposal pipeline.

A ``StrategyBotRunner`` is a self-contained scan-and-propose unit that:

1. Scans the market universe and scores candidates (``scan()``).
2. Converts high-confidence ``ScoredCandidate``s to ``TradeProposal``s.
3. Submits each proposal to ``dispatch_trade_proposal()``, which runs it
   through the full policy → approval → execution pipeline.

Paper mode, approval gates, kill switches, risk limits, and observability
are all inherited from the existing infrastructure.  Bot runners add no new
execution path — they are *proposal sources*, nothing more.

Scheduling
----------
Runners can be invoked in three ways:
- **Cron**: create a Hermes cron job whose prompt instructs an agent to call
  the ``run_strategy_cycle`` backend tool with the runner name and universe.
- **Direct**: call ``runner.run_cycle()`` from any async or sync context.
- **Event-driven**: call ``run_cycle()`` from an event-bus consumer that
  reacts to market signals, webhook events, or TradingView alerts.

Example (programmatic)::

    from backend.trading.bot_runner import StrategyBotRunner
    from backend.strategies.registry import ScoredCandidate

    class MyRunner(StrategyBotRunner):
        strategy_id = "my_strategy/v1"
        source_agent = "my_strategy_bot"
        default_size_usd = 50.0

        def scan(self, universe: list[str]) -> list[ScoredCandidate]:
            # Call scorers, indicators, etc.
            return [...]

    runner = MyRunner()
    results = runner.run_cycle(universe=["BTC", "ETH"])
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from backend.strategies.registry import ScoredCandidate
from backend.trading.models import (
    ExecutionDispatchResult,
    TradeProposal,
    TradeProposalLeg,
)

logger = logging.getLogger(__name__)

StrategyScanResult = ScoredCandidate | TradeProposal


def _persist_strategy_scan_artifacts(
    proposals: list[tuple[TradeProposal, ScoredCandidate | None]],
) -> None:
    """Persist actionable scan output for nightly evaluation and audit joins."""
    if not proposals:
        return

    try:
        from backend.db import ensure_time_series_schema, session_scope
        from backend.db.models import AgentSignalRow, StrategyEvaluationRow
        from backend.db.session import get_engine

        ensure_time_series_schema(get_engine())
        with session_scope() as session:
            for proposal, candidate in proposals:
                signal_time = _parse_signal_time(proposal.created_at)
                strategy_name = (
                    candidate.strategy_name
                    if candidate is not None
                    else proposal.strategy_template_id or proposal.strategy_id or "proposal"
                )
                direction = candidate.direction if candidate is not None else ("long" if proposal.side == "buy" else "short")
                confidence = (
                    candidate.confidence
                    if candidate is not None
                    else float(proposal.metadata.get("confidence") or 0.5)
                )
                payload = {
                    "proposal_id": proposal.proposal_id,
                    "strategy_id": proposal.strategy_id,
                    "strategy_template_id": proposal.strategy_template_id,
                    "strategy_name": strategy_name,
                    "timeframe": proposal.timeframe,
                    "source_agent": proposal.source_agent,
                    "rationale": candidate.rationale if candidate is not None else proposal.rationale,
                    "chronos_score": candidate.chronos_score if candidate is not None else proposal.metadata.get("chronos_score"),
                    "metadata": proposal.metadata,
                }

                session.add(
                    AgentSignalRow(
                        signal_time=signal_time,
                        agent_id=proposal.source_agent,
                        symbol=proposal.symbol,
                        signal_type=strategy_name,
                        direction=direction,
                        confidence=confidence,
                        payload=payload,
                    )
                )

                if candidate is not None:
                    session.add(
                        StrategyEvaluationRow(
                            eval_time=signal_time,
                            strategy_name=candidate.strategy_name,
                            strategy_version=candidate.strategy_version,
                            symbol=candidate.symbol,
                            timeframe=proposal.timeframe or "1h",
                            direction=candidate.direction,
                            confidence=candidate.confidence,
                            rationale=candidate.rationale,
                            metadata_json={
                                "proposal_id": proposal.proposal_id,
                                "strategy_id": proposal.strategy_id,
                                "source_agent": proposal.source_agent,
                                "signal_type": strategy_name,
                                "chronos_score": candidate.chronos_score,
                                "metadata": proposal.metadata,
                            },
                        )
                    )
    except Exception as exc:
        logger.debug("bot_runner: strategy scan persistence failed (non-critical): %s", exc)

# ---------------------------------------------------------------------------
# Proposal factory helper
# ---------------------------------------------------------------------------


def proposal_from_candidate(
    candidate: ScoredCandidate,
    *,
    size_usd: float,
    source_agent: str,
    strategy_id: str | None = None,
    timeframe: str | None = None,
    require_operator_approval: bool | None = None,
    metadata: dict[str, Any] | None = None,
) -> TradeProposal:
    """Convert a ``ScoredCandidate`` into a ``TradeProposal``.

    Only ``long`` and ``short`` directions are mapped to actionable proposals.
    Callers should filter out ``watch`` candidates before calling this helper.
    """
    if candidate.direction == "watch":
        raise ValueError(
            f"Cannot create a proposal for watch-only candidate: {candidate.symbol}"
        )

    side = "buy" if candidate.direction == "long" else "sell"

    return TradeProposal(
        source_agent=source_agent,
        symbol=candidate.symbol,
        side=side,
        order_type="market",
        requested_size_usd=size_usd,
        rationale=(
            f"[{candidate.strategy_name} v{candidate.strategy_version}] "
            f"confidence={candidate.confidence:.2f} — {candidate.rationale}"
        ),
        strategy_id=strategy_id,
        strategy_template_id=candidate.strategy_name,
        timeframe=timeframe,
        require_operator_approval=require_operator_approval,
        metadata={
            "confidence": candidate.confidence,
            "chronos_score": candidate.chronos_score,
            **(metadata or {}),
        },
    )


def paired_proposal_from_legs(
    *,
    symbol: str,
    source_agent: str,
    requested_size_usd: float,
    rationale: str,
    legs: list[TradeProposalLeg],
    strategy_id: str | None = None,
    strategy_template_id: str | None = None,
    timeframe: str | None = None,
    require_operator_approval: bool | None = None,
    metadata: dict[str, Any] | None = None,
) -> TradeProposal:
    """Build a paired proposal containing two or more explicit execution legs."""
    if len(legs) < 2:
        raise ValueError("paired proposals require at least two legs")

    primary_leg = legs[0]
    return TradeProposal(
        source_agent=source_agent,
        execution_style="paired",
        symbol=symbol,
        side=primary_leg.side,
        order_type=primary_leg.order_type,
        requested_size_usd=requested_size_usd,
        rationale=rationale,
        strategy_id=strategy_id,
        strategy_template_id=strategy_template_id,
        timeframe=timeframe,
        require_operator_approval=require_operator_approval,
        legs=legs,
        metadata=metadata or {},
    )


def paired_unwind_proposal(
    proposal: TradeProposal,
    *,
    reason: str,
    source_agent: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> TradeProposal:
    """Create an inverse paired proposal suitable for stop-based unwind flows."""
    if proposal.execution_style != "paired" or len(proposal.legs) < 2:
        raise ValueError("paired_unwind_proposal requires a paired TradeProposal")

    unwind_legs = [
        TradeProposalLeg(
            symbol=leg.symbol,
            side="sell" if leg.side == "buy" else "buy",
            order_type="market",
            requested_size_usd=leg.requested_size_usd,
            amount=leg.amount,
            venue=leg.venue,
            account_type=leg.account_type,
            reduce_only=leg.account_type in {"swap", "futures", "contract"},
            position_side=leg.position_side,
            metadata={**leg.metadata, "paired_action": "unwind", "unwind_reason": reason},
        )
        for leg in proposal.legs
    ]

    return paired_proposal_from_legs(
        symbol=proposal.symbol,
        source_agent=source_agent or proposal.source_agent,
        requested_size_usd=proposal.requested_size_usd,
        rationale=f"[paired unwind] {reason}",
        legs=unwind_legs,
        strategy_id=proposal.strategy_id,
        strategy_template_id=proposal.strategy_template_id,
        timeframe=proposal.timeframe,
        require_operator_approval=proposal.require_operator_approval,
        metadata={
            **proposal.metadata,
            "paired_parent_proposal_id": proposal.proposal_id,
            "paired_action": "unwind",
            **(metadata or {}),
        },
    )


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class StrategyBotRunner(ABC):
    """Abstract base for autonomous strategy runners.

    Subclass and implement ``scan()``.  Everything else — risk gating,
    approval routing, execution, and observability — is handled by the
    existing pipeline via ``dispatch_trade_proposal()``.

    Class attributes
    ----------------
    strategy_id:
        Unique stable identifier for this runner (e.g. ``"momentum/v1.1"``).
        Carried through proposals and audit logs.
    source_agent:
        Agent identity surfaced in proposals and observability records.
    default_size_usd:
        Requested USD notional per proposal when no per-candidate size is set.
    min_confidence:
        Candidates below this threshold are silently filtered before proposals
        are created.  Defaults to ``0.25`` (same as strategy registry default).
    """

    strategy_id: str = "strategy_bot/v1"
    source_agent: str = "strategy_bot"
    default_size_usd: float = 50.0
    min_confidence: float = 0.25

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def scan(self, universe: list[str]) -> list[StrategyScanResult]:
        """Score every symbol in *universe* and return candidates.

        Return either scored candidates or fully-formed trade proposals.
        Strategies that need multi-leg execution plans can emit proposals
        directly and still inherit the shared policy and execution pipeline.
        """

    # ------------------------------------------------------------------
    # Optional hooks (override for custom behaviour)
    # ------------------------------------------------------------------

    def size_for_candidate(self, candidate: ScoredCandidate) -> float:
        """Return the requested USD size for a given candidate.

        Default: ``default_size_usd``.  Override to scale size by confidence
        or portfolio state.
        """
        return self.default_size_usd

    def timeframe_for_candidate(self, candidate: ScoredCandidate) -> str | None:
        """Return a timeframe hint for a candidate (e.g. ``"4h"``).

        Default: ``None`` (no hint).
        """
        return None

    def should_require_approval(self, candidate: ScoredCandidate) -> bool | None:
        """Return ``True`` to force operator approval, ``False`` to bypass
        the env-var gate, or ``None`` to defer to ``HERMES_REQUIRE_APPROVAL``.

        Default: ``None`` (defer to env).
        """
        return None

    def prepare_proposal(
        self,
        proposal: TradeProposal,
        *,
        started_at: str,
        dry_run: bool,
        extra_metadata: dict[str, Any] | None,
    ) -> TradeProposal:
        """Normalize a directly emitted proposal with runner metadata."""
        return proposal.model_copy(
            update={
                "source_agent": proposal.source_agent or self.source_agent,
                "strategy_id": proposal.strategy_id or self.strategy_id,
                "metadata": {
                    **proposal.metadata,
                    "bot_runner": self.__class__.__name__,
                    "strategy_id": proposal.strategy_id or self.strategy_id,
                    "cycle_started_at": started_at,
                    "dry_run": dry_run,
                    **(extra_metadata or {}),
                },
            }
        )

    # ------------------------------------------------------------------
    # Cycle execution
    # ------------------------------------------------------------------

    def run_cycle(
        self,
        universe: list[str],
        *,
        dry_run: bool = False,
        extra_metadata: dict[str, Any] | None = None,
    ) -> list[ExecutionDispatchResult]:
        """Run one full scan-and-propose cycle.

        Parameters
        ----------
        universe:
            Symbols to scan (e.g. ``["BTC", "ETH", "SOL"]``).
        dry_run:
            If ``True``, proposals are evaluated (risk + policy) but the
            final ``execution_requested`` event is NOT published.  Useful
            for back-testing or operator previews.
        extra_metadata:
            Additional fields merged into each proposal's ``metadata``.

        Returns
        -------
        list[ExecutionDispatchResult]:
            One entry per submitted proposal (filtered candidates only).
        """
        from backend.trading.execution_service import dispatch_trade_proposal

        started_at = datetime.now(timezone.utc).isoformat()
        logger.info(
            "bot_runner: cycle start strategy_id=%s universe=%s dry_run=%s",
            self.strategy_id,
            universe,
            dry_run,
        )

        scan_results = self.scan(universe)
        proposals: list[tuple[TradeProposal, ScoredCandidate | None]] = []
        candidate_count = 0

        for item in scan_results:
            if isinstance(item, TradeProposal):
                proposals.append(
                    (
                        self.prepare_proposal(
                            item,
                            started_at=started_at,
                            dry_run=dry_run,
                            extra_metadata=extra_metadata,
                        ),
                        None,
                    )
                )
                continue

            candidate_count += 1
            if item.direction == "watch" or item.confidence < self.min_confidence:
                continue

            proposals.append(
                (
                    proposal_from_candidate(
                        item,
                        size_usd=self.size_for_candidate(item),
                        source_agent=self.source_agent,
                        strategy_id=self.strategy_id,
                        timeframe=self.timeframe_for_candidate(item),
                        require_operator_approval=self.should_require_approval(item),
                        metadata={
                            "bot_runner": self.__class__.__name__,
                            "strategy_id": self.strategy_id,
                            "cycle_started_at": started_at,
                            "dry_run": dry_run,
                            **(extra_metadata or {}),
                        },
                    ),
                    item,
                )
            )

        logger.info(
            "bot_runner: scanned %d symbols → %d candidates → %d proposals (confidence≥%.2f)",
            len(universe),
            candidate_count,
            len(proposals),
            self.min_confidence,
        )

        if not dry_run:
            _persist_strategy_scan_artifacts(proposals)

        results: list[ExecutionDispatchResult] = []
        for proposal, _candidate in proposals:
            try:
                if dry_run:
                    from backend.trading.policy_engine import evaluate_trade_proposal

                    decision = evaluate_trade_proposal(proposal)
                    logger.info(
                        "bot_runner: dry_run proposal_id=%s symbol=%s status=%s",
                        proposal.proposal_id,
                        proposal.symbol,
                        decision.status,
                    )
                    # Synthesize a blocked dispatch result so callers can
                    # inspect the policy decision without side effects.
                    results.append(
                        ExecutionDispatchResult(
                            proposal_id=proposal.proposal_id,
                            status="blocked",
                            execution_mode=decision.execution_mode,
                            correlation_id=proposal.proposal_id,
                            workflow_id=f"dry_run::{proposal.proposal_id}",
                            approval_required=decision.requires_operator_approval,
                            policy_decision=decision,
                            dispatch_payload=_stub_execution_request(proposal, decision),
                            warnings=["dry_run=true — no event published"] + decision.warnings,
                        )
                    )
                else:
                    result = dispatch_trade_proposal(proposal)
                    logger.info(
                        "bot_runner: dispatched proposal_id=%s symbol=%s status=%s mode=%s",
                        result.proposal_id,
                        proposal.symbol,
                        result.status,
                        result.execution_mode,
                    )
                    results.append(result)

            except Exception as exc:
                logger.exception(
                    "bot_runner: error processing proposal symbol=%s proposal_id=%s: %s",
                    proposal.symbol,
                    proposal.proposal_id,
                    exc,
                )

        logger.info(
            "bot_runner: cycle complete strategy_id=%s submitted=%d",
            self.strategy_id,
            len(results),
        )
        return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _stub_execution_request(
    proposal: TradeProposal,
    decision: Any,
) -> Any:
    """Build a minimal ExecutionRequest for dry-run dispatch results."""
    from backend.trading.models import ExecutionRequest

    return ExecutionRequest(
        proposal_id=proposal.proposal_id,
        symbol=proposal.symbol,
        side=proposal.side,
        order_type=proposal.order_type,
        size_usd=decision.approved_size_usd or proposal.requested_size_usd,
        amount=decision.approved_size_usd or proposal.requested_size_usd,
        rationale=proposal.rationale,
        strategy_id=proposal.strategy_id,
        strategy_template_id=proposal.strategy_template_id,
        timeframe=proposal.timeframe,
        leverage=proposal.leverage,
        margin_mode=proposal.margin_mode,
        stop_loss_price=proposal.stop_loss_price,
        take_profit_price=proposal.take_profit_price,
        source_agent=proposal.source_agent,
        policy_trace=decision.policy_trace,
        metadata={**proposal.metadata, "dry_run": True},
    )


def _parse_signal_time(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value).astimezone(timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)
