from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TradeProposalPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_agent: str = Field(default="orchestrator_trader", min_length=2, max_length=120)
    symbol: str = Field(min_length=3, max_length=32)
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"] = "market"
    requested_size_usd: float = Field(gt=0)
    rationale: str = Field(min_length=8, max_length=4000)
    strategy_id: str | None = Field(default=None, max_length=160)
    strategy_template_id: str | None = Field(default=None, max_length=160)
    timeframe: str | None = Field(default=None, max_length=32)
    limit_price: float | None = Field(default=None, gt=0)
    stop_loss_price: float | None = Field(default=None, gt=0)
    take_profit_price: float | None = Field(default=None, gt=0)
    require_operator_approval: bool | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        return value.upper()


class BridgeExecutionSafety(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_mode: Literal["paper", "live"]
    blockers: list[str] = Field(default_factory=list)
    approval_required: bool = False
    kill_switch_active: bool = False
    kill_switch_reason: str | None = None
    live_allowed: bool = False


class BridgeExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    proposal_id: str | None = None
    symbol: str
    side: Literal["buy", "sell"]
    order_type: str
    size_usd: float | None = None
    amount: float | None = None
    price: float | None = None
    client_order_id: str | None = None
    rationale: str | None = None
    strategy_id: str | None = None
    strategy_template_id: str | None = None
    timeframe: str | None = None
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    stop_guidance: str | None = None
    source_agent: str | None = None
    policy_trace: list[str] = Field(default_factory=list)
    approval_id: str | None = None
    approved_by: str | None = None
    idempotency_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BridgeExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    order_id: str | None = None
    status: Literal["paper_filled", "filled", "failed", "blocked"]
    success: bool
    execution_mode: Literal["paper", "live"]
    reason: str | None = None
    error_message: str | None = None
    correlation_id: str | None = None
    workflow_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class BridgePolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    evaluated_at: str
    status: Literal["approved", "rejected", "manual_review"]
    execution_mode: Literal["paper", "live"]
    approved: bool
    approved_size_usd: float | None = None
    requires_operator_approval: bool = False
    live_trading_blockers: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    risk_confidence: float | None = None
    stop_guidance: str | None = None
    policy_trace: list[str] = Field(default_factory=list)
    raw_risk_payload: dict[str, Any] = Field(default_factory=dict)
    rejection_reasons: list[str] = Field(default_factory=list)


class BridgeExecutionDispatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    dispatched_at: str
    status: Literal["queued", "blocked", "manual_review"]
    execution_mode: Literal["paper", "live"]
    event_type: str = "execution_requested"
    correlation_id: str
    workflow_id: str
    approval_required: bool = False
    policy_decision: BridgePolicyDecision
    dispatch_payload: BridgeExecutionRequest
    warnings: list[str] = Field(default_factory=list)


class BridgeExecutionEvent(BaseModel):
    model_config = ConfigDict(extra="allow")


class BridgePendingSignalEvent(BaseModel):
    model_config = ConfigDict(extra="allow")


class BridgeExecutionSurface(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exchange: str
    configured: bool
    trading_mode: str
    safety: BridgeExecutionSafety
    live_trading_enabled: bool
    live_trading_blockers: list[str] = Field(default_factory=list)
    approval_required: bool = False
    kill_switch_active: bool = False
    pending_signal_events: list[BridgePendingSignalEvent] = Field(default_factory=list)
    pending_signal_count: int = 0
    recent_execution_events: list[BridgeExecutionEvent] = Field(default_factory=list)


class BridgeExecutionSurfaceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "live"
    execution: BridgeExecutionSurface


class BridgeExecutionPolicyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "live"
    policy_decision: BridgePolicyDecision


class BridgeExecutionDispatchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "live"
    dispatch: BridgeExecutionDispatch


class BridgeExecutionPlaceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "live"
    order: dict[str, Any]


class BridgeExecutionEventsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "live"
    count: int
    events: list[BridgeExecutionEvent]


class BridgePendingSignalsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "live"
    count: int
    events: list[BridgePendingSignalEvent]
