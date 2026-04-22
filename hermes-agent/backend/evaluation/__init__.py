"""Replay, evaluation, and regression support for Hermes trading workflows."""

from __future__ import annotations

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
    "ReplayRunner",
    "ReplayStorage",
    "ReplayWorkflowTools",
    "compare_replay_runs",
    "score_replay_result",
    "summarize_scores",
]


def __getattr__(name: str):
    if name in {"ReplayRunner", "ReplayWorkflowTools"}:
        from .replay import ReplayRunner, ReplayWorkflowTools

        return {"ReplayRunner": ReplayRunner, "ReplayWorkflowTools": ReplayWorkflowTools}[name]
    raise AttributeError(name)
