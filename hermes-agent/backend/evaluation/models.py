"""Typed models for replay, evaluation, and regression workflows."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from backend.workflows.models import TradingInputEvent, TradingWorkflowState


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


class ReplaySourceType(StrEnum):
    TRADINGVIEW_ALERT = "tradingview_alert"


class ReplayRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ComparisonDimension(StrEnum):
    MODEL = "model"
    PROMPT = "prompt"
    WORKFLOW = "workflow"


class ReplayCase(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: _new_id("replay_case"))
    created_at: datetime = Field(default_factory=_utcnow)
    source_type: ReplaySourceType = ReplaySourceType.TRADINGVIEW_ALERT
    source_event_id: str | None = None
    source_correlation_id: str | None = None
    source_alert_id: str | None = None
    label: str | None = None
    input_event: Any
    source_payload: dict[str, Any] = Field(default_factory=dict)
    expected_outcome: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReplayRunConfig(BaseModel):
    workflow_name: str = "trading_workflow_graph"
    workflow_version: str = "v1"
    model_name: str | None = None
    prompt_version: str | None = None
    mode: str = "replay"
    allow_live_execution: bool = False
    allow_live_notifications: bool = False
    notification_test_sink: str | None = "log"
    persist_observability: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReplayRunRecord(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("replay_run"))
    created_at: datetime = Field(default_factory=_utcnow)
    replay_case_id: str
    workflow_run_id: str | None = None
    workflow_name: str
    workflow_version: str | None = None
    model_name: str | None = None
    prompt_version: str | None = None
    source_event_id: str | None = None
    source_correlation_id: str | None = None
    mode: str = "replay"
    status: ReplayRunStatus = ReplayRunStatus.PENDING
    configuration: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReplayResultRecord(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("replay_result"))
    created_at: datetime = Field(default_factory=_utcnow)
    replay_run_id: str
    replay_case_id: str
    workflow_run_id: str | None = None
    source_event_id: str | None = None
    source_correlation_id: str | None = None
    decision: str | None = None
    status: str | None = None
    should_execute: bool = False
    execution_intent: dict[str, Any] = Field(default_factory=dict)
    notifications: list[Any] = Field(default_factory=list)
    output: dict[str, Any] = Field(default_factory=dict)
    state: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationRuleConfig(BaseModel):
    approved_vs_rejected_expected: str | None = None
    execution_expected: bool | None = None
    forward_return_horizon_bars: int | None = 1
    min_forward_return: float | None = None
    max_latency_ms: float | None = None
    require_risk_compliance: bool = True


class EvaluationScoreRecord(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("eval_score"))
    created_at: datetime = Field(default_factory=_utcnow)
    replay_run_id: str
    replay_result_id: str
    replay_case_id: str
    rule_name: str
    metric_name: str
    value: float
    passed: bool
    detail: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RegressionComparisonRecord(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("regression"))
    created_at: datetime = Field(default_factory=_utcnow)
    baseline_replay_run_id: str
    candidate_replay_run_id: str
    comparison_type: ComparisonDimension
    baseline_label: str | None = None
    candidate_label: str | None = None
    status: str = "completed"
    summary: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReplayExecutionArtifacts(BaseModel):
    replay_run: ReplayRunRecord
    replay_result: ReplayResultRecord
    evaluation_scores: list[EvaluationScoreRecord] = Field(default_factory=list)


class ReplayWorkflowExecution(BaseModel):
    state: Any
    output: dict[str, Any]
    workflow_run_id: str
    correlation_id: str
    latency_ms: float
