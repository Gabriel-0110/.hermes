"""Context propagation helpers for correlation-aware backend observability."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from typing import Any, Iterator


@dataclass(slots=True)
class AuditContext:
    event_id: str | None = None
    correlation_id: str | None = None
    workflow_run_id: str | None = None
    workflow_name: str | None = None
    workflow_step: str | None = None
    agent_name: str | None = None
    tool_name: str | None = None
    metadata: dict[str, Any] | None = None


_AUDIT_CONTEXT: ContextVar[AuditContext | None] = ContextVar("audit_context", default=None)
_PENDING_TOOL_INPUT: ContextVar[dict[str, Any] | None] = ContextVar("pending_tool_input", default=None)


def get_audit_context() -> AuditContext | None:
    return _AUDIT_CONTEXT.get()


def get_pending_tool_input() -> dict[str, Any] | None:
    return _PENDING_TOOL_INPUT.get()


def set_pending_tool_input(payload: dict[str, Any] | None) -> None:
    _PENDING_TOOL_INPUT.set(payload)


def clear_pending_tool_input() -> None:
    _PENDING_TOOL_INPUT.set(None)


@contextmanager
def use_audit_context(context: AuditContext) -> Iterator[AuditContext]:
    token = _AUDIT_CONTEXT.set(context)
    try:
        yield context
    finally:
        _AUDIT_CONTEXT.reset(token)


@contextmanager
def derived_audit_context(**updates: Any) -> Iterator[AuditContext]:
    current = get_audit_context() or AuditContext()
    metadata = dict(current.metadata or {})
    extra_metadata = updates.pop("metadata", None)
    if isinstance(extra_metadata, dict):
        metadata.update(extra_metadata)
    next_context = replace(current, **updates, metadata=metadata)
    with use_audit_context(next_context):
        yield next_context
