"""operator_snapshots table for imported operator balance state.

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-26 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operator_snapshots",
        sa.Column("id", sa.String(length=80), primary_key=True, nullable=False),
        sa.Column("exchange", sa.String(length=64), nullable=False),
        sa.Column("as_of_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_equity_usd", sa.Float(), nullable=True),
        sa.Column("available_usd", sa.Float(), nullable=True),
        sa.Column("invested_usd", sa.Float(), nullable=True),
        sa.Column("unrealized_pnl_usd", sa.Float(), nullable=True),
        sa.Column("raw_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("divergence_summary", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_operator_snapshots_exchange_time", "operator_snapshots", ["exchange", "as_of_utc"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_operator_snapshots_exchange_time", table_name="operator_snapshots")
    op.drop_table("operator_snapshots")
