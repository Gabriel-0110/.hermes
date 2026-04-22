"""Typed models for the Hermes trading workflow graph."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_workflow_id() -> str:
    return f"wf_{uuid4().hex[:16]}"


class TradingBranchDecision(StrEnum):
    REJECT = "reject"
    CONTINUE = "continue"
    EXECUTE = "execute"


class WorkflowStage(StrEnum):
    INGEST_SIGNAL = "ingest_signal"
    MARKET_RESEARCH = "market_research"
    STRATEGY_PLANNING = "strategy_planning"
    RISK_REVIEW = "risk_review"
    FINAL_ORCHESTRATION_DECISION = "final_orchestration_decision"
    COMPLETED = "completed"


class EvidenceItem(BaseModel):
    source: str
    summary: str
    tool_name: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class TradingInputEvent(BaseModel):
    """Normalized workflow input event for the trading pipeline."""

    model_config = ConfigDict(extra="allow")

    workflow_id: str = Field(default_factory=_new_workflow_id)
    event_id: str = Field(default_factory=lambda: f"evt_{uuid4().hex[:16]}")
    event_type: str = "tradingview_signal_ready"
    source: str = "tradingview"
    received_at: datetime = Field(default_factory=_utcnow)
    symbol: str | None = None
    timeframe: str | None = None
    strategy: str | None = None
    signal: str | None = None
    direction: str | None = None
    price: float | None = None
    alert_id: str | None = None
    correlation_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str | None) -> str | None:
        return value.upper() if value else value

    @classmethod
    def from_tradingview_alert(cls, alert: Any) -> "TradingInputEvent":
        return cls(
            alert_id=getattr(alert, "id", None),
            source=getattr(alert, "source", "tradingview"),
            received_at=_utcnow(),
            symbol=getattr(alert, "symbol", None),
            timeframe=getattr(alert, "timeframe", None),
            strategy=getattr(alert, "strategy", None),
            signal=getattr(alert, "signal", None),
            direction=getattr(alert, "direction", None),
            price=getattr(alert, "price", None),
            payload=getattr(alert, "payload", {}) or {},
        )

    @classmethod
    def from_stream_event(cls, envelope: Any) -> "TradingInputEvent":
        event = envelope.event if hasattr(envelope, "event") else envelope
        return cls(
            workflow_id=getattr(event, "workflow_id", None) or _new_workflow_id(),
            event_id=getattr(event, "event_id", f"evt_{uuid4().hex[:16]}"),
            event_type=getattr(event, "event_type", "tradingview_signal_ready"),
            source=getattr(event, "source", "tradingview"),
            received_at=_utcnow(),
            symbol=getattr(event, "symbol", None),
            alert_id=getattr(event, "alert_id", None),
            correlation_id=getattr(event, "correlation_id", None),
            payload=getattr(event, "payload", {}) or {},
            metadata=getattr(event, "metadata", {}) or {},
        )


class ResearcherOutput(BaseModel):
    decision: TradingBranchDecision = TradingBranchDecision.CONTINUE
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    summary: str
    market_regime: str = "unknown"
    risk_bias: str = "unknown"
    volatility_regime: str = "unknown"
    catalysts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    raw_context: dict[str, Any] = Field(default_factory=dict)


class StrategyOutput(BaseModel):
    decision: TradingBranchDecision = TradingBranchDecision.CONTINUE
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    strategy_name: str
    action: str
    thesis: str
    timeframe: str | None = None
    proposed_size_usd: float | None = None
    entry_plan: str | None = None
    invalidation: str | None = None
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RiskOutput(BaseModel):
    decision: TradingBranchDecision = TradingBranchDecision.CONTINUE
    approved: bool = False
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    summary: str
    max_size_usd: float | None = None
    risk_score: float = Field(default=0.5, ge=0.0, le=1.0)
    blocking_reasons: list[str] = Field(default_factory=list)
    required_actions: list[str] = Field(default_factory=list)
    stop_guidance: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ExecutionIntent(BaseModel):
    symbol: str
    action: str
    size_usd: float | None = None
    timeframe: str | None = None
    stop_guidance: str | None = None
    rationale: str


class OrchestratorOutput(BaseModel):
    decision: TradingBranchDecision
    status: str
    summary: str
    should_execute: bool = False
    execution_intent: ExecutionIntent | None = None
    notifications: list[str] = Field(default_factory=list)
    audit: dict[str, Any] = Field(default_factory=dict)


class TradingWorkflowState(BaseModel):
    workflow_id: str
    current_stage: WorkflowStage = WorkflowStage.INGEST_SIGNAL
    input_event: TradingInputEvent
    research_output: ResearcherOutput | None = None
    strategy_output: StrategyOutput | None = None
    risk_output: RiskOutput | None = None
    orchestrator_output: OrchestratorOutput | None = None
    branch_history: list[TradingBranchDecision] = Field(default_factory=list)
    execution_trace: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    extension_points: dict[str, Any] = Field(
        default_factory=lambda: {
            "durable_runtime": None,
            "prefect_flow_name": None,
            "temporal_workflow": None,
            "dbos_workflow": None,
            "resume_token": None,
        }
    )

    @classmethod
    def from_event(cls, event: TradingInputEvent) -> "TradingWorkflowState":
        return cls(workflow_id=event.workflow_id, input_event=event)
