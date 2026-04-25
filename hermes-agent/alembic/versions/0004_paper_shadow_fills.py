"""Add paper_shadow_fills table.

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-25
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "paper_shadow_fills"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("fill_time", sa.DateTime(timezone=True), primary_key=True, nullable=False),
        sa.Column("id", sa.String(length=120), primary_key=True, nullable=False),
        sa.Column("proposal_id", sa.String(length=120), nullable=True),
        sa.Column("request_id", sa.String(length=120), nullable=True),
        sa.Column("leg_id", sa.String(length=120), nullable=True),
        sa.Column("correlation_id", sa.String(length=120), nullable=True),
        sa.Column("workflow_run_id", sa.String(length=120), nullable=True),
        sa.Column("strategy_id", sa.String(length=160), nullable=True),
        sa.Column("strategy_template_id", sa.String(length=160), nullable=True),
        sa.Column("source_agent", sa.String(length=120), nullable=True),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("side", sa.String(length=32), nullable=False),
        sa.Column("execution_style", sa.String(length=32), nullable=False, server_default="single"),
        sa.Column("live_order_id", sa.String(length=160), nullable=True),
        sa.Column("live_reference_price", sa.Float(), nullable=True),
        sa.Column("shadow_price", sa.Float(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("live_notional_usd", sa.Float(), nullable=True),
        sa.Column("shadow_notional_usd", sa.Float(), nullable=True),
        sa.Column("pnl_divergence_usd", sa.Float(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_paper_shadow_fills_strategy_time", _TABLE, ["strategy_template_id", "fill_time"])
    op.create_index("ix_paper_shadow_fills_symbol_time", _TABLE, ["symbol", "fill_time"])
    op.create_index("ix_paper_shadow_fills_request_time", _TABLE, ["request_id", "fill_time"])
    op.create_index("ix_paper_shadow_fills_correlation_time", _TABLE, ["correlation_id", "fill_time"])


def downgrade() -> None:
    op.drop_index("ix_paper_shadow_fills_correlation_time", table_name=_TABLE)
    op.drop_index("ix_paper_shadow_fills_request_time", table_name=_TABLE)
    op.drop_index("ix_paper_shadow_fills_symbol_time", table_name=_TABLE)
    op.drop_index("ix_paper_shadow_fills_strategy_time", table_name=_TABLE)
    op.drop_table(_TABLE)