"""Add retry tracking columns to notifications_sent.

Adds three nullable columns to support persistent retry state:
  - retry_count   INTEGER NOT NULL DEFAULT 0
  - next_retry_at TIMESTAMPTZ       NULL
  - last_error    TEXT              NULL

Also adds indexes for efficient retry-queue queries:
  - ix_notifications_sent_delivered_time  (delivered, sent_time)
  - ix_notifications_sent_retry_time      (next_retry_at, sent_time)

Existing rows get retry_count=0, next_retry_at=NULL, last_error=NULL.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-16
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "notifications_sent"


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # Add columns (safe to run against existing table; uses server default)
    op.add_column(
        _TABLE,
        sa.Column(
            "retry_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "next_retry_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "last_error",
            sa.Text(),
            nullable=True,
        ),
    )

    # Add supporting indexes
    # TimescaleDB hypertables support regular B-tree indexes.
    op.create_index(
        "ix_notifications_sent_delivered_time",
        _TABLE,
        ["delivered", "sent_time"],
    )
    op.create_index(
        "ix_notifications_sent_retry_time",
        _TABLE,
        ["next_retry_at", "sent_time"],
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_sent_retry_time", table_name=_TABLE)
    op.drop_index("ix_notifications_sent_delivered_time", table_name=_TABLE)
    op.drop_column(_TABLE, "last_error")
    op.drop_column(_TABLE, "next_retry_at")
    op.drop_column(_TABLE, "retry_count")
