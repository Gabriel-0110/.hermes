"""Add copy-trader curator score and proposal tables.

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-25
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCORES_TABLE = "copy_trader_scores"
_PROPOSALS_TABLE = "copy_trader_switch_proposals"


def upgrade() -> None:
    op.create_table(
        _SCORES_TABLE,
        sa.Column("score_time", sa.DateTime(timezone=True), primary_key=True, nullable=False),
        sa.Column("id", sa.String(length=120), primary_key=True, nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="bitmart_aihub"),
        sa.Column("snapshot_ref", sa.String(length=120), nullable=True),
        sa.Column("trader_id", sa.String(length=160), nullable=False),
        sa.Column("trader_name", sa.String(length=200), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("score_percentile", sa.Float(), nullable=False),
        sa.Column("sharpe_30d", sa.Float(), nullable=True),
        sa.Column("max_drawdown_pct_30d", sa.Float(), nullable=True),
        sa.Column("fee_pct", sa.Float(), nullable=True),
        sa.Column("is_active_master", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_copy_trader_scores_trader_time", _SCORES_TABLE, ["trader_id", "score_time"])
    op.create_index("ix_copy_trader_scores_rank_time", _SCORES_TABLE, ["rank", "score_time"])
    op.create_index("ix_copy_trader_scores_active_time", _SCORES_TABLE, ["is_active_master", "score_time"])

    op.create_table(
        _PROPOSALS_TABLE,
        sa.Column("id", sa.String(length=120), primary_key=True, nullable=False),
        sa.Column("active_trader_id", sa.String(length=160), nullable=False),
        sa.Column("active_trader_name", sa.String(length=200), nullable=False),
        sa.Column("candidate_trader_id", sa.String(length=160), nullable=True),
        sa.Column("candidate_trader_name", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("active_score", sa.Float(), nullable=True),
        sa.Column("active_percentile", sa.Float(), nullable=True),
        sa.Column("candidate_score", sa.Float(), nullable=True),
        sa.Column("candidate_percentile", sa.Float(), nullable=True),
        sa.Column("threshold_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("delivery_channel", sa.String(length=64), nullable=True),
        sa.Column("notification_message_id", sa.String(length=160), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("operator", sa.String(length=120), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_copy_trader_switch_proposals_active_time",
        _PROPOSALS_TABLE,
        ["active_trader_id", "created_at"],
    )
    op.create_index(
        "ix_copy_trader_switch_proposals_status_time",
        _PROPOSALS_TABLE,
        ["status", "created_at"],
    )
    op.create_index(
        "ix_copy_trader_switch_proposals_candidate_time",
        _PROPOSALS_TABLE,
        ["candidate_trader_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_copy_trader_switch_proposals_candidate_time", table_name=_PROPOSALS_TABLE)
    op.drop_index("ix_copy_trader_switch_proposals_status_time", table_name=_PROPOSALS_TABLE)
    op.drop_index("ix_copy_trader_switch_proposals_active_time", table_name=_PROPOSALS_TABLE)
    op.drop_table(_PROPOSALS_TABLE)

    op.drop_index("ix_copy_trader_scores_active_time", table_name=_SCORES_TABLE)
    op.drop_index("ix_copy_trader_scores_rank_time", table_name=_SCORES_TABLE)
    op.drop_index("ix_copy_trader_scores_trader_time", table_name=_SCORES_TABLE)
    op.drop_table(_SCORES_TABLE)