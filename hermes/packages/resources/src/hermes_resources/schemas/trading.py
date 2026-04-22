"""Core trading domain models shared across agents, APIs, and adapters.

These models define the canonical language for proposing, validating,
executing, and monitoring trades. They are intentionally serialization-friendly
so the same payloads can move through API routes, message buses, and database
records without lossy translation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _utcnow() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


def _new_trace_id(prefix: str) -> str:
    """Return a short stable identifier for cross-system correlation."""
    return f"{prefix}_{uuid4().hex[:16]}"


class TradeMode(StrEnum):
    """Operator control mode for how a trade may be handled."""

    MANUAL = "manual"
    SEMI_AUTO = "semi_auto"
    FULL_AUTO = "full_auto"
    PAPER = "paper"
    SHADOW_LIVE = "shadow_live"
    LIVE = "live"


class MarketType(StrEnum):
    """Normalized market venue type."""

    SPOT = "spot"
    FUTURES = "futures"


class OrderSide(StrEnum):
    """Normalized order direction."""

    BUY = "buy"
    SELL = "sell"


class PositionSide(StrEnum):
    """Normalized exposure direction after execution."""

    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


class EntryLogicType(StrEnum):
    """How the entry condition should be interpreted by downstream systems."""

    MARKET = "market"
    LIMIT = "limit"
    BREAKOUT = "breakout"
    PULLBACK = "pullback"
    TWAP = "twap"
    VWAP = "vwap"


class RiskDecisionStatus(StrEnum):
    """Normalized outcome from the risk engine."""

    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"
    RESIZED = "resized"


class TradeLifecycleStatus(StrEnum):
    """End-to-end lifecycle states for a trade request."""

    PROPOSED = "proposed"
    VALIDATED = "validated"
    APPROVED = "approved"
    REJECTED_BY_RISK = "rejected_by_risk"
    REJECTED_BY_POLICY = "rejected_by_policy"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    PROTECTED = "protected"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class TradePolicy(BaseModel):
    """Policy constraints that bound autonomous trade behavior."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    policy_id: str = Field(default_factory=lambda: _new_trace_id("policy"))
    name: str = Field(min_length=3, max_length=120)
    trade_mode: TradeMode
    market_types: list[MarketType] = Field(default_factory=list, min_length=1)
    allow_spot: bool = True
    allow_futures: bool = False
    max_notional_usd: Decimal = Field(gt=0)
    max_leverage: Decimal = Field(default=Decimal("1"), ge=Decimal("1"))
    require_manual_approval: bool = False
    allow_live_execution: bool = False
    allow_shadow_live: bool = True
    allow_reduce_only_exits: bool = True
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _validate_market_flags(self) -> "TradePolicy":
        if MarketType.SPOT in self.market_types and not self.allow_spot:
            raise ValueError("allow_spot must be true when spot is listed in market_types")
        if MarketType.FUTURES in self.market_types and not self.allow_futures:
            raise ValueError("allow_futures must be true when futures is listed in market_types")
        if self.trade_mode is TradeMode.LIVE and not self.allow_live_execution:
            raise ValueError("LIVE trade_mode requires allow_live_execution=true")
        if self.trade_mode is TradeMode.SHADOW_LIVE and not self.allow_shadow_live:
            raise ValueError("SHADOW_LIVE trade_mode requires allow_shadow_live=true")
        if self.allow_futures and self.max_leverage < Decimal("1"):
            raise ValueError("Futures-enabled policies must have max_leverage >= 1")
        return self


