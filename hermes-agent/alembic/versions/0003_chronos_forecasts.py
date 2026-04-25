"""Add chronos_forecasts cache table.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-25
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "chronos_forecasts"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("forecast_time", sa.DateTime(timezone=True), primary_key=True, nullable=False),
        sa.Column("id", sa.String(length=80), primary_key=True, nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("interval", sa.String(length=32), nullable=False),
        sa.Column("horizon", sa.Integer(), nullable=False),
        sa.Column("latest_price", sa.Float(), nullable=True),
        sa.Column("median_price", sa.Float(), nullable=True),
        sa.Column("low_price", sa.Float(), nullable=True),
        sa.Column("high_price", sa.Float(), nullable=True),
        sa.Column("projected_return", sa.Float(), nullable=True),
        sa.Column("forecast_model", sa.String(length=120), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_chronos_forecasts_symbol_interval_time",
        _TABLE,
        ["symbol", "interval", "forecast_time"],
    )
    op.create_index(
        "ix_chronos_forecasts_symbol_horizon_time",
        _TABLE,
        ["symbol", "horizon", "forecast_time"],
    )


def downgrade() -> None:
    op.drop_index("ix_chronos_forecasts_symbol_horizon_time", table_name=_TABLE)
    op.drop_index("ix_chronos_forecasts_symbol_interval_time", table_name=_TABLE)
    op.drop_table(_TABLE)
