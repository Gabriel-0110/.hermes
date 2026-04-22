"""Initial schema baseline.

This migration marks the point at which Alembic discipline was introduced.
It does NOT re-create tables — the application bootstrap (``ensure_time_series_schema``)
already handles initial table and hypertable creation.

For an existing database (bootstrapped via create_all):
  alembic stamp head

For a fresh database:
  1. Start the application once so bootstrap creates all tables and hypertables.
  2. Run: alembic stamp head
  All future schema changes should then be tracked as Alembic revisions.

Revision ID: 0001
Revises: —
Create Date: 2026-04-16
"""
from __future__ import annotations

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tables are created by ensure_time_series_schema() at application startup.
    # This revision exists solely to establish the Alembic version baseline.
    pass


def downgrade() -> None:
    # No automated downgrade from the initial baseline.
    pass
