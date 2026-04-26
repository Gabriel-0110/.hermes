"""policy_traces table for persisted policy decision audit trail.

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-26 23:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "policy_traces",
        sa.Column("id", sa.String(length=80), primary_key=True, nullable=False),
        sa.Column("proposal_id", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("execution_mode", sa.String(length=16), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=True),
        sa.Column("decision_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("trace", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("rejection_reasons", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_policy_traces_proposal_id", "policy_traces", ["proposal_id"], unique=False)
    op.create_index("ix_policy_traces_created_at", "policy_traces", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_policy_traces_created_at", table_name="policy_traces")
    op.drop_index("ix_policy_traces_proposal_id", table_name="policy_traces")
    op.drop_table("policy_traces")