class StrategySignal(BaseModel):
    """Normalized strategy output before it becomes a concrete execution intent."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    signal_id: str = Field(default_factory=lambda: _new_trace_id("signal"))
    symbol: str = Field(min_length=3, max_length=40)
    market_type: MarketType
    side: OrderSide
    strategy: str = Field(min_length=2, max_length=160)
    confidence: float = Field(ge=0.0, le=1.0)
    entry_logic: EntryLogicType
    entry_price: Decimal | None = Field(default=None, gt=0)
    stop_loss: Decimal | None = Field(default=None, gt=0)
    take_profit: Decimal | None = Field(default=None, gt=0)
    leverage: Decimal | None = Field(default=None, ge=Decimal("1"))
    notional_usd: Decimal = Field(gt=0)
    source_agent: str = Field(min_length=2, max_length=120)
    reasoning_summary: str = Field(min_length=8, max_length=4000)
    timeframe: str | None = Field(default=None, max_length=32)
    correlation_id: str = Field(default_factory=lambda: _new_trace_id("corr"))
    trace_id: str = Field(default_factory=lambda: _new_trace_id("trace"))
    created_at: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def _validate_signal(self) -> "StrategySignal":
        if self.market_type is MarketType.SPOT and self.leverage not in (None, Decimal("1")):
            raise ValueError("Spot signals may not specify leverage other than 1")
        if self.entry_logic in {EntryLogicType.LIMIT, EntryLogicType.BREAKOUT, EntryLogicType.PULLBACK} and self.entry_price is None:
            raise ValueError("entry_price is required for non-market entry logic")
        return self


class TradeIntent(BaseModel):
    """Concrete trading intent produced by an agent or orchestration layer."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    intent_id: str = Field(default_factory=lambda: _new_trace_id("intent"))
    lifecycle_status: TradeLifecycleStatus = TradeLifecycleStatus.PROPOSED
    symbol: str = Field(min_length=3, max_length=40)
    market_type: MarketType
    side: OrderSide
    strategy: str = Field(min_length=2, max_length=160)
    confidence: float = Field(ge=0.0, le=1.0)
    entry_logic: EntryLogicType
    entry_price: Decimal | None = Field(default=None, gt=0)
    stop_loss: Decimal | None = Field(default=None, gt=0)
    take_profit: Decimal | None = Field(default=None, gt=0)
    leverage: Decimal | None = Field(default=None, ge=Decimal("1"))
    notional_usd: Decimal = Field(gt=0)
    source_agent: str = Field(min_length=2, max_length=120)
    trade_mode: TradeMode
    reasoning_summary: str = Field(min_length=8, max_length=4000)
    correlation_id: str = Field(default_factory=lambda: _new_trace_id("corr"))
    trace_id: str = Field(default_factory=lambda: _new_trace_id("trace"))
    signal_id: str | None = Field(default=None, max_length=64)
    submitted_at: datetime | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def _validate_intent(self) -> "TradeIntent":
        if self.market_type is MarketType.SPOT and self.leverage not in (None, Decimal("1")):
            raise ValueError("Spot intents may not specify leverage other than 1")
        if self.entry_logic in {EntryLogicType.LIMIT, EntryLogicType.BREAKOUT, EntryLogicType.PULLBACK} and self.entry_price is None:
            raise ValueError("entry_price is required for non-market entry logic")
        if self.stop_loss is not None and self.take_profit is not None and self.stop_loss == self.take_profit:
            raise ValueError("stop_loss and take_profit must differ")
        return self


class RiskDecision(BaseModel):
    """Canonical output of the risk module for a trade intent."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    decision_id: str = Field(default_factory=lambda: _new_trace_id("risk"))
    intent_id: str = Field(min_length=4, max_length=64)
    symbol: str = Field(min_length=3, max_length=40)
    market_type: MarketType
    status: RiskDecisionStatus
    approved: bool
    approved_notional_usd: Decimal | None = Field(default=None, ge=0)
    approved_leverage: Decimal | None = Field(default=None, ge=Decimal("1"))
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    risk_score: float | None = Field(default=None, ge=0.0, le=1.0)
    reasoning_summary: str = Field(min_length=8, max_length=4000)
    rejection_reason: str | None = Field(default=None, max_length=2000)
    required_actions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_agent: str = Field(min_length=2, max_length=120)
    correlation_id: str = Field(min_length=4, max_length=64)
    trace_id: str = Field(min_length=4, max_length=64)
    created_at: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def _validate_decision(self) -> "RiskDecision":
        if self.approved and self.status is RiskDecisionStatus.REJECTED:
            raise ValueError("approved cannot be true when status is rejected")
        if not self.approved and self.status in {RiskDecisionStatus.APPROVED, RiskDecisionStatus.RESIZED} and not self.rejection_reason:
            raise ValueError("A non-approved approval-like status requires rejection_reason for clarity")
        if self.approved and self.approved_notional_usd is None:
            raise ValueError("approved_notional_usd is required when approved is true")
        return self


class ExecutionRequest(BaseModel):
    """Request passed to an execution engine after policy and risk validation."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    request_id: str = Field(default_factory=lambda: _new_trace_id("exec_req"))
    intent_id: str = Field(min_length=4, max_length=64)
    symbol: str = Field(min_length=3, max_length=40)
    market_type: MarketType
    side: OrderSide
    strategy: str = Field(min_length=2, max_length=160)
    lifecycle_status: TradeLifecycleStatus = TradeLifecycleStatus.VALIDATED
    trade_mode: TradeMode
    notional_usd: Decimal = Field(gt=0)
    leverage: Decimal | None = Field(default=None, ge=Decimal("1"))
    entry_logic: EntryLogicType
    entry_price: Decimal | None = Field(default=None, gt=0)
    stop_loss: Decimal | None = Field(default=None, gt=0)
    take_profit: Decimal | None = Field(default=None, gt=0)
    source_agent: str = Field(min_length=2, max_length=120)
    exchange: str | None = Field(default=None, max_length=80)
    venue_account: str | None = Field(default=None, max_length=120)
    reasoning_summary: str = Field(min_length=8, max_length=4000)
    correlation_id: str = Field(min_length=4, max_length=64)
    trace_id: str = Field(min_length=4, max_length=64)
    created_at: datetime = Field(default_factory=_utcnow)
    submitted_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def _validate_request(self) -> "ExecutionRequest":
        if self.market_type is MarketType.SPOT and self.leverage not in (None, Decimal("1")):
            raise ValueError("Spot execution requests may not specify leverage other than 1")
        if self.entry_logic in {EntryLogicType.LIMIT, EntryLogicType.BREAKOUT, EntryLogicType.PULLBACK} and self.entry_price is None:
            raise ValueError("entry_price is required for non-market execution requests")
        return self


