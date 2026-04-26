"""strategy_weight_overrides table for learned weight adjustments.

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-26 22:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategy_weight_overrides",
        sa.Column("id", sa.String(length=80), primary_key=True, nullable=False),
        sa.Column("strategy", sa.String(length=120), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False, server_default="*"),
        sa.Column("regime", sa.String(length=32), nullable=False, server_default="*"),
        sa.Column("weight", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("evidence_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index(
        "ix_strategy_weight_overrides_lookup",
        "strategy_weight_overrides",
        ["strategy", "symbol", "regime"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_strategy_weight_overrides_lookup", table_name="strategy_weight_overrides")
    op.drop_table("strategy_weight_overrides")
