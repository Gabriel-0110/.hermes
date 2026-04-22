from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class BridgePortfolioEnvelopeMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    providers: list[Any] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    ok: bool = True


class BridgePortfolioAsset(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: str
    quantity: float


class BridgePortfolioState(BaseModel):
    model_config = ConfigDict(extra="allow")

    account_id: str
    total_equity_usd: float | None = None
    cash_usd: float | None = None
    exposure_usd: float | None = None
    positions: list[BridgePortfolioAsset] = Field(default_factory=list)
    snapshot_metadata: dict[str, Any] | None = None
    updated_at: str | None = None
    reconciliation: dict[str, Any] | None = None
    venues: list[str] | None = None


class BridgePortfolioEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: BridgePortfolioEnvelopeMeta
    data: BridgePortfolioState


class BridgePositionRiskSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_positions: int = 0
    largest_position_symbol: str | None = None
    largest_position_notional_usd: float | None = None
    largest_position_weight: float | None = None
    cash_buffer_pct: float | None = None
    gross_exposure_pct: float | None = None
    warnings: list[str] = Field(default_factory=list)


class BridgePositionStateLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    quantity: float
    mark_price: float | None = None
    notional_usd: float | None = None
    state: Literal["open", "closed"]
    exposure_side: Literal["long", "short", "flat", "unknown"]
    last_update_source: Literal["persisted_snapshot", "live_sync", "execution_projection"]
    execution_mode: Literal["paper", "live", "unknown"]
    updated_at: str | None = None
    last_request_id: str | None = None
    last_correlation_id: str | None = None


class BridgeMonitorExecutionContext(BaseModel):
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


class BridgePositionMonitor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    observed_at: str
    portfolio: BridgePortfolioState
    risk_summary: BridgePositionRiskSummary
    position_states: list[BridgePositionStateLine] = Field(default_factory=list)
    snapshot_metadata: dict[str, Any] = Field(default_factory=dict)
    state_mode: Literal["paper", "live", "unknown"] = "unknown"
    last_execution: BridgeMonitorExecutionContext | None = None
    source: Literal["persisted_snapshot", "live_sync"]


class BridgePortfolioResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "live"
    portfolio: BridgePortfolioEnvelope


class BridgePortfolioSyncResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "live"
    sync: BridgePortfolioEnvelope


class BridgePositionMonitorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "live"
    monitor: BridgePositionMonitor
