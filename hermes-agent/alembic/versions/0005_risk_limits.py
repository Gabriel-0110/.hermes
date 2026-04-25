"""risk_limits table for persisted position and leverage caps.

Revision ID: 0005_risk_limits
Revises: 0004_paper_shadow_fills
Create Date: 2026-04-25 11:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005_risk_limits"
down_revision = "0004_paper_shadow_fills"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "risk_limits",
        sa.Column("scope", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("max_position_usd", sa.Float(), nullable=True),
        sa.Column("max_notional_usd", sa.Float(), nullable=True),
        sa.Column("max_leverage", sa.Float(), nullable=True),
        sa.Column("max_daily_loss_usd", sa.Float(), nullable=True),
        sa.Column("drawdown_limit_pct", sa.Float(), nullable=True),
        sa.Column("carry_trade_max_equity_pct", sa.Float(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_risk_limits_updated_at", "risk_limits", ["updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_risk_limits_updated_at", table_name="risk_limits")
    op.drop_table("risk_limits")