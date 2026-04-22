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
)

logger = logging.getLogger(__name__)

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
        metadata=metadata or {},
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
    def scan(self, universe: list[str]) -> list[ScoredCandidate]:
        """Score every symbol in *universe* and return candidates.

        Return all candidates including low-confidence ones — the runner
        filters by ``min_confidence`` before creating proposals.
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

        candidates = self.scan(universe)
        actionable = [
            c for c in candidates
            if c.direction != "watch" and c.confidence >= self.min_confidence
        ]

        logger.info(
            "bot_runner: scanned %d symbols → %d actionable candidates (confidence≥%.2f)",
            len(universe),
            len(actionable),
            self.min_confidence,
        )

        results: list[ExecutionDispatchResult] = []
        for candidate in actionable:
            try:
                proposal = proposal_from_candidate(
                    candidate,
                    size_usd=self.size_for_candidate(candidate),
                    source_agent=self.source_agent,
                    strategy_id=self.strategy_id,
                    timeframe=self.timeframe_for_candidate(candidate),
                    require_operator_approval=self.should_require_approval(candidate),
                    metadata={
                        "bot_runner": self.__class__.__name__,
                        "strategy_id": self.strategy_id,
                        "cycle_started_at": started_at,
                        "dry_run": dry_run,
                        **(extra_metadata or {}),
                    },
                )

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
                    "bot_runner: error processing candidate symbol=%s: %s",
                    candidate.symbol,
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
        source_agent=proposal.source_agent,
        policy_trace=decision.policy_trace,
        metadata={**proposal.metadata, "dry_run": True},
    )
