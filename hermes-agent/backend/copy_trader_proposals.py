"""Persistence helpers for operator-reviewed copy-trader switch proposals."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select

from backend.db import ensure_time_series_schema, session_scope
from backend.db.models import CopyTraderSwitchProposalRow
from backend.db.session import get_engine

logger = logging.getLogger(__name__)


def create_or_get_pending_copy_trader_switch_proposal(
    *,
    active_trader_id: str,
    active_trader_name: str,
    candidate_trader_id: str | None,
    candidate_trader_name: str | None,
    rationale: str,
    active_score: float | None,
    active_percentile: float | None,
    candidate_score: float | None,
    candidate_percentile: float | None,
    threshold_days: int = 7,
    payload: dict[str, Any] | None = None,
    database_url: str | None = None,
) -> tuple[dict[str, Any], bool]:
    """Create a pending proposal unless one already exists for the same active trader."""

    ensure_time_series_schema(get_engine(database_url=database_url))

    with session_scope(database_url=database_url) as session:
        existing = session.scalars(
            select(CopyTraderSwitchProposalRow)
            .where(CopyTraderSwitchProposalRow.active_trader_id == active_trader_id)
            .where(CopyTraderSwitchProposalRow.status == "pending")
            .order_by(desc(CopyTraderSwitchProposalRow.created_at))
        ).first()
        if existing is not None:
            return _row_to_dict(existing), False

        row = CopyTraderSwitchProposalRow(
            active_trader_id=active_trader_id,
            active_trader_name=active_trader_name,
            candidate_trader_id=candidate_trader_id,
            candidate_trader_name=candidate_trader_name,
            status="pending",
            rationale=rationale,
            active_score=active_score,
            active_percentile=active_percentile,
            candidate_score=candidate_score,
            candidate_percentile=candidate_percentile,
            threshold_days=threshold_days,
            payload_json=payload or {},
        )
        session.add(row)
        session.flush()
        return _row_to_dict(row), True


def get_copy_trader_switch_proposal(
    proposal_id: str,
    *,
    database_url: str | None = None,
) -> dict[str, Any] | None:
    """Return a copy-trader switch proposal by ID."""

    ensure_time_series_schema(get_engine(database_url=database_url))
    with session_scope(database_url=database_url) as session:
        row = session.get(CopyTraderSwitchProposalRow, proposal_id)
        return _row_to_dict(row) if row is not None else None


def mark_copy_trader_switch_proposal_notified(
    proposal_id: str,
    *,
    channel: str,
    message_id: str | None,
    database_url: str | None = None,
) -> dict[str, Any] | None:
    """Attach outbound notification metadata to a proposal."""

    ensure_time_series_schema(get_engine(database_url=database_url))
    with session_scope(database_url=database_url) as session:
        row = session.get(CopyTraderSwitchProposalRow, proposal_id)
        if row is None:
            return None
        row.delivery_channel = channel
        row.notification_message_id = message_id
        return _row_to_dict(row)


def approve_copy_trader_switch_proposal(
    proposal_id: str,
    *,
    operator: str = "telegram",
    note: str | None = None,
    database_url: str | None = None,
) -> dict[str, Any] | None:
    """Approve a pending copy-trader switch proposal."""

    return _resolve_copy_trader_switch_proposal(
        proposal_id,
        status="approved",
        operator=operator,
        note=note,
        database_url=database_url,
    )


def reject_copy_trader_switch_proposal(
    proposal_id: str,
    *,
    operator: str = "telegram",
    note: str | None = None,
    database_url: str | None = None,
) -> dict[str, Any] | None:
    """Reject a pending copy-trader switch proposal."""

    return _resolve_copy_trader_switch_proposal(
        proposal_id,
        status="rejected",
        operator=operator,
        note=note,
        database_url=database_url,
    )


def _resolve_copy_trader_switch_proposal(
    proposal_id: str,
    *,
    status: str,
    operator: str,
    note: str | None,
    database_url: str | None,
) -> dict[str, Any] | None:
    ensure_time_series_schema(get_engine(database_url=database_url))

    with session_scope(database_url=database_url) as session:
        row = session.get(CopyTraderSwitchProposalRow, proposal_id)
        if row is None:
            logger.warning("copy_trader_proposals: unknown proposal_id=%s", proposal_id)
            return None
        if row.status != "pending":
            logger.info(
                "copy_trader_proposals: proposal_id=%s already resolved as %s",
                proposal_id,
                row.status,
            )
            return None

        now = datetime.now(UTC)
        row.status = status
        row.operator = operator
        row.decision_note = note
        if status == "approved":
            row.approved_at = now
        elif status == "rejected":
            row.rejected_at = now
        return _row_to_dict(row)


def _row_to_dict(row: CopyTraderSwitchProposalRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "active_trader_id": row.active_trader_id,
        "active_trader_name": row.active_trader_name,
        "candidate_trader_id": row.candidate_trader_id,
        "candidate_trader_name": row.candidate_trader_name,
        "status": row.status,
        "rationale": row.rationale,
        "active_score": row.active_score,
        "active_percentile": row.active_percentile,
        "candidate_score": row.candidate_score,
        "candidate_percentile": row.candidate_percentile,
        "threshold_days": row.threshold_days,
        "delivery_channel": row.delivery_channel,
        "notification_message_id": row.notification_message_id,
        "payload": row.payload_json or {},
        "operator": row.operator,
        "decision_note": row.decision_note,
        "approved_at": row.approved_at.astimezone(UTC).isoformat() if row.approved_at is not None else None,
        "rejected_at": row.rejected_at.astimezone(UTC).isoformat() if row.rejected_at is not None else None,
        "created_at": row.created_at.astimezone(UTC).isoformat() if row.created_at is not None else None,
        "updated_at": row.updated_at.astimezone(UTC).isoformat() if row.updated_at is not None else None,
    }