class ExecutionResult(BaseModel):
    """Normalized execution outcome from an exchange adapter or simulator."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    result_id: str = Field(default_factory=lambda: _new_trace_id("exec_res"))
    request_id: str = Field(min_length=4, max_length=64)
    intent_id: str = Field(min_length=4, max_length=64)
    symbol: str = Field(min_length=3, max_length=40)
    market_type: MarketType
    lifecycle_status: TradeLifecycleStatus
    success: bool
    exchange: str = Field(min_length=2, max_length=80)
    exchange_order_id: str | None = Field(default=None, max_length=160)
    client_order_id: str | None = Field(default=None, max_length=160)
    side: OrderSide
    requested_notional_usd: Decimal = Field(gt=0)
    filled_notional_usd: Decimal | None = Field(default=None, ge=0)
    filled_quantity: Decimal | None = Field(default=None, ge=0)
    average_fill_price: Decimal | None = Field(default=None, gt=0)
    leverage: Decimal | None = Field(default=None, ge=Decimal("1"))
    fees_usd: Decimal | None = Field(default=None, ge=0)
    error_code: str | None = Field(default=None, max_length=120)
    error_message: str | None = Field(default=None, max_length=2000)
    reasoning_summary: str | None = Field(default=None, max_length=4000)
    correlation_id: str = Field(min_length=4, max_length=64)
    trace_id: str = Field(min_length=4, max_length=64)
    submitted_at: datetime | None = None
    updated_at: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def _validate_result(self) -> "ExecutionResult":
        if self.success and self.lifecycle_status in {
            TradeLifecycleStatus.REJECTED_BY_POLICY,
            TradeLifecycleStatus.REJECTED_BY_RISK,
            TradeLifecycleStatus.FAILED,
        }:
            raise ValueError("Successful execution results cannot use rejected or failed lifecycle states")
        if not self.success and self.lifecycle_status in {
            TradeLifecycleStatus.FILLED,
            TradeLifecycleStatus.PARTIALLY_FILLED,
            TradeLifecycleStatus.PROTECTED,
            TradeLifecycleStatus.CLOSED,
        }:
            raise ValueError("Unsuccessful execution results cannot use successful fill lifecycle states")
        if self.success and self.lifecycle_status in {
            TradeLifecycleStatus.PARTIALLY_FILLED,
            TradeLifecycleStatus.FILLED,
        } and self.filled_quantity is None:
            raise ValueError("filled_quantity is required for filled execution results")
        return self


class PositionState(BaseModel):
    """Normalized open or closed position state derived from executions."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    position_id: str = Field(default_factory=lambda: _new_trace_id("pos"))
    intent_id: str | None = Field(default=None, max_length=64)
    symbol: str = Field(min_length=3, max_length=40)
    market_type: MarketType
    position_side: PositionSide
    lifecycle_status: TradeLifecycleStatus
    strategy: str = Field(min_length=2, max_length=160)
    source_agent: str = Field(min_length=2, max_length=120)
    quantity: Decimal = Field(ge=0)
    entry_price: Decimal | None = Field(default=None, gt=0)
    mark_price: Decimal | None = Field(default=None, gt=0)
    stop_loss: Decimal | None = Field(default=None, gt=0)
    take_profit: Decimal | None = Field(default=None, gt=0)
    leverage: Decimal | None = Field(default=None, ge=Decimal("1"))
    notional_usd: Decimal | None = Field(default=None, ge=0)
    unrealized_pnl_usd: Decimal | None = None
    realized_pnl_usd: Decimal | None = None
    reasoning_summary: str | None = Field(default=None, max_length=4000)
    correlation_id: str = Field(min_length=4, max_length=64)
    trace_id: str = Field(min_length=4, max_length=64)
    opened_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    closed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def _validate_position(self) -> "PositionState":
        if self.market_type is MarketType.SPOT and self.leverage not in (None, Decimal("1")):
            raise ValueError("Spot positions may not specify leverage other than 1")
        if self.position_side is PositionSide.FLAT and self.quantity != 0:
            raise ValueError("FLAT positions must have quantity=0")
        if self.position_side is not PositionSide.FLAT and self.quantity == 0:
            raise ValueError("Non-flat positions must have quantity > 0")
        if self.closed_at is not None and self.closed_at < self.opened_at:
            raise ValueError("closed_at cannot be earlier than opened_at")
        return self
