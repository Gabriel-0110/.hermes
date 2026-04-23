"""Backend-native observability and audit trail helpers."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import OperationalError

from backend.db import HermesTimeSeriesRepository, ensure_time_series_schema, session_scope
from backend.db.session import get_database_url, get_engine, get_sqlite_fallback_url
from hermes_constants import get_hermes_home

from .context import AuditContext, get_audit_context

logger = logging.getLogger(__name__)

_SENSITIVE_KEYWORDS = ("token", "secret", "password", "authorization", "webhook", "api_key", "private_key")
_SUMMARY_LIMIT = 1200
_FALLBACK_EXCEPTIONS = (OperationalError, ModuleNotFoundError, ImportError)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if any(keyword in str(key).lower() for keyword in _SENSITIVE_KEYWORDS):
                sanitized[str(key)] = "[redacted]"
            else:
                sanitized[str(key)] = _redact(item)
        return sanitized
    if isinstance(value, list):
        return [_redact(item) for item in value[:50]]
    if isinstance(value, tuple):
        return [_redact(item) for item in value[:50]]
    if isinstance(value, str):
        return value[:400]
    return value


def summarize_payload(payload: Any) -> str | None:
    if payload is None:
        return None
    try:
        text = json.dumps(_redact(payload), sort_keys=True, default=str)
    except Exception:
        text = str(payload)
    if len(text) <= _SUMMARY_LIMIT:
        return text
    return f"{text[:_SUMMARY_LIMIT]}...<truncated>"


def _context_or_default(context: AuditContext | None = None) -> AuditContext:
    return context or get_audit_context() or AuditContext()


def _row_to_dict(row: Any, *, created_attr: str = "created_at") -> dict[str, Any]:
    payload = {
        key: value
        for key, value in vars(row).items()
        if not key.startswith("_sa_")
    }
    created_at = payload.get(created_attr)
    updated_at = payload.get("updated_at")
    if isinstance(created_at, datetime):
        payload[created_attr] = created_at.isoformat()
    if isinstance(updated_at, datetime):
        payload["updated_at"] = updated_at.isoformat()
    record_payload = payload.pop("payload_json", None)
    metadata = payload.pop("metadata_json", None)
    if record_payload is not None:
        payload["payload"] = record_payload
    if metadata is not None:
        payload["metadata"] = metadata
        if isinstance(metadata, dict):
            if "symbol" not in payload and metadata.get("symbol") is not None:
                payload["symbol"] = metadata.get("symbol")
            if "payload" not in payload and metadata.get("payload") is not None:
                payload["payload"] = metadata.get("payload")
    return payload


class ObservabilityService:
    """High-level persistence/query facade for audit and operator visibility."""

    def __init__(self) -> None:
        self._fallback_db_path = get_hermes_home() / "state.db"

    def _with_repo(self, fn):
        database_url = get_database_url()
        fallback_url = get_sqlite_fallback_url(self._fallback_db_path)
        try:
            ensure_time_series_schema(get_engine(database_url=database_url, db_path=self._fallback_db_path))
            with session_scope(database_url=database_url, db_path=self._fallback_db_path) as session:
                repo = HermesTimeSeriesRepository(session)
                return fn(repo)
        except _FALLBACK_EXCEPTIONS:
            logger.warning("Observability falling back to local SQLite because the shared DB is unavailable.")
            ensure_time_series_schema(get_engine(database_url=fallback_url))
            with session_scope(database_url=fallback_url) as session:
                repo = HermesTimeSeriesRepository(session)
                return fn(repo)

    def record_workflow_run(
        self,
        *,
        workflow_run_id: str,
        workflow_name: str,
        status: str,
        context: AuditContext | None = None,
        agent_name: str | None = None,
        workflow_step: str | None = None,
        summarized_input: Any = None,
        summarized_output: Any = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        audit = _context_or_default(context)
        row = self._with_repo(
            lambda repo: repo.upsert_workflow_run(
                workflow_run_id=workflow_run_id,
                event_id=audit.event_id,
                correlation_id=audit.correlation_id,
                workflow_name=workflow_name,
                status=status,
                agent_name=agent_name or audit.agent_name,
                workflow_step=workflow_step or audit.workflow_step,
                summarized_input=summarize_payload(summarized_input),
                summarized_output=summarize_payload(summarized_output),
                error_message=error_message,
                metadata=metadata or audit.metadata or {},
                created_at=_utcnow(),
            )
        )
        return _row_to_dict(row)

    def record_workflow_step(
        self,
        *,
        step_id: str,
        workflow_run_id: str | None,
        workflow_name: str,
        workflow_step: str,
        status: str,
        context: AuditContext | None = None,
        agent_name: str | None = None,
        tool_name: str | None = None,
        summarized_input: Any = None,
        summarized_output: Any = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        audit = _context_or_default(context)
        row = self._with_repo(
            lambda repo: repo.upsert_workflow_step(
                step_id=step_id,
                workflow_run_id=workflow_run_id or audit.workflow_run_id,
                event_id=audit.event_id,
                correlation_id=audit.correlation_id,
                workflow_name=workflow_name,
                workflow_step=workflow_step,
                status=status,
                agent_name=agent_name or audit.agent_name,
                tool_name=tool_name or audit.tool_name,
                summarized_input=summarize_payload(summarized_input),
                summarized_output=summarize_payload(summarized_output),
                error_message=error_message,
                metadata=metadata or audit.metadata or {},
                created_at=_utcnow(),
            )
        )
        return _row_to_dict(row)

    def record_tool_call(
        self,
        *,
        tool_name: str,
        status: str,
        context: AuditContext | None = None,
        summarized_input: Any = None,
        summarized_output: Any = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        audit = _context_or_default(context)
        row = self._with_repo(
            lambda repo: repo.insert_tool_call(
                workflow_run_id=audit.workflow_run_id,
                event_id=audit.event_id,
                correlation_id=audit.correlation_id,
                agent_name=audit.agent_name,
                workflow_name=audit.workflow_name,
                workflow_step=audit.workflow_step,
                tool_name=tool_name,
                status=status,
                summarized_input=summarize_payload(summarized_input),
                summarized_output=summarize_payload(summarized_output),
                error_message=error_message,
                metadata=metadata or audit.metadata or {},
                created_at=_utcnow(),
            )
        )
        return _row_to_dict(row)

    def record_agent_decision(
        self,
        *,
        agent_name: str,
        status: str,
        decision: str | None = None,
        context: AuditContext | None = None,
        summarized_input: Any = None,
        summarized_output: Any = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        audit = _context_or_default(context)
        row = self._with_repo(
            lambda repo: repo.insert_agent_decision(
                workflow_run_id=audit.workflow_run_id,
                event_id=audit.event_id,
                correlation_id=audit.correlation_id,
                agent_name=agent_name,
                workflow_name=audit.workflow_name,
                workflow_step=audit.workflow_step,
                tool_name=audit.tool_name,
                status=status,
                decision=decision,
                summarized_input=summarize_payload(summarized_input),
                summarized_output=summarize_payload(summarized_output),
                error_message=error_message,
                metadata=metadata or audit.metadata or {},
                created_at=_utcnow(),
            )
        )
        return _row_to_dict(row)

    def record_execution_event(
        self,
        *,
        status: str,
        event_type: str,
        context: AuditContext | None = None,
        workflow_run_id: str | None = None,
        event_id: str | None = None,
        correlation_id: str | None = None,
        workflow_name: str | None = None,
        workflow_step: str | None = None,
        agent_name: str | None = None,
        tool_name: str | None = None,
        symbol: str | None = None,
        payload: dict[str, Any] | None = None,
        summarized_input: Any = None,
        summarized_output: Any = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        audit = _context_or_default(context)
        merged_metadata = {**(audit.metadata or {}), **(metadata or {})}
        if symbol is not None:
            merged_metadata.setdefault("symbol", symbol)
        if payload is not None:
            merged_metadata.setdefault("payload", payload)
        row = self._with_repo(
            lambda repo: repo.insert_execution_event(
                workflow_run_id=workflow_run_id or audit.workflow_run_id,
                event_id=event_id or audit.event_id,
                correlation_id=correlation_id or audit.correlation_id,
                agent_name=agent_name or audit.agent_name,
                workflow_name=workflow_name or audit.workflow_name,
                workflow_step=workflow_step or audit.workflow_step,
                tool_name=tool_name or audit.tool_name,
                status=status,
                event_type=event_type,
                summarized_input=summarize_payload(summarized_input),
                summarized_output=summarize_payload(summarized_output),
                error_message=error_message,
                metadata=merged_metadata,
                created_at=_utcnow(),
            )
        )
        return _row_to_dict(row)

    def record_movement(
        self,
        *,
        movement_type: str,
        status: str,
        context: AuditContext | None = None,
        workflow_run_id: str | None = None,
        event_id: str | None = None,
        correlation_id: str | None = None,
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
    ) -> dict[str, Any]:
        audit = _context_or_default(context)
        row = self._with_repo(
            lambda repo: repo.insert_movement_journal_entry(
                movement_type=movement_type,
                status=status,
                workflow_run_id=workflow_run_id or audit.workflow_run_id,
                event_id=event_id or audit.event_id,
                correlation_id=correlation_id or audit.correlation_id,
                account_id=account_id,
                symbol=symbol,
                side=side,
                quantity=quantity,
                cash_delta_usd=cash_delta_usd,
                notional_delta_usd=notional_delta_usd,
                price=price,
                execution_mode=execution_mode,
                order_id=order_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                source_kind=source_kind or audit.agent_name,
                payload=payload or {},
                metadata={**(audit.metadata or {}), **(metadata or {})},
                movement_time=_utcnow(),
            )
        )
        return _row_to_dict(row, created_attr="movement_time")

    def record_system_error(
        self,
        *,
        status: str,
        error_message: str | None,
        context: AuditContext | None = None,
        error_type: str | None = None,
        agent_name: str | None = None,
        tool_name: str | None = None,
        summarized_input: Any = None,
        summarized_output: Any = None,
        metadata: dict[str, Any] | None = None,
        is_failure: bool = True,
    ) -> dict[str, Any]:
        audit = _context_or_default(context)
        row = self._with_repo(
            lambda repo: repo.insert_system_error(
                workflow_run_id=audit.workflow_run_id,
                event_id=audit.event_id,
                correlation_id=audit.correlation_id,
                agent_name=agent_name or audit.agent_name,
                workflow_name=audit.workflow_name,
                workflow_step=audit.workflow_step,
                tool_name=tool_name or audit.tool_name,
                status=status,
                error_type=error_type,
                summarized_input=summarize_payload(summarized_input),
                summarized_output=summarize_payload(summarized_output),
                error_message=error_message,
                metadata=metadata or audit.metadata or {},
                is_failure=is_failure,
                created_at=_utcnow(),
            )
        )
        return _row_to_dict(row)

    def get_workflow_run(self, workflow_run_id: str) -> dict[str, Any] | None:
        row = self._with_repo(lambda repo: repo.get_workflow_run(workflow_run_id))
        if row is None:
            return None
        payload = _row_to_dict(row)
        payload["steps"] = self._with_repo(
            lambda repo: [_row_to_dict(item) for item in repo.list_workflow_steps(workflow_run_id=workflow_run_id)]
        )
        return payload

    def list_recent_workflow_runs(self, *, limit: int = 20, status: str | None = None) -> list[dict[str, Any]]:
        rows = self._with_repo(lambda repo: repo.list_recent_workflow_runs(limit=limit, status=status))
        return [_row_to_dict(row) for row in rows]

    def get_agent_decision_history(
        self,
        *,
        limit: int = 50,
        correlation_id: str | None = None,
        workflow_run_id: str | None = None,
        agent_name: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self._with_repo(
            lambda repo: repo.get_agent_decision_history(
                limit=limit,
                correlation_id=correlation_id,
                workflow_run_id=workflow_run_id,
                agent_name=agent_name,
            )
        )
        return [_row_to_dict(row) for row in rows]

    def get_tool_call_history(
        self,
        *,
        limit: int = 50,
        correlation_id: str | None = None,
        workflow_run_id: str | None = None,
        tool_name: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self._with_repo(
            lambda repo: repo.get_tool_call_history(
                limit=limit,
                correlation_id=correlation_id,
                workflow_run_id=workflow_run_id,
                tool_name=tool_name,
            )
        )
        return [_row_to_dict(row) for row in rows]

    def get_execution_event_history(
        self,
        *,
        limit: int = 50,
        correlation_id: str | None = None,
        workflow_run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self._with_repo(
            lambda repo: repo.get_execution_event_history(
                limit=limit,
                correlation_id=correlation_id,
                workflow_run_id=workflow_run_id,
            )
        )
        return [_row_to_dict(row) for row in rows]

    def get_movement_history(
        self,
        *,
        limit: int = 50,
        correlation_id: str | None = None,
        workflow_run_id: str | None = None,
        symbol: str | None = None,
        account_id: str | None = None,
        movement_type: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self._with_repo(
            lambda repo: repo.list_movement_journal_entries(
                limit=limit,
                correlation_id=correlation_id,
                workflow_run_id=workflow_run_id,
                symbol=symbol,
                account_id=account_id,
                movement_type=movement_type,
            )
        )
        return [_row_to_dict(row, created_attr="movement_time") for row in rows]

    def get_system_errors(
        self,
        *,
        limit: int = 50,
        correlation_id: str | None = None,
        workflow_run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self._with_repo(
            lambda repo: repo.get_system_errors(
                limit=limit,
                correlation_id=correlation_id,
                workflow_run_id=workflow_run_id,
            )
        )
        return [_row_to_dict(row) for row in rows]

    def get_recent_failures(self, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._with_repo(lambda repo: repo.get_recent_failures(limit=limit))
        return [_row_to_dict(row) for row in rows]

    def get_recent_notifications(self, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._with_repo(lambda repo: repo.list_notifications_sent(limit=limit))
        return [_row_to_dict(row, created_attr="sent_time") for row in rows]

    def get_event_timeline(self, correlation_id: str, *, limit_per_source: int = 100) -> list[dict[str, Any]]:
        timeline: list[dict[str, Any]] = []

        for item in self.list_recent_workflow_runs(limit=limit_per_source):
            if item.get("correlation_id") == correlation_id:
                timeline.append({"kind": "workflow_run", **item, "timestamp": item["created_at"]})

        for item in self.get_tool_call_history(limit=limit_per_source, correlation_id=correlation_id):
            timeline.append({"kind": "tool_call", **item, "timestamp": item["created_at"]})

        workflow_steps = self._with_repo(
            lambda repo: [_row_to_dict(row) for row in repo.list_workflow_steps(correlation_id=correlation_id, limit=limit_per_source)]
        )
        for item in workflow_steps:
            timeline.append({"kind": "workflow_step", **item, "timestamp": item["created_at"]})

        for item in self.get_agent_decision_history(limit=limit_per_source, correlation_id=correlation_id):
            timeline.append({"kind": "agent_decision", **item, "timestamp": item["created_at"]})

        for item in self.get_execution_event_history(limit=limit_per_source, correlation_id=correlation_id):
            timeline.append({"kind": "execution_event", **item, "timestamp": item["created_at"]})

        for item in self.get_movement_history(limit=limit_per_source, correlation_id=correlation_id):
            timeline.append({"kind": "movement", **item, "timestamp": item["movement_time"]})

        for item in self.get_system_errors(limit=limit_per_source, correlation_id=correlation_id):
            timeline.append({"kind": "system_error", **item, "timestamp": item["created_at"]})

        for item in self.get_recent_notifications(limit=limit_per_source):
            payload = item.get("payload") or {}
            metadata = payload.get("metadata") or {}
            if metadata.get("correlation_id") == correlation_id:
                timeline.append({"kind": "notification", **item, "timestamp": item["sent_time"]})

        timeline.sort(key=lambda item: item.get("timestamp") or "", reverse=False)
        return timeline

    def get_dashboard_snapshot(self, *, limit: int = 20) -> dict[str, Any]:
        workflow_runs = self.list_recent_workflow_runs(limit=limit)
        failures = self.get_recent_failures(limit=limit)
        execution_events = self.get_execution_event_history(limit=limit)
        movements = self.get_movement_history(limit=limit)
        notifications = self.get_recent_notifications(limit=limit)
        risk_rejections = [
            row
            for row in self.get_agent_decision_history(limit=limit * 3, agent_name="risk_manager")
            if row.get("decision") == "reject" or row.get("status") in {"reject", "rejected", "failed"}
        ][:limit]
        pending_or_running = [
            row for row in workflow_runs if row.get("status") in {"running", "in_progress", "pending", "manual_review"}
        ]
        return {
            "recent_workflow_runs": workflow_runs,
            "pending_or_in_progress": pending_or_running,
            "recent_failures": failures,
            "recent_execution_events": execution_events,
            "recent_movements": movements,
            "recent_risk_rejections": risk_rejections,
            "recent_notifications": notifications,
        }


_SERVICE: ObservabilityService | None = None


def get_observability_service() -> ObservabilityService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = ObservabilityService()
    return _SERVICE
