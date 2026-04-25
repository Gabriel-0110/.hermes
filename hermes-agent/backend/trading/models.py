"""Typed schemas for the existing proposal-driven trading control path."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.models import PortfolioState


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_proposal_id() -> str:
    return f"proposal_{uuid4().hex[:16]}"


def _new_execution_request_id() -> str:
    return f"exec_req_{uuid4().hex[:16]}"


def _new_leg_id() -> str:
    return f"leg_{uuid4().hex[:12]}"


class TradeProposalLeg(BaseModel):
    """Single execution leg contained within a paired proposal."""

    model_config = ConfigDict(extra="forbid")

    leg_id: str = Field(default_factory=_new_leg_id)
    symbol: str = Field(min_length=3, max_length=32)
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"] = "market"
    requested_size_usd: float = Field(gt=0)
    amount: float | None = Field(default=None, gt=0)
    limit_price: float | None = Field(default=None, gt=0)
    venue: str = Field(default="bitmart", min_length=2, max_length=32)
    account_type: Literal["spot", "swap", "futures", "contract"] = "spot"
    leverage: float | None = Field(default=None, gt=0)
    margin_mode: Literal["cross", "isolated"] | None = None
    reduce_only: bool = False
    position_side: Literal["long", "short"] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def _validate_leg(self) -> "TradeProposalLeg":
        if self.order_type == "limit" and self.limit_price is None:
            raise ValueError("limit_price is required for limit legs")
        return self


class ExecutionRequestLeg(BaseModel):
    """Single execution leg carried through the execution worker."""

    model_config = ConfigDict(extra="forbid")

    leg_id: str = Field(default_factory=_new_leg_id)
    symbol: str = Field(min_length=3, max_length=32)
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit", "stop", "stop_limit"] = "market"
    size_usd: float | None = Field(default=None, ge=0)
    amount: float | None = Field(default=None, ge=0)
    price: float | None = Field(default=None, gt=0)
    client_order_id: str | None = Field(default=None, min_length=1, max_length=64)
    venue: str = Field(default="bitmart", min_length=2, max_length=32)
    account_type: Literal["spot", "swap", "futures", "contract"] = "spot"
    leverage: float | None = Field(default=None, gt=0)
    margin_mode: Literal["cross", "isolated"] | None = None
    reduce_only: bool = False
    position_side: Literal["long", "short"] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def _validate_leg(self) -> "ExecutionRequestLeg":
        if self.order_type in {"limit", "stop", "stop_limit"} and self.price is None:
            raise ValueError("price is required for limit and stop-style execution legs")
        if self.amount is None and self.size_usd is None:
            raise ValueError("each execution leg must define amount or size_usd")
        return self


class TradeProposal(BaseModel):
    """A bounded execution proposal created by an agent or operator."""

    model_config = ConfigDict(extra="forbid")

    proposal_id: str = Field(default_factory=_new_proposal_id)
    created_at: str = Field(default_factory=_utcnow_iso)
    source_agent: str = Field(default="orchestrator_trader", min_length=2, max_length=120)
    execution_style: Literal["single", "paired"] = "single"
    symbol: str = Field(min_length=3, max_length=32)
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"] = "market"
    requested_size_usd: float = Field(gt=0)
    rationale: str = Field(min_length=8, max_length=4000)
    strategy_id: str | None = Field(default=None, max_length=160)
    strategy_template_id: str | None = Field(default=None, max_length=160)
    timeframe: str | None = Field(default=None, max_length=32)
    limit_price: float | None = Field(default=None, gt=0)
    leverage: float | None = Field(default=None, gt=0)
    margin_mode: Literal["cross", "isolated"] | None = None
    stop_loss_price: float | None = Field(default=None, gt=0)
    take_profit_price: float | None = Field(default=None, gt=0)
    require_operator_approval: bool | None = None
    legs: list[TradeProposalLeg] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def _validate_execution_style(self) -> "TradeProposal":
        if self.legs and self.execution_style == "single":
            self.execution_style = "paired"
        if self.execution_style == "paired" and len(self.legs) < 2:
            raise ValueError("paired trade proposals must include at least two legs")
        return self


class RiskRejectionReason(StrEnum):
    """Normalized rejection reasons used by policy and execution gates."""

    KILL_SWITCH_ACTIVE = "kill_switch_active"
    LIVE_TRADING_DISABLED = "live_trading_disabled"
    RISK_APPROVAL_REJECTED = "risk_approval_rejected"
    APPROVAL_REQUIRED = "approval_required"
    MALFORMED_REQUEST = "malformed_request"
    EXCHANGE_NOT_CONFIGURED = "exchange_not_configured"
    EXECUTION_FAILED = "execution_failed"
    DRAWDOWN_LIMIT_BREACHED = "drawdown_limit_breached"
    POSITION_LIMIT_EXCEEDED = "position_limit_exceeded"
    LEVERAGE_LIMIT_EXCEEDED = "leverage_limit_exceeded"


class PolicyDecision(BaseModel):
    """Combined policy and risk decision for a validated trade proposal."""

    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    evaluated_at: str = Field(default_factory=_utcnow_iso)
    status: Literal["approved", "rejected", "manual_review"]
    execution_mode: Literal["paper", "live"]
    approved: bool
    approved_size_usd: float | None = Field(default=None, ge=0)
    requires_operator_approval: bool = False
    live_trading_blockers: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    risk_confidence: float | None = Field(default=None, ge=0, le=1)
    stop_guidance: str | None = None
    policy_trace: list[str] = Field(default_factory=list)
    raw_risk_payload: dict[str, Any] = Field(default_factory=dict)
    rejection_reasons: list[RiskRejectionReason] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_status(self) -> "PolicyDecision":
        if self.status == "rejected" and self.approved:
            raise ValueError("Rejected policy decisions cannot be approved")
        if self.status == "approved" and not self.approved:
            raise ValueError("Approved policy decisions must set approved=true")
        return self


TradePolicyDecision = PolicyDecision


class ExecutionRequest(BaseModel):
    """Normalized execution payload carried through approvals and workers."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(default_factory=_new_execution_request_id, max_length=64)
    proposal_id: str | None = None
    execution_style: Literal["single", "paired"] = "single"
    symbol: str = Field(min_length=3, max_length=32)
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit", "stop", "stop_limit"] = "market"
    size_usd: float | None = Field(default=None, ge=0)
    amount: float | None = Field(default=None, ge=0)
    price: float | None = Field(default=None, gt=0)
    client_order_id: str | None = Field(default=None, min_length=1, max_length=64)
    reduce_only: bool = False
    position_side: Literal["long", "short"] | None = None
    rationale: str | None = Field(default=None, max_length=4000)
    strategy_id: str | None = Field(default=None, max_length=160)
    strategy_template_id: str | None = Field(default=None, max_length=160)
    timeframe: str | None = Field(default=None, max_length=32)
    leverage: float | None = Field(default=None, gt=0)
    margin_mode: Literal["cross", "isolated"] | None = None
    stop_loss_price: float | None = Field(default=None, gt=0)
    take_profit_price: float | None = Field(default=None, gt=0)
    stop_guidance: str | None = Field(default=None, max_length=2000)
    source_agent: str | None = Field(default=None, min_length=2, max_length=120)
    policy_trace: list[str] = Field(default_factory=list)
    approval_id: str | None = Field(default=None, max_length=64)
    approved_by: str | None = Field(default=None, max_length=120)
    idempotency_key: str | None = Field(default=None, max_length=160)
    legs: list[ExecutionRequestLeg] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def _normalize_request_symbol(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def _validate_request(self) -> "ExecutionRequest":
        if self.legs and self.execution_style == "single":
            self.execution_style = "paired"
        if self.execution_style == "paired" and len(self.legs) < 2:
            raise ValueError("paired execution requests must include at least two legs")
        if self.order_type in {"limit", "stop", "stop_limit"} and self.price is None:
            raise ValueError("price is required for limit and stop-style orders")
        if self.amount is None and self.size_usd is None:
            raise ValueError("either amount or size_usd must be provided")
        if self.idempotency_key is None:
            stable_parts = [
                self.proposal_id or "",
                self.request_id,
                self.client_order_id or "",
                self.symbol,
                self.side,
                self.order_type,
                "reduce-only" if self.reduce_only else "",
                self.position_side or "",
                f"leverage={self.leverage}" if self.leverage is not None else "",
                f"margin={self.margin_mode}" if self.margin_mode else "",
                f"stop_loss={self.stop_loss_price}" if self.stop_loss_price is not None else "",
                f"take_profit={self.take_profit_price}" if self.take_profit_price is not None else "",
            ]
            if self.legs:
                stable_parts.append("paired")
                stable_parts.extend(
                    ":".join(
                        part
                        for part in (
                            leg.venue,
                            leg.account_type,
                            leg.symbol,
                            leg.side,
                            leg.order_type,
                            f"leverage={leg.leverage}" if leg.leverage is not None else "",
                            f"margin={leg.margin_mode}" if leg.margin_mode else "",
                        )
                        if part
                    )
                    for leg in self.legs
                )
            self.idempotency_key = ":".join(part for part in stable_parts if part)
        return self


class ExecutionResult(BaseModel):
    """Normalized result of an execution attempt in the current runtime path."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=3, max_length=32)
    order_id: str | None = Field(default=None, max_length=160)
    status: Literal["paper_filled", "filled", "failed", "blocked"]
    success: bool
    execution_mode: Literal["paper", "live"]
    reason: RiskRejectionReason | None = None
    error_message: str | None = Field(default=None, max_length=2000)
    correlation_id: str | None = Field(default=None, max_length=120)
    workflow_id: str | None = Field(default=None, max_length=120)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def _normalize_result_symbol(cls, value: str) -> str:
        return value.upper()

    @classmethod
    def blocked(
        cls,
        *,
        symbol: str,
        execution_mode: Literal["paper", "live"],
        reason: RiskRejectionReason,
        correlation_id: str | None = None,
        workflow_id: str | None = None,
        error_message: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> "ExecutionResult":
        return cls(
            symbol=symbol,
            order_id=None,
            status="blocked",
            success=False,
            execution_mode=execution_mode,
            reason=reason,
            error_message=error_message,
            correlation_id=correlation_id,
            workflow_id=workflow_id,
            payload=payload or {},
        )

    @classmethod
    def success_result(
        cls,
        *,
        symbol: str,
        order_id: str | None,
        execution_mode: Literal["paper", "live"],
        correlation_id: str | None = None,
        workflow_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> "ExecutionResult":
        return cls(
            symbol=symbol,
            order_id=order_id,
            status="paper_filled" if execution_mode == "paper" else "filled",
            success=True,
            execution_mode=execution_mode,
            correlation_id=correlation_id,
            workflow_id=workflow_id,
            payload=payload or {},
        )

    @classmethod
    def failed(
        cls,
        *,
        symbol: str,
        execution_mode: Literal["live"],
        correlation_id: str | None = None,
        workflow_id: str | None = None,
        error_message: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> "ExecutionResult":
        return cls(
            symbol=symbol,
            order_id=None,
            status="failed",
            success=False,
            execution_mode=execution_mode,
            reason=RiskRejectionReason.EXECUTION_FAILED,
            error_message=error_message,
            correlation_id=correlation_id,
            workflow_id=workflow_id,
            payload=payload or {},
        )


class ExecutionOutcome(BaseModel):
    """Traceable pairing of a normalized request and its normalized outcome."""

    model_config = ConfigDict(extra="forbid")

    request: ExecutionRequest
    result: ExecutionResult

    @classmethod
    def from_result(cls, request: ExecutionRequest, result: ExecutionResult) -> "ExecutionOutcome":
        return cls(request=request, result=result)


class ExecutionDispatchResult(BaseModel):
    """Result of dispatching a proposal into the existing execution pipeline."""

    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    dispatched_at: str = Field(default_factory=_utcnow_iso)
    status: Literal["queued", "blocked", "manual_review"]
    execution_mode: Literal["paper", "live"]
    event_type: str = "execution_requested"
    correlation_id: str
    workflow_id: str
    approval_required: bool = False
    policy_decision: PolicyDecision
    dispatch_payload: ExecutionRequest
    warnings: list[str] = Field(default_factory=list)


class PositionRiskSummary(BaseModel):
    """Compact portfolio risk summary derived from the canonical portfolio state."""

    model_config = ConfigDict(extra="forbid")

    total_positions: int = 0
    largest_position_symbol: str | None = None
    largest_position_notional_usd: float | None = None
    largest_position_weight: float | None = Field(default=None, ge=0)
    cash_buffer_pct: float | None = None
    gross_exposure_pct: float | None = None
    warnings: list[str] = Field(default_factory=list)


class PositionStateLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    quantity: float
    mark_price: float | None = None
    notional_usd: float | None = None
    state: Literal["open", "closed"] = "open"
    exposure_side: Literal["long", "short", "flat", "unknown"] = "unknown"
    last_update_source: Literal["persisted_snapshot", "live_sync", "execution_projection"] = "persisted_snapshot"
    execution_mode: Literal["paper", "live", "unknown"] = "unknown"
    updated_at: str | None = None
    last_request_id: str | None = None
    last_correlation_id: str | None = None


class PositionMonitorExecutionContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str
    status: str | None = None
    execution_mode: Literal["paper", "live", "unknown"] = "unknown"
    symbol: str | None = None
    request_id: str | None = None
    idempotency_key: str | None = None
    correlation_id: str | None = None
    workflow_id: str | None = None
    observed_at: str | None = None


class PositionMonitorSnapshot(BaseModel):
    """Current monitoring snapshot built on top of the canonical portfolio service."""

    model_config = ConfigDict(extra="forbid")

    account_id: str
    observed_at: str = Field(default_factory=_utcnow_iso)
    portfolio: PortfolioState
    risk_summary: PositionRiskSummary
    position_states: list[PositionStateLine] = Field(default_factory=list)
    snapshot_metadata: dict[str, Any] = Field(default_factory=dict)
    state_mode: Literal["paper", "live", "unknown"] = "unknown"
    last_execution: PositionMonitorExecutionContext | None = None
    source: Literal["persisted_snapshot", "live_sync"] = "persisted_snapshot"
