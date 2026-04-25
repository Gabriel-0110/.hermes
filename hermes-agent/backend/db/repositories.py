"""Shared repository layer for Hermes Timescale-backed storage."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .models import (
    AgentSignalRow,
    AgentDecisionRow,
    EvaluationScoreRow,
    ExecutionEventRow,
    MovementJournalRow,
    NotificationSentRow,
    PaperShadowFillRow,
    PortfolioSnapshotRow,
    RegressionComparisonRow,
    ReplayCaseRow,
    ReplayResultRow,
    ReplayRunRow,
    RiskEventRow,
    SystemErrorRow,
    ToolCallRow,
    TradingViewAlertEventRow,
    TradingViewInternalEventRow,
    WorkflowRunRow,
    WorkflowStepRow,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class HermesTimeSeriesRepository:
    """Shared backend-owned reads and writes for trading/time-series data."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def insert_tradingview_alert(
        self,
        *,
        source: str,
        symbol: str | None,
        timeframe: str | None,
        alert_name: str | None,
        signal: str | None,
        direction: str | None,
        strategy: str | None,
        price: float | None,
        payload: dict[str, Any],
        processing_status: str,
        processing_error: str | None,
        alert_id: str | None = None,
        event_time: datetime | None = None,
    ) -> TradingViewAlertEventRow:
        row = TradingViewAlertEventRow(
            event_time=event_time or _utcnow(),
            id=alert_id,
            source=source,
            symbol=symbol,
            timeframe=timeframe,
            alert_name=alert_name,
            signal=signal,
            direction=direction,
            strategy=strategy,
            price=price,
            payload=payload,
            processing_status=processing_status,
            processing_error=processing_error,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def insert_internal_event(
        self,
        *,
        event_type: str,
        alert_event_id: str,
        symbol: str | None,
        payload: dict[str, Any],
        delivery_status: str = "pending",
        delivery_error: str | None = None,
        event_id: str | None = None,
        event_time: datetime | None = None,
    ) -> TradingViewInternalEventRow:
        row = TradingViewInternalEventRow(
            event_time=event_time or _utcnow(),
            id=event_id,
            event_type=event_type,
            alert_event_id=alert_event_id,
            symbol=symbol,
            payload=payload,
            delivery_status=delivery_status,
            delivery_error=delivery_error,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def list_tradingview_alerts(
        self,
        *,
        limit: int = 20,
        symbol: str | None = None,
        processing_status: str | None = None,
    ) -> list[TradingViewAlertEventRow]:
        statement = select(TradingViewAlertEventRow)
        if symbol:
            statement = statement.where(TradingViewAlertEventRow.symbol == symbol.upper())
        if processing_status:
            statement = statement.where(TradingViewAlertEventRow.processing_status == processing_status)
        statement = statement.order_by(desc(TradingViewAlertEventRow.event_time)).limit(max(1, min(limit, 200)))
        return list(self.session.scalars(statement))

    def get_tradingview_alert_by_id(self, alert_id: str) -> TradingViewAlertEventRow | None:
        statement = (
            select(TradingViewAlertEventRow)
            .where(TradingViewAlertEventRow.id == alert_id)
            .order_by(desc(TradingViewAlertEventRow.event_time))
            .limit(1)
        )
        return self.session.scalars(statement).first()

    def list_internal_events(
        self,
        *,
        limit: int = 20,
        event_type: str | None = None,
        delivery_status: str | None = None,
        symbol: str | None = None,
        alert_event_id: str | None = None,
    ) -> list[TradingViewInternalEventRow]:
        statement = select(TradingViewInternalEventRow)
        if event_type:
            statement = statement.where(TradingViewInternalEventRow.event_type == event_type)
        if delivery_status:
            statement = statement.where(TradingViewInternalEventRow.delivery_status == delivery_status)
        if symbol:
            statement = statement.where(TradingViewInternalEventRow.symbol == symbol.upper())
        if alert_event_id:
            statement = statement.where(TradingViewInternalEventRow.alert_event_id == alert_event_id)
        statement = statement.order_by(desc(TradingViewInternalEventRow.event_time)).limit(max(1, min(limit, 200)))
        return list(self.session.scalars(statement))

    def insert_agent_signal(
        self,
        *,
        agent_id: str | None,
        symbol: str | None,
        signal_type: str | None,
        direction: str | None,
        confidence: float | None,
        payload: dict[str, Any],
        signal_time: datetime | None = None,
        signal_id: str | None = None,
    ) -> AgentSignalRow:
        row = AgentSignalRow(
            signal_time=signal_time or _utcnow(),
            id=signal_id,
            agent_id=agent_id,
            symbol=symbol,
            signal_type=signal_type,
            direction=direction,
            confidence=confidence,
            payload=payload,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def list_agent_signals(
        self,
        *,
        limit: int = 20,
        symbol: str | None = None,
        agent_id: str | None = None,
    ) -> list[AgentSignalRow]:
        statement = select(AgentSignalRow)
        if symbol:
            statement = statement.where(AgentSignalRow.symbol == symbol.upper())
        if agent_id:
            statement = statement.where(AgentSignalRow.agent_id == agent_id)
        statement = statement.order_by(desc(AgentSignalRow.signal_time)).limit(max(1, min(limit, 200)))
        return list(self.session.scalars(statement))

    def insert_portfolio_snapshot(
        self,
        *,
        account_id: str,
        total_equity_usd: float | None,
        cash_usd: float | None,
        exposure_usd: float | None,
        positions: list[dict[str, Any]],
        payload: dict[str, Any] | None = None,
        snapshot_time: datetime | None = None,
    ) -> PortfolioSnapshotRow:
        row = PortfolioSnapshotRow(
            snapshot_time=snapshot_time or _utcnow(),
            account_id=account_id,
            total_equity_usd=total_equity_usd,
            cash_usd=cash_usd,
            exposure_usd=exposure_usd,
            positions=positions,
            payload=payload or {},
        )
        self.session.merge(row)
        self.session.flush()
        return row

    def get_latest_portfolio_snapshot(self, *, account_id: str) -> PortfolioSnapshotRow | None:
        statement = (
            select(PortfolioSnapshotRow)
            .where(PortfolioSnapshotRow.account_id == account_id)
            .order_by(desc(PortfolioSnapshotRow.snapshot_time))
            .limit(1)
        )
        return self.session.scalars(statement).first()

    def get_portfolio_snapshot_at_or_before(
        self,
        *,
        account_id: str,
        as_of: datetime,
    ) -> PortfolioSnapshotRow | None:
        statement = (
            select(PortfolioSnapshotRow)
            .where(PortfolioSnapshotRow.account_id == account_id)
            .where(PortfolioSnapshotRow.snapshot_time <= as_of)
            .order_by(desc(PortfolioSnapshotRow.snapshot_time))
            .limit(1)
        )
        return self.session.scalars(statement).first()

    def list_portfolio_snapshots(
        self,
        *,
        limit: int = 20,
        account_id: str | None = None,
    ) -> list[PortfolioSnapshotRow]:
        statement = select(PortfolioSnapshotRow)
        if account_id:
            statement = statement.where(PortfolioSnapshotRow.account_id == account_id)
        statement = statement.order_by(desc(PortfolioSnapshotRow.snapshot_time)).limit(max(1, min(limit, 200)))
        return list(self.session.scalars(statement))

    def insert_risk_event(
        self,
        *,
        symbol: str | None,
        severity: str | None,
        event_type: str | None,
        payload: dict[str, Any],
        event_time: datetime | None = None,
        event_id: str | None = None,
    ) -> RiskEventRow:
        row = RiskEventRow(
            event_time=event_time or _utcnow(),
            id=event_id,
            symbol=symbol,
            severity=severity,
            event_type=event_type,
            payload=payload,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def list_risk_events(
        self,
        *,
        limit: int = 20,
        symbol: str | None = None,
        severity: str | None = None,
    ) -> list[RiskEventRow]:
        statement = select(RiskEventRow)
        if symbol:
            statement = statement.where(RiskEventRow.symbol == symbol.upper())
        if severity:
            statement = statement.where(RiskEventRow.severity == severity)
        statement = statement.order_by(desc(RiskEventRow.event_time)).limit(max(1, min(limit, 200)))
        return list(self.session.scalars(statement))

    def insert_notification_sent(
        self,
        *,
        channel: str,
        message_id: str | None,
        delivered: bool,
        payload: dict[str, Any],
        detail: str | None = None,
        sent_time: datetime | None = None,
        notification_id: str | None = None,
        retry_count: int = 0,
        next_retry_at: datetime | None = None,
        last_error: str | None = None,
    ) -> NotificationSentRow:
        row = NotificationSentRow(
            sent_time=sent_time or _utcnow(),
            id=notification_id,
            channel=channel,
            message_id=message_id,
            delivered=delivered,
            payload=payload,
            detail=detail,
            retry_count=retry_count,
            next_retry_at=next_retry_at,
            last_error=last_error,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def update_notification_delivery(
        self,
        *,
        notification_row: NotificationSentRow,
        delivered: bool,
        message_id: str | None = None,
        detail: str | None = None,
        retry_count: int | None = None,
        next_retry_at: datetime | None = None,
        last_error: str | None = None,
    ) -> NotificationSentRow:
        """Update delivery status and retry tracking on an existing row."""
        notification_row.delivered = delivered
        if message_id is not None:
            notification_row.message_id = message_id
        if detail is not None:
            notification_row.detail = detail
        if retry_count is not None:
            notification_row.retry_count = retry_count
        if next_retry_at is not None:
            notification_row.next_retry_at = next_retry_at
        if last_error is not None:
            notification_row.last_error = last_error
        elif delivered:
            notification_row.last_error = None
            notification_row.next_retry_at = None
        self.session.flush()
        return notification_row

    def list_notifications_sent(
        self,
        *,
        limit: int = 20,
        channel: str | None = None,
        delivered: bool | None = None,
    ) -> list[NotificationSentRow]:
        statement = select(NotificationSentRow)
        if channel:
            statement = statement.where(NotificationSentRow.channel == channel)
        if delivered is not None:
            statement = statement.where(NotificationSentRow.delivered == delivered)
        statement = statement.order_by(desc(NotificationSentRow.sent_time)).limit(max(1, min(limit, 200)))
        return list(self.session.scalars(statement))

    def list_failed_notifications_for_retry(
        self,
        *,
        max_retries: int = 3,
        limit: int = 50,
        as_of: datetime | None = None,
    ) -> list[NotificationSentRow]:
        """Return undelivered notifications eligible for a retry attempt."""
        from sqlalchemy import or_

        now = as_of or _utcnow()
        statement = (
            select(NotificationSentRow)
            .where(NotificationSentRow.delivered == False)  # noqa: E712
            .where(NotificationSentRow.retry_count < max_retries)
            .where(NotificationSentRow.channel != "log")
            .where(
                or_(
                    NotificationSentRow.next_retry_at == None,  # noqa: E711
                    NotificationSentRow.next_retry_at <= now,
                )
            )
            .order_by(NotificationSentRow.sent_time)
            .limit(max(1, min(limit, 200)))
        )
        return list(self.session.scalars(statement))

    def upsert_workflow_run(
        self,
        *,
        workflow_run_id: str,
        event_id: str | None,
        correlation_id: str | None,
        workflow_name: str,
        status: str,
        agent_name: str | None = None,
        workflow_step: str | None = None,
        tool_name: str | None = None,
        summarized_input: str | None = None,
        summarized_output: str | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
        created_at: datetime | None = None,
    ) -> WorkflowRunRow:
        row = self.get_workflow_run(workflow_run_id)
        if row is None:
            row = WorkflowRunRow(
                created_at=created_at or _utcnow(),
                id=workflow_run_id,
                event_id=event_id,
                correlation_id=correlation_id,
                workflow_name=workflow_name,
                status=status,
                agent_name=agent_name,
                workflow_step=workflow_step,
                tool_name=tool_name,
                summarized_input=summarized_input,
                summarized_output=summarized_output,
                error_message=error_message,
                metadata_json=metadata or {},
            )
            self.session.add(row)
        else:
            row.event_id = event_id or row.event_id
            row.correlation_id = correlation_id or row.correlation_id
            row.workflow_name = workflow_name or row.workflow_name
            row.status = status
            row.agent_name = agent_name if agent_name is not None else row.agent_name
            row.workflow_step = workflow_step if workflow_step is not None else row.workflow_step
            row.tool_name = tool_name if tool_name is not None else row.tool_name
            row.summarized_input = summarized_input if summarized_input is not None else row.summarized_input
            row.summarized_output = summarized_output if summarized_output is not None else row.summarized_output
            row.error_message = error_message if error_message is not None else row.error_message
            row.metadata_json = metadata or row.metadata_json or {}
        self.session.flush()
        return row

    def get_workflow_run(self, workflow_run_id: str) -> WorkflowRunRow | None:
        statement = (
            select(WorkflowRunRow)
            .where(WorkflowRunRow.id == workflow_run_id)
            .order_by(desc(WorkflowRunRow.created_at))
            .limit(1)
        )
        return self.session.scalars(statement).first()

    def list_recent_workflow_runs(
        self,
        *,
        limit: int = 20,
        status: str | None = None,
    ) -> list[WorkflowRunRow]:
        statement = select(WorkflowRunRow)
        if status:
            statement = statement.where(WorkflowRunRow.status == status)
        statement = statement.order_by(desc(WorkflowRunRow.created_at)).limit(max(1, min(limit, 200)))
        return list(self.session.scalars(statement))

    def upsert_workflow_step(
        self,
        *,
        step_id: str,
        workflow_run_id: str | None,
        event_id: str | None,
        correlation_id: str | None,
        workflow_name: str,
        workflow_step: str,
        status: str,
        agent_name: str | None = None,
        tool_name: str | None = None,
        summarized_input: str | None = None,
        summarized_output: str | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
        created_at: datetime | None = None,
    ) -> WorkflowStepRow:
        row = self.get_workflow_step(step_id)
        if row is None:
            row = WorkflowStepRow(
                created_at=created_at or _utcnow(),
                id=step_id,
                workflow_run_id=workflow_run_id,
                event_id=event_id,
                correlation_id=correlation_id,
                workflow_name=workflow_name,
                workflow_step=workflow_step,
                status=status,
                agent_name=agent_name,
                tool_name=tool_name,
                summarized_input=summarized_input,
                summarized_output=summarized_output,
                error_message=error_message,
                metadata_json=metadata or {},
            )
            self.session.add(row)
        else:
            row.workflow_run_id = workflow_run_id or row.workflow_run_id
            row.event_id = event_id or row.event_id
            row.correlation_id = correlation_id or row.correlation_id
            row.workflow_name = workflow_name or row.workflow_name
            row.workflow_step = workflow_step or row.workflow_step
            row.status = status
            row.agent_name = agent_name if agent_name is not None else row.agent_name
            row.tool_name = tool_name if tool_name is not None else row.tool_name
            row.summarized_input = summarized_input if summarized_input is not None else row.summarized_input
            row.summarized_output = summarized_output if summarized_output is not None else row.summarized_output
            row.error_message = error_message if error_message is not None else row.error_message
            row.metadata_json = metadata or row.metadata_json or {}
        self.session.flush()
        return row

    def get_workflow_step(self, step_id: str) -> WorkflowStepRow | None:
        statement = (
            select(WorkflowStepRow)
            .where(WorkflowStepRow.id == step_id)
            .order_by(desc(WorkflowStepRow.created_at))
            .limit(1)
        )
        return self.session.scalars(statement).first()

    def list_workflow_steps(
        self,
        *,
        workflow_run_id: str | None = None,
        correlation_id: str | None = None,
        limit: int = 200,
    ) -> list[WorkflowStepRow]:
        statement = select(WorkflowStepRow)
        if workflow_run_id:
            statement = statement.where(WorkflowStepRow.workflow_run_id == workflow_run_id)
        if correlation_id:
            statement = statement.where(WorkflowStepRow.correlation_id == correlation_id)
        statement = statement.order_by(WorkflowStepRow.created_at.asc()).limit(max(1, min(limit, 500)))
        return list(self.session.scalars(statement))

    def insert_tool_call(
        self,
        *,
        workflow_run_id: str | None,
        event_id: str | None,
        correlation_id: str | None,
        tool_name: str,
        status: str,
        agent_name: str | None = None,
        workflow_name: str | None = None,
        workflow_step: str | None = None,
        summarized_input: str | None = None,
        summarized_output: str | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
        call_id: str | None = None,
        created_at: datetime | None = None,
    ) -> ToolCallRow:
        row = ToolCallRow(
            created_at=created_at or _utcnow(),
            id=call_id,
            workflow_run_id=workflow_run_id,
            event_id=event_id,
            correlation_id=correlation_id,
            agent_name=agent_name,
            workflow_name=workflow_name,
            workflow_step=workflow_step,
            tool_name=tool_name,
            status=status,
            summarized_input=summarized_input,
            summarized_output=summarized_output,
            error_message=error_message,
            metadata_json=metadata or {},
        )
        self.session.add(row)
        self.session.flush()
        return row

    def get_tool_call_history(
        self,
        *,
        limit: int = 50,
        correlation_id: str | None = None,
        workflow_run_id: str | None = None,
        tool_name: str | None = None,
    ) -> list[ToolCallRow]:
        statement = select(ToolCallRow)
        if correlation_id:
            statement = statement.where(ToolCallRow.correlation_id == correlation_id)
        if workflow_run_id:
            statement = statement.where(ToolCallRow.workflow_run_id == workflow_run_id)
        if tool_name:
            statement = statement.where(ToolCallRow.tool_name == tool_name)
        statement = statement.order_by(desc(ToolCallRow.created_at)).limit(max(1, min(limit, 500)))
        return list(self.session.scalars(statement))

    def insert_agent_decision(
        self,
        *,
        workflow_run_id: str | None,
        event_id: str | None,
        correlation_id: str | None,
        agent_name: str,
        status: str,
        decision: str | None = None,
        workflow_name: str | None = None,
        workflow_step: str | None = None,
        tool_name: str | None = None,
        summarized_input: str | None = None,
        summarized_output: str | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
        decision_id: str | None = None,
        created_at: datetime | None = None,
    ) -> AgentDecisionRow:
        row = AgentDecisionRow(
            created_at=created_at or _utcnow(),
            id=decision_id,
            workflow_run_id=workflow_run_id,
            event_id=event_id,
            correlation_id=correlation_id,
            agent_name=agent_name,
            workflow_name=workflow_name,
            workflow_step=workflow_step,
            tool_name=tool_name,
            status=status,
            decision=decision,
            summarized_input=summarized_input,
            summarized_output=summarized_output,
            error_message=error_message,
            metadata_json=metadata or {},
        )
        self.session.add(row)
        self.session.flush()
        return row

    def get_agent_decision_history(
        self,
        *,
        limit: int = 50,
        correlation_id: str | None = None,
        workflow_run_id: str | None = None,
        agent_name: str | None = None,
    ) -> list[AgentDecisionRow]:
        statement = select(AgentDecisionRow)
        if correlation_id:
            statement = statement.where(AgentDecisionRow.correlation_id == correlation_id)
        if workflow_run_id:
            statement = statement.where(AgentDecisionRow.workflow_run_id == workflow_run_id)
        if agent_name:
            statement = statement.where(AgentDecisionRow.agent_name == agent_name)
        statement = statement.order_by(desc(AgentDecisionRow.created_at)).limit(max(1, min(limit, 500)))
        return list(self.session.scalars(statement))

    def insert_execution_event(
        self,
        *,
        workflow_run_id: str | None,
        event_id: str | None,
        correlation_id: str | None,
        status: str,
        event_type: str | None = None,
        agent_name: str | None = None,
        workflow_name: str | None = None,
        workflow_step: str | None = None,
        tool_name: str | None = None,
        summarized_input: str | None = None,
        summarized_output: str | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
        execution_event_id: str | None = None,
        created_at: datetime | None = None,
    ) -> ExecutionEventRow:
        row = ExecutionEventRow(
            created_at=created_at or _utcnow(),
            id=execution_event_id,
            workflow_run_id=workflow_run_id,
            event_id=event_id,
            correlation_id=correlation_id,
            agent_name=agent_name,
            workflow_name=workflow_name,
            workflow_step=workflow_step,
            tool_name=tool_name,
            status=status,
            event_type=event_type,
            summarized_input=summarized_input,
            summarized_output=summarized_output,
            error_message=error_message,
            metadata_json=metadata or {},
        )
        self.session.add(row)
        self.session.flush()
        return row

    def get_execution_event_history(
        self,
        *,
        limit: int = 50,
        correlation_id: str | None = None,
        workflow_run_id: str | None = None,
    ) -> list[ExecutionEventRow]:
        statement = select(ExecutionEventRow)
        if correlation_id:
            statement = statement.where(ExecutionEventRow.correlation_id == correlation_id)
        if workflow_run_id:
            statement = statement.where(ExecutionEventRow.workflow_run_id == workflow_run_id)
        statement = statement.order_by(desc(ExecutionEventRow.created_at)).limit(max(1, min(limit, 500)))
        return list(self.session.scalars(statement))

    def insert_movement_journal_entry(
        self,
        *,
        movement_type: str,
        status: str,
        workflow_run_id: str | None,
        event_id: str | None,
        correlation_id: str | None,
        account_id: str | None = None,
        symbol: str | None = None,
        side: str | None = None,
        quantity: float | None = None,
        cash_delta_usd: float | None = None,
        notional_delta_usd: float | None = None,
        price: float | None = None,
        execution_mode: str | None = None,
        order_id: str | None = None,
        request_id: str | None = None,
        idempotency_key: str | None = None,
        source_kind: str | None = None,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        movement_id: str | None = None,
        movement_time: datetime | None = None,
    ) -> MovementJournalRow:
        row = MovementJournalRow(
            movement_time=movement_time or _utcnow(),
            id=movement_id,
            workflow_run_id=workflow_run_id,
            event_id=event_id,
            correlation_id=correlation_id,
            account_id=account_id,
            symbol=symbol,
            movement_type=movement_type,
            status=status,
            side=side,
            quantity=quantity,
            cash_delta_usd=cash_delta_usd,
            notional_delta_usd=notional_delta_usd,
            price=price,
            execution_mode=execution_mode,
            order_id=order_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
            source_kind=source_kind,
            payload_json=payload or {},
            metadata_json=metadata or {},
        )
        self.session.add(row)
        self.session.flush()
        return row

    def list_movement_journal_entries(
        self,
        *,
        limit: int = 50,
        correlation_id: str | None = None,
        workflow_run_id: str | None = None,
        symbol: str | None = None,
        account_id: str | None = None,
        movement_type: str | None = None,
    ) -> list[MovementJournalRow]:
        statement = select(MovementJournalRow)
        if correlation_id:
            statement = statement.where(MovementJournalRow.correlation_id == correlation_id)
        if workflow_run_id:
            statement = statement.where(MovementJournalRow.workflow_run_id == workflow_run_id)
        if symbol:
            statement = statement.where(MovementJournalRow.symbol == symbol.upper())
        if account_id:
            statement = statement.where(MovementJournalRow.account_id == account_id)
        if movement_type:
            statement = statement.where(MovementJournalRow.movement_type == movement_type)
        statement = statement.order_by(desc(MovementJournalRow.movement_time)).limit(max(1, min(limit, 500)))
        return list(self.session.scalars(statement))

    def insert_paper_shadow_fill(
        self,
        *,
        fill_time: datetime,
        symbol: str,
        side: str,
        execution_style: str,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        proposal_id: str | None = None,
        request_id: str | None = None,
        leg_id: str | None = None,
        correlation_id: str | None = None,
        workflow_run_id: str | None = None,
        strategy_id: str | None = None,
        strategy_template_id: str | None = None,
        source_agent: str | None = None,
        live_order_id: str | None = None,
        live_reference_price: float | None = None,
        shadow_price: float | None = None,
        amount: float | None = None,
        live_notional_usd: float | None = None,
        shadow_notional_usd: float | None = None,
        pnl_divergence_usd: float | None = None,
        paper_shadow_fill_id: str | None = None,
    ) -> PaperShadowFillRow:
        row = PaperShadowFillRow(
            fill_time=fill_time,
            id=paper_shadow_fill_id,
            proposal_id=proposal_id,
            request_id=request_id,
            leg_id=leg_id,
            correlation_id=correlation_id,
            workflow_run_id=workflow_run_id,
            strategy_id=strategy_id,
            strategy_template_id=strategy_template_id,
            source_agent=source_agent,
            symbol=symbol,
            side=side,
            execution_style=execution_style,
            live_order_id=live_order_id,
            live_reference_price=live_reference_price,
            shadow_price=shadow_price,
            amount=amount,
            live_notional_usd=live_notional_usd,
            shadow_notional_usd=shadow_notional_usd,
            pnl_divergence_usd=pnl_divergence_usd,
            payload_json=payload or {},
            metadata_json=metadata or {},
        )
        self.session.add(row)
        self.session.flush()
        return row

    def list_paper_shadow_fills(
        self,
        *,
        limit: int = 200,
        strategy_template_id: str | None = None,
        symbol: str | None = None,
        since: datetime | None = None,
    ) -> list[PaperShadowFillRow]:
        statement = select(PaperShadowFillRow)
        if strategy_template_id:
            statement = statement.where(PaperShadowFillRow.strategy_template_id == strategy_template_id)
        if symbol:
            statement = statement.where(PaperShadowFillRow.symbol == symbol.upper())
        if since:
            statement = statement.where(PaperShadowFillRow.fill_time >= since)
        statement = statement.order_by(desc(PaperShadowFillRow.fill_time)).limit(max(1, min(limit, 1000)))
        return list(self.session.scalars(statement))

    def insert_system_error(
        self,
        *,
        workflow_run_id: str | None,
        event_id: str | None,
        correlation_id: str | None,
        status: str,
        error_message: str | None,
        error_type: str | None = None,
        agent_name: str | None = None,
        workflow_name: str | None = None,
        workflow_step: str | None = None,
        tool_name: str | None = None,
        summarized_input: str | None = None,
        summarized_output: str | None = None,
        metadata: dict[str, Any] | None = None,
        is_failure: bool = True,
        system_error_id: str | None = None,
        created_at: datetime | None = None,
    ) -> SystemErrorRow:
        row = SystemErrorRow(
            created_at=created_at or _utcnow(),
            id=system_error_id,
            workflow_run_id=workflow_run_id,
            event_id=event_id,
            correlation_id=correlation_id,
            agent_name=agent_name,
            workflow_name=workflow_name,
            workflow_step=workflow_step,
            tool_name=tool_name,
            status=status,
            error_type=error_type,
            summarized_input=summarized_input,
            summarized_output=summarized_output,
            error_message=error_message,
            metadata_json=metadata or {},
            is_failure=is_failure,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def get_system_errors(
        self,
        *,
        limit: int = 50,
        correlation_id: str | None = None,
        workflow_run_id: str | None = None,
    ) -> list[SystemErrorRow]:
        statement = select(SystemErrorRow)
        if correlation_id:
            statement = statement.where(SystemErrorRow.correlation_id == correlation_id)
        if workflow_run_id:
            statement = statement.where(SystemErrorRow.workflow_run_id == workflow_run_id)
        statement = statement.order_by(desc(SystemErrorRow.created_at)).limit(max(1, min(limit, 500)))
        return list(self.session.scalars(statement))

    def get_recent_failures(self, *, limit: int = 50) -> list[SystemErrorRow]:
        statement = (
            select(SystemErrorRow)
            .where(SystemErrorRow.is_failure.is_(True))
            .order_by(desc(SystemErrorRow.created_at))
            .limit(max(1, min(limit, 500)))
        )
        return list(self.session.scalars(statement))

    def insert_replay_case(
        self,
        *,
        source_type: str,
        input_payload: dict[str, Any],
        source_event_id: str | None = None,
        source_correlation_id: str | None = None,
        source_alert_id: str | None = None,
        label: str | None = None,
        expected_outcome: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        replay_case_id: str | None = None,
        created_at: datetime | None = None,
    ) -> ReplayCaseRow:
        row = ReplayCaseRow(
            created_at=created_at or _utcnow(),
            id=replay_case_id,
            source_type=source_type,
            source_event_id=source_event_id,
            source_correlation_id=source_correlation_id,
            source_alert_id=source_alert_id,
            label=label,
            input_payload=input_payload,
            expected_outcome=expected_outcome or {},
            metadata_json=metadata or {},
        )
        self.session.add(row)
        self.session.flush()
        return row

    def get_replay_case(self, replay_case_id: str) -> ReplayCaseRow | None:
        statement = (
            select(ReplayCaseRow)
            .where(ReplayCaseRow.id == replay_case_id)
            .order_by(desc(ReplayCaseRow.created_at))
            .limit(1)
        )
        return self.session.scalars(statement).first()

    def list_replay_cases(
        self,
        *,
        limit: int = 50,
        source_type: str | None = None,
        source_event_id: str | None = None,
    ) -> list[ReplayCaseRow]:
        statement = select(ReplayCaseRow)
        if source_type:
            statement = statement.where(ReplayCaseRow.source_type == source_type)
        if source_event_id:
            statement = statement.where(ReplayCaseRow.source_event_id == source_event_id)
        statement = statement.order_by(desc(ReplayCaseRow.created_at)).limit(max(1, min(limit, 500)))
        return list(self.session.scalars(statement))

    def insert_replay_run(
        self,
        *,
        replay_case_id: str,
        workflow_name: str,
        status: str,
        workflow_run_id: str | None = None,
        workflow_version: str | None = None,
        model_name: str | None = None,
        prompt_version: str | None = None,
        source_event_id: str | None = None,
        source_correlation_id: str | None = None,
        mode: str = "replay",
        configuration: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        replay_run_id: str | None = None,
        created_at: datetime | None = None,
    ) -> ReplayRunRow:
        row = ReplayRunRow(
            created_at=created_at or _utcnow(),
            id=replay_run_id,
            replay_case_id=replay_case_id,
            workflow_run_id=workflow_run_id,
            workflow_name=workflow_name,
            workflow_version=workflow_version,
            model_name=model_name,
            prompt_version=prompt_version,
            source_event_id=source_event_id,
            source_correlation_id=source_correlation_id,
            mode=mode,
            status=status,
            configuration_json=configuration or {},
            metadata_json=metadata or {},
        )
        self.session.add(row)
        self.session.flush()
        return row

    def get_replay_run(self, replay_run_id: str) -> ReplayRunRow | None:
        statement = (
            select(ReplayRunRow)
            .where(ReplayRunRow.id == replay_run_id)
            .order_by(desc(ReplayRunRow.created_at))
            .limit(1)
        )
        return self.session.scalars(statement).first()

    def update_replay_run(
        self,
        replay_run_id: str,
        *,
        status: str | None = None,
        workflow_run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ReplayRunRow | None:
        row = self.get_replay_run(replay_run_id)
        if row is None:
            return None
        if status is not None:
            row.status = status
        if workflow_run_id is not None:
            row.workflow_run_id = workflow_run_id
        if metadata is not None:
            row.metadata_json = metadata
        self.session.flush()
        return row

    def list_replay_runs(
        self,
        *,
        limit: int = 50,
        replay_case_id: str | None = None,
        status: str | None = None,
    ) -> list[ReplayRunRow]:
        statement = select(ReplayRunRow)
        if replay_case_id:
            statement = statement.where(ReplayRunRow.replay_case_id == replay_case_id)
        if status:
            statement = statement.where(ReplayRunRow.status == status)
        statement = statement.order_by(desc(ReplayRunRow.created_at)).limit(max(1, min(limit, 500)))
        return list(self.session.scalars(statement))

    def insert_replay_result(
        self,
        *,
        replay_run_id: str,
        replay_case_id: str,
        output_json: dict[str, Any],
        state_json: dict[str, Any],
        should_execute: bool,
        execution_intent: dict[str, Any] | None = None,
        notifications: list[Any] | None = None,
        workflow_run_id: str | None = None,
        source_event_id: str | None = None,
        source_correlation_id: str | None = None,
        decision: str | None = None,
        status: str | None = None,
        latency_ms: float | None = None,
        metadata: dict[str, Any] | None = None,
        replay_result_id: str | None = None,
        created_at: datetime | None = None,
    ) -> ReplayResultRow:
        row = ReplayResultRow(
            created_at=created_at or _utcnow(),
            id=replay_result_id,
            replay_run_id=replay_run_id,
            replay_case_id=replay_case_id,
            workflow_run_id=workflow_run_id,
            source_event_id=source_event_id,
            source_correlation_id=source_correlation_id,
            decision=decision,
            status=status,
            should_execute=should_execute,
            execution_intent=execution_intent or {},
            notifications=notifications or [],
            output_json=output_json,
            state_json=state_json,
            latency_ms=latency_ms,
            metadata_json=metadata or {},
        )
        self.session.add(row)
        self.session.flush()
        return row

    def get_replay_result(self, replay_result_id: str) -> ReplayResultRow | None:
        statement = (
            select(ReplayResultRow)
            .where(ReplayResultRow.id == replay_result_id)
            .order_by(desc(ReplayResultRow.created_at))
            .limit(1)
        )
        return self.session.scalars(statement).first()

    def list_replay_results(
        self,
        *,
        replay_run_id: str,
        limit: int = 200,
    ) -> list[ReplayResultRow]:
        statement = (
            select(ReplayResultRow)
            .where(ReplayResultRow.replay_run_id == replay_run_id)
            .order_by(ReplayResultRow.created_at.asc())
            .limit(max(1, min(limit, 500)))
        )
        return list(self.session.scalars(statement))

    def insert_evaluation_score(
        self,
        *,
        replay_run_id: str,
        replay_result_id: str,
        replay_case_id: str,
        rule_name: str,
        metric_name: str,
        value: float,
        passed: bool,
        detail: str | None = None,
        metadata: dict[str, Any] | None = None,
        evaluation_score_id: str | None = None,
        created_at: datetime | None = None,
    ) -> EvaluationScoreRow:
        row = EvaluationScoreRow(
            created_at=created_at or _utcnow(),
            id=evaluation_score_id,
            replay_run_id=replay_run_id,
            replay_result_id=replay_result_id,
            replay_case_id=replay_case_id,
            rule_name=rule_name,
            metric_name=metric_name,
            value=value,
            passed=passed,
            detail=detail,
            metadata_json=metadata or {},
        )
        self.session.add(row)
        self.session.flush()
        return row

    def list_evaluation_scores(
        self,
        *,
        replay_run_id: str,
        limit: int = 500,
    ) -> list[EvaluationScoreRow]:
        statement = (
            select(EvaluationScoreRow)
            .where(EvaluationScoreRow.replay_run_id == replay_run_id)
            .order_by(EvaluationScoreRow.created_at.asc())
            .limit(max(1, min(limit, 1000)))
        )
        return list(self.session.scalars(statement))

    def insert_regression_comparison(
        self,
        *,
        baseline_replay_run_id: str,
        candidate_replay_run_id: str,
        comparison_type: str,
        summary: dict[str, Any],
        baseline_label: str | None = None,
        candidate_label: str | None = None,
        status: str = "completed",
        metadata: dict[str, Any] | None = None,
        regression_comparison_id: str | None = None,
        created_at: datetime | None = None,
    ) -> RegressionComparisonRow:
        row = RegressionComparisonRow(
            created_at=created_at or _utcnow(),
            id=regression_comparison_id,
            baseline_replay_run_id=baseline_replay_run_id,
            candidate_replay_run_id=candidate_replay_run_id,
            comparison_type=comparison_type,
            baseline_label=baseline_label,
            candidate_label=candidate_label,
            status=status,
            summary_json=summary,
            metadata_json=metadata or {},
        )
        self.session.add(row)
        self.session.flush()
        return row

    def list_regression_comparisons(
        self,
        *,
        baseline_replay_run_id: str | None = None,
        candidate_replay_run_id: str | None = None,
        limit: int = 100,
    ) -> list[RegressionComparisonRow]:
        statement = select(RegressionComparisonRow)
        if baseline_replay_run_id:
            statement = statement.where(RegressionComparisonRow.baseline_replay_run_id == baseline_replay_run_id)
        if candidate_replay_run_id:
            statement = statement.where(RegressionComparisonRow.candidate_replay_run_id == candidate_replay_run_id)
        statement = statement.order_by(desc(RegressionComparisonRow.created_at)).limit(max(1, min(limit, 500)))
        return list(self.session.scalars(statement))
