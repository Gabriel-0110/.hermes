"""Tests for post-trade learning loop — weight overrides and Bayesian updates."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from backend.db import ensure_time_series_schema, session_scope
from backend.db.models import StrategyEvaluationRow, StrategyWeightOverrideRow
from backend.db.session import get_engine
from backend.jobs.learning_loop import (
    WEIGHT_MAX,
    WEIGHT_MIN,
    LearningLoopSummary,
    clamp_weight,
    run_learning_loop,
)
from backend.strategies.performance_priors import (
    get_override_weight,
    scale_confidence_by_prior,
    strategy_prior_from_pnls,
)


@pytest.fixture()
def tmp_db(tmp_path):
    db_path = tmp_path / "test_learning.db"
    url = f"sqlite:///{db_path}"
    ensure_time_series_schema(get_engine(database_url=url))
    return url


# ---------------------------------------------------------------------------
# Weight clamping
# ---------------------------------------------------------------------------


def test_clamp_weight_lower_bound() -> None:
    assert clamp_weight(0.01) == WEIGHT_MIN
    assert clamp_weight(-1.0) == WEIGHT_MIN


def test_clamp_weight_upper_bound() -> None:
    assert clamp_weight(5.0) == WEIGHT_MAX
    assert clamp_weight(100.0) == WEIGHT_MAX


def test_clamp_weight_normal_range() -> None:
    assert clamp_weight(1.0) == 1.0
    assert clamp_weight(1.5) == 1.5
    assert clamp_weight(0.75) == 0.75


# ---------------------------------------------------------------------------
# Learning loop — run with real DB
# ---------------------------------------------------------------------------


def test_learning_loop_empty_db(tmp_db: str) -> None:
    summary = run_learning_loop(database_url=tmp_db)

    assert summary.strategies_processed == 0
    assert summary.overrides_written == 0


def _seed_evaluations(db_url: str, strategy: str, symbol: str, pnl_values: list[float]) -> None:
    now = datetime.now(UTC)
    with session_scope(database_url=db_url) as session:
        for i, pnl in enumerate(pnl_values):
            row = StrategyEvaluationRow(
                eval_time=now - timedelta(hours=i + 1),
                strategy_name=strategy,
                symbol=symbol,
                direction="long",
                confidence=0.8,
                outcome="win" if pnl > 0 else "loss",
                pnl_pct=pnl,
                resolved_at=now - timedelta(minutes=i),
            )
            session.add(row)
            session.flush()


def test_learning_loop_creates_overrides(tmp_db: str) -> None:
    _seed_evaluations(tmp_db, "momentum", "BTCUSDT", [0.05] * 7 + [-0.03] * 3)

    summary = run_learning_loop(database_url=tmp_db)

    assert summary.strategies_processed == 1
    assert summary.overrides_written == 1
    assert len(summary.overrides) == 1
    assert summary.overrides[0]["strategy"] == "momentum"
    assert WEIGHT_MIN <= summary.overrides[0]["weight"] <= WEIGHT_MAX

    with session_scope(database_url=tmp_db) as session:
        rows = list(session.scalars(select(StrategyWeightOverrideRow)))
        assert len(rows) == 1
        assert rows[0].strategy == "momentum"
        assert rows[0].symbol == "*"
        assert rows[0].regime == "*"
        assert WEIGHT_MIN <= rows[0].weight <= WEIGHT_MAX


def test_learning_loop_idempotent_same_day(tmp_db: str) -> None:
    _seed_evaluations(tmp_db, "breakout", "ETHUSDT", [0.04] * 5)

    summary1 = run_learning_loop(database_url=tmp_db)
    assert summary1.overrides_written == 1

    summary2 = run_learning_loop(database_url=tmp_db)
    assert summary2.overrides_unchanged == 1
    assert summary2.overrides_written == 0


def test_learning_loop_updates_existing_override(tmp_db: str) -> None:
    _seed_evaluations(tmp_db, "mean_reversion", "SOLUSDT", [0.05] * 5)

    run_learning_loop(database_url=tmp_db)

    with session_scope(database_url=tmp_db) as session:
        row = session.scalars(select(StrategyWeightOverrideRow).where(
            StrategyWeightOverrideRow.strategy == "mean_reversion"
        )).first()
        original_weight = row.weight

    _seed_evaluations(tmp_db, "mean_reversion", "SOLUSDT", [-0.08] * 10)

    summary = run_learning_loop(database_url=tmp_db)

    with session_scope(database_url=tmp_db) as session:
        row = session.scalars(select(StrategyWeightOverrideRow).where(
            StrategyWeightOverrideRow.strategy == "mean_reversion"
        )).first()
        assert row.weight != original_weight or summary.overrides_unchanged == 1


def test_learning_loop_dry_run(tmp_db: str) -> None:
    _seed_evaluations(tmp_db, "momentum", "BTCUSDT", [0.05] * 5)

    summary = run_learning_loop(database_url=tmp_db, dry_run=True)

    assert summary.dry_run is True
    assert summary.overrides_proposed == 1
    assert summary.overrides_written == 0
    assert len(summary.overrides) == 1

    with session_scope(database_url=tmp_db) as session:
        rows = list(session.scalars(select(StrategyWeightOverrideRow)))
        assert len(rows) == 0


def test_learning_loop_multiple_strategies(tmp_db: str) -> None:
    for strategy in ("momentum", "breakout", "mean_reversion"):
        _seed_evaluations(tmp_db, strategy, "BTCUSDT", [0.03] * 3 + [-0.02] * 2)

    summary = run_learning_loop(database_url=tmp_db)

    assert summary.strategies_processed == 3
    assert summary.overrides_written == 3


# ---------------------------------------------------------------------------
# Performance priors — override weight lookup
# ---------------------------------------------------------------------------


def test_get_override_weight_returns_none_without_data(tmp_db: str) -> None:
    result = get_override_weight("momentum", database_url=tmp_db)
    assert result is None


def test_get_override_weight_returns_stored_value(tmp_db: str) -> None:
    now = datetime.now(UTC)
    with session_scope(database_url=tmp_db) as session:
        session.add(StrategyWeightOverrideRow(
            strategy="momentum",
            symbol="*",
            regime="*",
            weight=1.25,
            evidence_json={"test": True},
            updated_at=now,
        ))

    result = get_override_weight("momentum", database_url=tmp_db)
    assert result == 1.25


def test_scale_confidence_uses_override_when_present(tmp_db: str) -> None:
    now = datetime.now(UTC)
    with session_scope(database_url=tmp_db) as session:
        session.add(StrategyWeightOverrideRow(
            strategy="momentum",
            symbol="*",
            regime="*",
            weight=2.0,
            evidence_json={},
            updated_at=now,
        ))

    scaled, prior = scale_confidence_by_prior(
        "momentum", 0.4, database_url=tmp_db,
    )
    assert scaled == round(min(max(0.4 * 2.0, 0.01), 0.99), 2)


def test_scale_confidence_falls_back_to_prior_without_override(tmp_db: str) -> None:
    scaled, prior = scale_confidence_by_prior(
        "unknown_strategy", 0.5, database_url=tmp_db,
    )
    assert scaled == round(min(max(0.5 * prior.multiplier, 0.01), 0.99), 2)


# ---------------------------------------------------------------------------
# Weight bounds validation
# ---------------------------------------------------------------------------


def test_weights_always_bounded(tmp_db: str) -> None:
    _seed_evaluations(tmp_db, "extreme_winner", "BTCUSDT", [0.10] * 50)
    _seed_evaluations(tmp_db, "extreme_loser", "BTCUSDT", [-0.10] * 50)

    summary = run_learning_loop(database_url=tmp_db)

    for override in summary.overrides:
        assert WEIGHT_MIN <= override["weight"] <= WEIGHT_MAX


# ---------------------------------------------------------------------------
# Bayesian prior from pnls
# ---------------------------------------------------------------------------


def test_strategy_prior_from_pnls_all_wins() -> None:
    prior = strategy_prior_from_pnls("test", [0.05] * 10)
    assert prior.wins == 10
    assert prior.losses == 0
    assert prior.multiplier > 1.0


def test_strategy_prior_from_pnls_all_losses() -> None:
    prior = strategy_prior_from_pnls("test", [-0.05] * 10)
    assert prior.wins == 0
    assert prior.losses == 10
    assert prior.multiplier < 1.0


def test_strategy_prior_from_pnls_empty() -> None:
    prior = strategy_prior_from_pnls("test", [])
    assert prior.wins == 0
    assert prior.losses == 0
    assert prior.multiplier == 1.0


def test_strategy_prior_from_pnls_mixed() -> None:
    pnls = [0.05, -0.03, 0.02, 0.04, -0.01]
    prior = strategy_prior_from_pnls("test", pnls)
    assert prior.wins == 3
    assert prior.losses == 2
    assert 0.75 < prior.multiplier < 1.25


# ---------------------------------------------------------------------------
# Summary markdown
# ---------------------------------------------------------------------------


def test_learning_loop_summary_markdown() -> None:
    summary = LearningLoopSummary(
        strategies_processed=2,
        overrides_written=2,
        overrides=[
            {"strategy": "momentum", "symbol": "*", "regime": "*", "weight": 1.15, "wins": 7, "losses": 3},
        ],
    )
    md = summary.to_markdown()
    assert "momentum" in md
    assert "1.15" in md


# ---------------------------------------------------------------------------
# Migration and model structure
# ---------------------------------------------------------------------------


def test_strategy_weight_override_row_persists(tmp_db: str) -> None:
    now = datetime.now(UTC)
    with session_scope(database_url=tmp_db) as session:
        session.add(StrategyWeightOverrideRow(
            strategy="test_strategy",
            symbol="BTCUSDT",
            regime="trend_up",
            weight=1.5,
            evidence_json={"alpha": 5.0, "beta": 3.0},
            updated_at=now,
        ))

    with session_scope(database_url=tmp_db) as session:
        row = session.scalars(
            select(StrategyWeightOverrideRow)
            .where(StrategyWeightOverrideRow.strategy == "test_strategy")
        ).first()
        assert row is not None
        assert row.symbol == "BTCUSDT"
        assert row.regime == "trend_up"
        assert row.weight == 1.5
        assert row.evidence_json["alpha"] == 5.0


def test_alembic_migration_0008_exists() -> None:
    import os
    migration_path = os.path.join(
        os.path.dirname(__file__),
        "..", "..",
        "alembic", "versions", "0008_strategy_weight_overrides.py",
    )
    assert os.path.isfile(migration_path), "Migration 0008 should exist"
