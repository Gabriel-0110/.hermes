"""Replay, evaluation, and regression support for Hermes trading workflows."""

from __future__ import annotations

from .backtest import (
    BacktestMetrics,
    BacktestTrade,
    StrategyBacktestSummary,
    format_backtest_report,
    run_strategy_backtest,
)
from .models import (
    ComparisonDimension,
    EvaluationRuleConfig,
    EvaluationScoreRecord,
    RegressionComparisonRecord,
    ReplayCase,
    ReplayExecutionArtifacts,
    ReplayResultRecord,
    ReplayRunConfig,
    ReplayRunRecord,
    ReplayRunStatus,
)
from .regression import compare_replay_runs
from .scoring import score_replay_result, summarize_scores
from .storage import ReplayStorage

__all__ = [
    "BacktestMetrics",
    "BacktestTrade",
    "ComparisonDimension",
    "EvaluationRuleConfig",
    "EvaluationScoreRecord",
    "RegressionComparisonRecord",
    "ReplayCase",
    "ReplayExecutionArtifacts",
    "ReplayResultRecord",
    "ReplayRunConfig",
    "ReplayRunRecord",
    "ReplayRunStatus",
    "StrategyBacktestSummary",
    "ReplayRunner",
    "ReplayStorage",
    "ReplayWorkflowTools",
    "compare_replay_runs",
    "format_backtest_report",
    "run_strategy_backtest",
    "score_replay_result",
    "summarize_scores",
]


def __getattr__(name: str):
    if name in {"ReplayRunner", "ReplayWorkflowTools"}:
        from .replay import ReplayRunner, ReplayWorkflowTools

        return {"ReplayRunner": ReplayRunner, "ReplayWorkflowTools": ReplayWorkflowTools}[name]
    raise AttributeError(name)
