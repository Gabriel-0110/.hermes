"""Controlled trading orchestration primitives.

This package wraps the existing workflow, risk, execution, and portfolio
building blocks behind a stricter proposal -> policy -> execution ->
position-management interface.
"""

from .bot_runner import (
    StrategyBotRunner,
    paired_proposal_from_legs,
    paired_unwind_proposal,
    proposal_from_candidate,
)
from .execution_service import dispatch_trade_proposal
from .models import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionOutcome,
    ExecutionDispatchResult,
    PolicyDecision,
    PositionMonitorSnapshot,
    PositionRiskSummary,
    RiskRejectionReason,
    TradePolicyDecision,
    TradeProposal,
)
from .policy_engine import evaluate_trade_proposal, normalize_trade_proposal
from .position_manager import get_position_monitor_snapshot

__all__ = [
    "TradeProposal",
    "PolicyDecision",
    "TradePolicyDecision",
    "ExecutionRequest",
    "ExecutionResult",
    "ExecutionOutcome",
    "ExecutionDispatchResult",
    "RiskRejectionReason",
    "PositionRiskSummary",
    "PositionMonitorSnapshot",
    "normalize_trade_proposal",
    "evaluate_trade_proposal",
    "dispatch_trade_proposal",
    "get_position_monitor_snapshot",
    "StrategyBotRunner",
    "proposal_from_candidate",
    "paired_proposal_from_legs",
    "paired_unwind_proposal",
]
