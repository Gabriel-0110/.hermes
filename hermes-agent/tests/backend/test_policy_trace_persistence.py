"""Tests for policy trace persistence and the /api/policy/traces endpoint."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import desc, select

from backend.db import ensure_time_series_schema, session_scope
from backend.db.models import PolicyTraceRow
from backend.db.session import get_engine
from backend.trading.models import PolicyDecision, RiskRejectionReason
from backend.trading.policy_engine import persist_policy_trace


@pytest.fixture()
def tmp_db(tmp_path):
    db_path = tmp_path / "test_traces.db"
    url = f"sqlite:///{db_path}"
    ensure_time_series_schema(get_engine(database_url=url))
    return url


# ---------------------------------------------------------------------------
# persist_policy_trace
# ---------------------------------------------------------------------------


def _mock_db(monkeypatch: pytest.MonkeyPatch, tmp_db: str) -> None:
    monkeypatch.setenv("DATABASE_URL", tmp_db)


def test_persist_policy_trace_stores_decision(tmp_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_db(monkeypatch, tmp_db)

    decision = PolicyDecision(
        proposal_id="prop-001",
        status="approved",
        execution_mode="paper",
        approved=True,
        approved_size_usd=1000.0,
        requires_operator_approval=False,
        policy_trace=["execution_mode=paper", "risk_gate=approved", "regime=trend_up"],
        rejection_reasons=[],
    )

    persist_policy_trace(decision, symbol="BTCUSDT")

    with session_scope(database_url=tmp_db) as session:
        rows = list(session.scalars(select(PolicyTraceRow)))
        assert len(rows) == 1
        row = rows[0]
        assert row.proposal_id == "prop-001"
        assert row.status == "approved"
        assert row.execution_mode == "paper"
        assert row.approved is True
        assert row.symbol == "BTCUSDT"
        assert "execution_mode=paper" in row.trace
        assert "risk_gate=approved" in row.trace


def test_persist_policy_trace_stores_rejection(tmp_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_db(monkeypatch, tmp_db)

    decision = PolicyDecision(
        proposal_id="prop-002",
        status="rejected",
        execution_mode="paper",
        approved=False,
        approved_size_usd=0.0,
        requires_operator_approval=False,
        policy_trace=["execution_mode=paper", "regime=range", "regime_gate=rejected"],
        rejection_reasons=[RiskRejectionReason.REGIME_MISMATCH],
    )

    persist_policy_trace(decision, symbol="ETHUSDT")

    with session_scope(database_url=tmp_db) as session:
        row = session.scalars(select(PolicyTraceRow)).first()
        assert row is not None
        assert row.status == "rejected"
        assert row.approved is False
        assert "regime_mismatch" in row.rejection_reasons


def test_persist_policy_trace_tolerates_db_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///nonexistent/path/db.sqlite")

    decision = PolicyDecision(
        proposal_id="prop-003",
        status="approved",
        execution_mode="paper",
        approved=True,
        approved_size_usd=500.0,
        requires_operator_approval=False,
    )

    persist_policy_trace(decision, symbol="BTCUSDT")


def test_persist_multiple_traces(tmp_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_db(monkeypatch, tmp_db)

    for i in range(5):
        decision = PolicyDecision(
            proposal_id=f"prop-{i:03d}",
            status="approved" if i % 2 == 0 else "rejected",
            execution_mode="paper",
            approved=i % 2 == 0,
            approved_size_usd=1000.0 if i % 2 == 0 else 0.0,
            requires_operator_approval=False,
            policy_trace=[f"test_entry_{i}"],
        )
        persist_policy_trace(decision, symbol="BTCUSDT")

    with session_scope(database_url=tmp_db) as session:
        rows = list(session.scalars(select(PolicyTraceRow)))
        assert len(rows) == 5


# ---------------------------------------------------------------------------
# PolicyTraceRow model
# ---------------------------------------------------------------------------


def test_policy_trace_row_persists(tmp_db: str) -> None:
    with session_scope(database_url=tmp_db) as session:
        session.add(PolicyTraceRow(
            proposal_id="test-prop",
            status="manual_review",
            execution_mode="live",
            approved=True,
            symbol="SOLUSDT",
            decision_json={"test": True},
            trace=["step1", "step2"],
            rejection_reasons=["approval_required"],
        ))

    with session_scope(database_url=tmp_db) as session:
        row = session.scalars(select(PolicyTraceRow)).first()
        assert row is not None
        assert row.proposal_id == "test-prop"
        assert row.status == "manual_review"
        assert row.trace == ["step1", "step2"]
        assert row.created_at is not None


# ---------------------------------------------------------------------------
# Migration existence
# ---------------------------------------------------------------------------


def test_alembic_migration_0009_exists() -> None:
    import os
    migration_path = os.path.join(
        os.path.dirname(__file__),
        "..", "..",
        "alembic", "versions", "0009_policy_traces.py",
    )
    assert os.path.isfile(migration_path)
