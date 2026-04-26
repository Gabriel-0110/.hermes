"""SQLAlchemy models for Timescale-backed shared time-series storage."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class TradingViewAlertEventRow(Base):
    __tablename__ = "tradingview_alert_events"
    __table_args__ = (
        Index("ix_tv_alert_events_symbol_time", "symbol", "event_time"),
        Index("ix_tv_alert_events_status_time", "processing_status", "event_time"),
    )

    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: _new_id("tv_alert"))
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timeframe: Mapped[str | None] = mapped_column(String(32), nullable=True)
    alert_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    signal: Mapped[str | None] = mapped_column(String(64), nullable=True)
    direction: Mapped[str | None] = mapped_column(String(32), nullable=True)
    strategy: Mapped[str | None] = mapped_column(String(160), nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False)
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class TradingViewInternalEventRow(Base):
    __tablename__ = "tradingview_internal_events"
    __table_args__ = (
        Index("ix_tv_internal_events_type_status_time", "event_type", "delivery_status", "event_time"),
        Index("ix_tv_internal_events_symbol_time", "symbol", "event_time"),
    )

    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: _new_id("tv_evt"))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    alert_event_id: Mapped[str] = mapped_column(String(80), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    delivery_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    delivery_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class AgentSignalRow(Base):
    __tablename__ = "agent_signals"
    __table_args__ = (
        Index("ix_agent_signals_symbol_time", "symbol", "signal_time"),
        Index("ix_agent_signals_agent_time", "agent_id", "signal_time"),
    )

    signal_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: _new_id("signal"))
    agent_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    symbol: Mapped[str | None] = mapped_column(String(64), nullable=True)
    signal_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    direction: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class PortfolioSnapshotRow(Base):
    __tablename__ = "portfolio_snapshots"
    __table_args__ = (
        Index("ix_portfolio_snapshots_account_time", "account_id", "snapshot_time"),
    )

    snapshot_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    total_equity_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    cash_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    exposure_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    positions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class RiskEventRow(Base):
    __tablename__ = "risk_events"
    __table_args__ = (
        Index("ix_risk_events_symbol_time", "symbol", "event_time"),
        Index("ix_risk_events_severity_time", "severity", "event_time"),
    )

    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: _new_id("risk"))
    symbol: Mapped[str | None] = mapped_column(String(64), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class NotificationSentRow(Base):
    __tablename__ = "notifications_sent"
    __table_args__ = (
        Index("ix_notifications_sent_channel_time", "channel", "sent_time"),
        Index("ix_notifications_sent_delivered_time", "delivered", "sent_time"),
        Index("ix_notifications_sent_retry_time", "next_retry_at", "sent_time"),
    )

    sent_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: _new_id("notif"))
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    message_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    delivered: Mapped[bool] = mapped_column(nullable=False, default=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Retry tracking — nullable so existing rows without these columns still load
    retry_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class WorkflowRunRow(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        Index("ix_workflow_runs_correlation_time", "correlation_id", "created_at"),
        Index("ix_workflow_runs_event_time", "event_id", "created_at"),
        Index("ix_workflow_runs_status_time", "status", "created_at"),
        Index("ix_workflow_runs_workflow_name_time", "workflow_name", "created_at"),
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=lambda: _new_id("wf_run"))
    event_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    agent_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    workflow_name: Mapped[str] = mapped_column(String(160), nullable=False)
    workflow_step: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    summarized_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    summarized_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class WorkflowStepRow(Base):
    __tablename__ = "workflow_steps"
    __table_args__ = (
        Index("ix_workflow_steps_run_time", "workflow_run_id", "created_at"),
        Index("ix_workflow_steps_correlation_time", "correlation_id", "created_at"),
        Index("ix_workflow_steps_status_time", "status", "created_at"),
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=lambda: _new_id("wf_step"))
    workflow_run_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    event_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    agent_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    workflow_name: Mapped[str] = mapped_column(String(160), nullable=False)
    workflow_step: Mapped[str] = mapped_column(String(120), nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    summarized_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    summarized_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ToolCallRow(Base):
    __tablename__ = "tool_calls"
    __table_args__ = (
        Index("ix_tool_calls_correlation_time", "correlation_id", "created_at"),
        Index("ix_tool_calls_tool_time", "tool_name", "created_at"),
        Index("ix_tool_calls_run_time", "workflow_run_id", "created_at"),
        Index("ix_tool_calls_status_time", "status", "created_at"),
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=lambda: _new_id("tool"))
    workflow_run_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    event_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    agent_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    workflow_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    workflow_step: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    summarized_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    summarized_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AgentDecisionRow(Base):
    __tablename__ = "agent_decisions"
    __table_args__ = (
        Index("ix_agent_decisions_correlation_time", "correlation_id", "created_at"),
        Index("ix_agent_decisions_agent_time", "agent_name", "created_at"),
        Index("ix_agent_decisions_run_time", "workflow_run_id", "created_at"),
        Index("ix_agent_decisions_status_time", "status", "created_at"),
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=lambda: _new_id("decision"))
    workflow_run_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    event_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    agent_name: Mapped[str] = mapped_column(String(120), nullable=False)
    workflow_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    workflow_step: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summarized_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    summarized_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ExecutionEventRow(Base):
    __tablename__ = "execution_events"
    __table_args__ = (
        Index("ix_execution_events_correlation_time", "correlation_id", "created_at"),
        Index("ix_execution_events_status_time", "status", "created_at"),
        Index("ix_execution_events_run_time", "workflow_run_id", "created_at"),
        Index("ix_execution_events_tool_time", "tool_name", "created_at"),
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=lambda: _new_id("exec"))
    workflow_run_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    event_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    agent_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    workflow_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    workflow_step: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    summarized_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    summarized_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class MovementJournalRow(Base):
    __tablename__ = "movement_journal"
    __table_args__ = (
        Index("ix_movement_journal_correlation_time", "correlation_id", "movement_time"),
        Index("ix_movement_journal_run_time", "workflow_run_id", "movement_time"),
        Index("ix_movement_journal_symbol_time", "symbol", "movement_time"),
        Index("ix_movement_journal_account_time", "account_id", "movement_time"),
        Index("ix_movement_journal_type_time", "movement_type", "movement_time"),
    )

    movement_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=lambda: _new_id("move"))
    workflow_run_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    event_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    account_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    symbol: Mapped[str | None] = mapped_column(String(64), nullable=True)
    movement_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    side: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    cash_delta_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    notional_delta_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    execution_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    order_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_kind: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payload_json: Mapped[dict] = mapped_column("payload", JSON, nullable=False, default=dict)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class PaperShadowFillRow(Base):
    __tablename__ = "paper_shadow_fills"
    __table_args__ = (
        Index("ix_paper_shadow_fills_strategy_time", "strategy_template_id", "fill_time"),
        Index("ix_paper_shadow_fills_symbol_time", "symbol", "fill_time"),
        Index("ix_paper_shadow_fills_request_time", "request_id", "fill_time"),
        Index("ix_paper_shadow_fills_correlation_time", "correlation_id", "fill_time"),
    )

    fill_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=lambda: _new_id("shadow_fill"))
    proposal_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    leg_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    workflow_run_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    strategy_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    strategy_template_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_agent: Mapped[str | None] = mapped_column(String(120), nullable=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    side: Mapped[str] = mapped_column(String(32), nullable=False)
    execution_style: Mapped[str] = mapped_column(String(32), nullable=False, default="single")
    live_order_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    live_reference_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    shadow_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    live_notional_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    shadow_notional_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl_divergence_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    payload_json: Mapped[dict] = mapped_column("payload", JSON, nullable=False, default=dict)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class RiskLimitRow(Base):
    __tablename__ = "risk_limits"
    __table_args__ = (
        Index("ix_risk_limits_updated_at", "updated_at"),
    )

    scope: Mapped[str] = mapped_column(String(64), primary_key=True)
    max_position_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_notional_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_leverage: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_daily_loss_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    drawdown_limit_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    carry_trade_max_equity_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SystemErrorRow(Base):
    __tablename__ = "system_errors"
    __table_args__ = (
        Index("ix_system_errors_correlation_time", "correlation_id", "created_at"),
        Index("ix_system_errors_status_time", "status", "created_at"),
        Index("ix_system_errors_tool_time", "tool_name", "created_at"),
        Index("ix_system_errors_run_time", "workflow_run_id", "created_at"),
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=lambda: _new_id("err"))
    workflow_run_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    event_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    agent_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    workflow_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    workflow_step: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="error")
    error_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    summarized_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    summarized_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    is_failure: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ReplayCaseRow(Base):
    __tablename__ = "replay_cases"
    __table_args__ = (
        Index("ix_replay_cases_source_event_time", "source_event_id", "created_at"),
        Index("ix_replay_cases_source_correlation_time", "source_correlation_id", "created_at"),
        Index("ix_replay_cases_source_type_time", "source_type", "created_at"),
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=lambda: _new_id("replay_case"))
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_event_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_correlation_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_alert_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    input_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    expected_outcome: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ReplayRunRow(Base):
    __tablename__ = "replay_runs"
    __table_args__ = (
        Index("ix_replay_runs_case_time", "replay_case_id", "created_at"),
        Index("ix_replay_runs_status_time", "status", "created_at"),
        Index("ix_replay_runs_workflow_run_time", "workflow_run_id", "created_at"),
        Index("ix_replay_runs_source_event_time", "source_event_id", "created_at"),
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=lambda: _new_id("replay_run"))
    replay_case_id: Mapped[str] = mapped_column(String(120), nullable=False)
    workflow_run_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    workflow_name: Mapped[str] = mapped_column(String(160), nullable=False)
    workflow_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_event_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_correlation_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="replay")
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_json: Mapped[dict] = mapped_column("configuration", JSON, nullable=False, default=dict)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ReplayResultRow(Base):
    __tablename__ = "replay_results"
    __table_args__ = (
        Index("ix_replay_results_run_time", "replay_run_id", "created_at"),
        Index("ix_replay_results_case_time", "replay_case_id", "created_at"),
        Index("ix_replay_results_decision_time", "decision", "created_at"),
        Index("ix_replay_results_source_event_time", "source_event_id", "created_at"),
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=lambda: _new_id("replay_result"))
    replay_run_id: Mapped[str] = mapped_column(String(120), nullable=False)
    replay_case_id: Mapped[str] = mapped_column(String(120), nullable=False)
    workflow_run_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_event_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_correlation_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    decision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    should_execute: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    execution_intent: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    notifications: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    output_json: Mapped[dict] = mapped_column("output", JSON, nullable=False, default=dict)
    state_json: Mapped[dict] = mapped_column("state", JSON, nullable=False, default=dict)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class EvaluationScoreRow(Base):
    __tablename__ = "evaluation_scores"
    __table_args__ = (
        Index("ix_evaluation_scores_run_time", "replay_run_id", "created_at"),
        Index("ix_evaluation_scores_result_time", "replay_result_id", "created_at"),
        Index("ix_evaluation_scores_rule_time", "rule_name", "created_at"),
        Index("ix_evaluation_scores_passed_time", "passed", "created_at"),
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=lambda: _new_id("eval_score"))
    replay_run_id: Mapped[str] = mapped_column(String(120), nullable=False)
    replay_result_id: Mapped[str] = mapped_column(String(120), nullable=False)
    replay_case_id: Mapped[str] = mapped_column(String(120), nullable=False)
    rule_name: Mapped[str] = mapped_column(String(120), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class RegressionComparisonRow(Base):
    __tablename__ = "regression_comparisons"
    __table_args__ = (
        Index("ix_regression_comparisons_baseline_time", "baseline_replay_run_id", "created_at"),
        Index("ix_regression_comparisons_candidate_time", "candidate_replay_run_id", "created_at"),
        Index("ix_regression_comparisons_type_time", "comparison_type", "created_at"),
        Index("ix_regression_comparisons_status_time", "status", "created_at"),
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=lambda: _new_id("regression"))
    baseline_replay_run_id: Mapped[str] = mapped_column(String(120), nullable=False)
    candidate_replay_run_id: Mapped[str] = mapped_column(String(120), nullable=False)
    comparison_type: Mapped[str] = mapped_column(String(64), nullable=False)
    baseline_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    candidate_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="completed")
    summary_json: Mapped[dict] = mapped_column("summary", JSON, nullable=False, default=dict)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ChronosForecastRow(Base):
    """Cached Chronos forecast snapshots used by strategy scorers."""

    __tablename__ = "chronos_forecasts"
    __table_args__ = (
        Index("ix_chronos_forecasts_symbol_interval_time", "symbol", "interval", "forecast_time"),
        Index("ix_chronos_forecasts_symbol_horizon_time", "symbol", "horizon", "forecast_time"),
    )

    forecast_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: _new_id("chronos"))
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    interval: Mapped[str] = mapped_column(String(32), nullable=False)
    horizon: Mapped[int] = mapped_column(Integer, nullable=False)
    latest_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    median_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    low_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    high_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    projected_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    forecast_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payload_json: Mapped[dict] = mapped_column("payload", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


# ---------------------------------------------------------------------------
# Phase 4 — Advanced Intelligence / Optimization
# ---------------------------------------------------------------------------


class ResearchMemoRow(Base):
    """Durable per-symbol and themed research memos for agent knowledge accumulation."""

    __tablename__ = "research_memos"
    __table_args__ = (
        Index("ix_research_memos_symbol_time", "symbol", "memo_time"),
        Index("ix_research_memos_agent_time", "source_agent", "memo_time"),
        Index("ix_research_memos_strategy_time", "strategy_ref", "memo_time"),
    )

    memo_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: _new_id("memo"))
    symbol: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_agent: Mapped[str] = mapped_column(String(120), nullable=False, default="hermes")
    strategy_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    superseded_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class StrategyEvaluationRow(Base):
    """Records of strategy scoring runs for candidate symbols — evaluation loop scaffold."""

    __tablename__ = "strategy_evaluations"
    __table_args__ = (
        Index("ix_strategy_evals_strategy_time", "strategy_name", "eval_time"),
        Index("ix_strategy_evals_symbol_time", "symbol", "eval_time"),
        Index("ix_strategy_evals_direction_time", "direction", "eval_time"),
    )

    eval_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: _new_id("eval"))
    strategy_name: Mapped[str] = mapped_column(String(120), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0.0")
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(32), nullable=False, default="1h")
    direction: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Outcome fields — filled in after trade resolves (evaluation loop)
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pnl_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class CopyTraderScoreRow(Base):
    """Daily leaderboard scoring snapshots for copy-trader curation."""

    __tablename__ = "copy_trader_scores"
    __table_args__ = (
        Index("ix_copy_trader_scores_trader_time", "trader_id", "score_time"),
        Index("ix_copy_trader_scores_rank_time", "rank", "score_time"),
        Index("ix_copy_trader_scores_active_time", "is_active_master", "score_time"),
    )

    score_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=lambda: _new_id("copy_score"))
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="bitmart_aihub")
    snapshot_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    trader_id: Mapped[str] = mapped_column(String(160), nullable=False)
    trader_name: Mapped[str] = mapped_column(String(200), nullable=False)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    score_percentile: Mapped[float] = mapped_column(Float, nullable=False)
    sharpe_30d: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown_pct_30d: Mapped[float | None] = mapped_column(Float, nullable=True)
    fee_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active_master: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )


class CopyTraderSwitchProposalRow(Base):
    """Operator approvals for recommended copy-trader master switches."""

    __tablename__ = "copy_trader_switch_proposals"
    __table_args__ = (
        Index("ix_copy_trader_switch_proposals_active_time", "active_trader_id", "created_at"),
        Index("ix_copy_trader_switch_proposals_status_time", "status", "created_at"),
        Index("ix_copy_trader_switch_proposals_candidate_time", "candidate_trader_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=lambda: _new_id("copy_switch"))
    active_trader_id: Mapped[str] = mapped_column(String(160), nullable=False)
    active_trader_name: Mapped[str] = mapped_column(String(200), nullable=False)
    candidate_trader_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    candidate_trader_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    active_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    active_percentile: Mapped[float | None] = mapped_column(Float, nullable=True)
    candidate_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    candidate_percentile: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    delivery_channel: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notification_message_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    payload_json: Mapped[dict] = mapped_column("payload", JSON, nullable=False, default=dict)
    operator: Mapped[str | None] = mapped_column(String(120), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
    )


class PolicyTraceRow(Base):
    __tablename__ = "policy_traces"
    __table_args__ = (
        Index("ix_policy_traces_proposal_id", "proposal_id"),
        Index("ix_policy_traces_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: _new_id("ptrace"))
    proposal_id: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decision_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    trace: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    rejection_reasons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), server_default=func.now(),
    )


class StrategyWeightOverrideRow(Base):
    __tablename__ = "strategy_weight_overrides"
    __table_args__ = (
        Index("ix_strategy_weight_overrides_lookup", "strategy", "symbol", "regime", unique=True),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: _new_id("swo"))
    strategy: Mapped[str] = mapped_column(String(120), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False, default="*")
    regime: Mapped[str] = mapped_column(String(32), nullable=False, default="*")
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    evidence_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), server_default=func.now(),
    )


class OperatorSnapshotRow(Base):
    __tablename__ = "operator_snapshots"
    __table_args__ = (
        Index("ix_operator_snapshots_exchange_time", "exchange", "as_of_utc"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: _new_id("snap"))
    exchange: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_equity_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    available_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    invested_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    unrealized_pnl_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    divergence_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
