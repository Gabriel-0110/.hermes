"""Typed trading workflows built on PydanticAI and Pydantic Graph."""

from .deps import TradingWorkflowDeps
from .graph import build_trading_workflow_graph, run_trading_workflow, trading_workflow_graph
from .models import (
    OrchestratorOutput,
    ResearcherOutput,
    RiskOutput,
    StrategyOutput,
    TradingBranchDecision,
    TradingInputEvent,
    TradingWorkflowState,
)

__all__ = (
    "TradingWorkflowDeps",
    "TradingBranchDecision",
    "TradingInputEvent",
    "TradingWorkflowState",
    "ResearcherOutput",
    "StrategyOutput",
    "RiskOutput",
    "OrchestratorOutput",
    "build_trading_workflow_graph",
    "trading_workflow_graph",
    "run_trading_workflow",
)
