"""Backend tool: run a named strategy bot cycle.

This is the bridge between the cron/agent layer and the autonomous strategy
runner infrastructure.  An agent (or a cron job prompt) calls this tool with
a strategy name and a universe of symbols; the tool instantiates the
corresponding ``StrategyBotRunner``, runs one scan-and-propose cycle, and
returns a structured summary of each proposal's dispatch outcome.

All risk gating, approval routing, kill-switch enforcement, paper/live mode
selection, and observability happen inside the existing pipeline — this tool
is purely an entry point.

Usage from an agent tool call::

    run_strategy_cycle({
        "strategy": "momentum",
        "universe": ["BTC", "ETH", "SOL"],
        "dry_run": false
    })

Cron scheduling example (via ``hermes cron add``)::

    prompt: >
      Run the momentum strategy cycle for BTC, ETH, SOL.
      Use the run_strategy_cycle tool with strategy=momentum and
      universe=["BTC","ETH","SOL"].
    schedule: every 4h
    deliver: origin
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from backend.tools._helpers import envelope, run_tool, validate

logger = logging.getLogger(__name__)


class RunStrategyCycleInput(BaseModel):
    strategy: str = Field(
        min_length=2,
        max_length=64,
        description="Name of the strategy runner (e.g. 'momentum', 'mean_reversion', 'breakout').",
    )
    universe: list[str] = Field(
        min_length=1,
        max_length=60,
        description="Symbols to scan (e.g. ['BTC', 'ETH', 'SOL']). Supports larger scheduled top-alt universes.",
    )
    dry_run: bool = Field(
        default=False,
        description=(
            "When true, proposals are risk-evaluated but the execution event is NOT published. "
            "Use for previewing what the bot would do without side effects."
        ),
    )
    size_usd: float | None = Field(
        default=None,
        gt=0,
        description="Override the runner's default position size (USD) for every proposal.",
    )
    min_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Override the runner's minimum confidence threshold.",
    )


def run_strategy_cycle(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run one scan-and-propose cycle for a named strategy bot runner.

    Returns a summary of each proposal's dispatch outcome including mode,
    status, and any policy warnings.
    """

    def _run() -> dict[str, Any]:
        args = validate(RunStrategyCycleInput, payload or {})

        from backend.strategies.runners import BOT_RUNNER_REGISTRY

        strategy_name = args.strategy.lower().strip()
        if strategy_name not in BOT_RUNNER_REGISTRY:
            available = ", ".join(sorted(BOT_RUNNER_REGISTRY.keys()))
            raise ValueError(
                f"Unknown strategy runner: {strategy_name!r}. "
                f"Available runners: {available}"
            )

        RunnerCls = BOT_RUNNER_REGISTRY[strategy_name]
        runner = RunnerCls()

        # Apply optional per-call overrides
        if args.size_usd is not None:
            runner.default_size_usd = args.size_usd
        if args.min_confidence is not None:
            runner.min_confidence = args.min_confidence

        universe = [s.upper().strip() for s in args.universe]

        logger.info(
            "run_strategy_cycle: strategy=%s universe=%s dry_run=%s",
            strategy_name,
            universe,
            args.dry_run,
        )

        results = runner.run_cycle(universe, dry_run=args.dry_run)

        outcome_summaries = [
            {
                "proposal_id": r.proposal_id,
                "status": r.status,
                "execution_mode": r.execution_mode,
                "approval_required": r.approval_required,
                "symbol": r.dispatch_payload.symbol,
                "side": r.dispatch_payload.side,
                "size_usd": r.dispatch_payload.size_usd,
                "policy_status": r.policy_decision.status,
                "blocking_reasons": r.policy_decision.blocking_reasons,
                "warnings": r.warnings,
            }
            for r in results
        ]

        summary = {
            "strategy": strategy_name,
            "universe": universe,
            "dry_run": args.dry_run,
            "proposals_submitted": len(results),
            "outcomes": outcome_summaries,
        }

        logger.info(
            "run_strategy_cycle: complete strategy=%s submitted=%d dry_run=%s",
            strategy_name,
            len(results),
            args.dry_run,
        )

        return envelope("run_strategy_cycle", [], summary)

    return run_tool("run_strategy_cycle", _run)
