"""Initial schema baseline.

This migration marks the point at which Alembic discipline was introduced and
creates the baseline schema that existed before revision 0002.

Revision ID: 0001
Revises: —
Create Date: 2026-04-16
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from backend.db.base import Base
import backend.db.models  # noqa: F401 - registers mapped tables on Base.metadata

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOTIFICATIONS_TABLE = "notifications_sent"
_BASELINE_TABLES = {
    "agent_decisions",
    "agent_signals",
    "evaluation_scores",
    "execution_events",
    "movement_journal",
    "portfolio_snapshots",
    "regression_comparisons",
    "replay_cases",
    "replay_results",
    "replay_runs",
    "research_memos",
    "risk_events",
    "strategy_evaluations",
    "system_errors",
    "tool_calls",
    "tradingview_alert_events",
    "tradingview_internal_events",
    "workflow_runs",
    "workflow_steps",
}


def _baseline_metadata() -> sa.MetaData:
    metadata = sa.MetaData()
    for table in Base.metadata.sorted_tables:
        if table.name not in _BASELINE_TABLES:
            continue
        table.to_metadata(metadata)
    return metadata


def upgrade() -> None:
    _baseline_metadata().create_all(bind=op.get_bind())
    op.create_table(
        _NOTIFICATIONS_TABLE,
        sa.Column("sent_time", sa.DateTime(timezone=True), primary_key=True, nullable=False),
        sa.Column("id", sa.String(length=80), primary_key=True, nullable=False),
        sa.Column("channel", sa.String(length=64), nullable=False),
        sa.Column("message_id", sa.String(length=160), nullable=True),
        sa.Column("delivered", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_notifications_sent_channel_time",
        _NOTIFICATIONS_TABLE,
        ["channel", "sent_time"],
    )


def downgrade() -> None:
    op.drop_table(_NOTIFICATIONS_TABLE)
    _baseline_metadata().drop_all(bind=op.get_bind())
