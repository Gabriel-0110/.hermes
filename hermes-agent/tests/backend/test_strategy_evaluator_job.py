from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from backend.db import HermesTimeSeriesRepository, ensure_time_series_schema, session_scope
from backend.db.models import StrategyEvaluationRow
from backend.db.session import get_engine
from backend.jobs.strategy_evaluator import run_strategy_evaluator
from backend.strategies.performance_priors import clear_strategy_prior_cache, get_strategy_prior


def test_strategy_evaluator_resolves_rows_and_updates_bayesian_prior(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'strategy_eval.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    ensure_time_series_schema(get_engine(database_url=database_url))

    t0 = datetime.now(UTC) - timedelta(hours=12)
    with session_scope(database_url=database_url) as session:
        repo = HermesTimeSeriesRepository(session)
        session.add(
            StrategyEvaluationRow(
                eval_time=t0,
                strategy_name="momentum",
                strategy_version="1.1.0",
                symbol="BTC",
                timeframe="4h",
                direction="long",
                confidence=0.71,
                rationale="test candidate",
                metadata_json={"proposal_id": "proposal_eval_1", "source_agent": "momentum_bot"},
            )
        )
        repo.insert_agent_signal(
            agent_id="momentum_bot",
            symbol="BTC",
            signal_type="momentum",
            direction="long",
            confidence=0.71,
            payload={
                "proposal_id": "proposal_eval_1",
                "strategy_name": "momentum",
                "source_agent": "momentum_bot",
            },
            signal_time=t0,
        )
        repo.insert_execution_event(
            workflow_run_id="proposal::proposal_eval_1",
            event_id="evt_eval_1",
            correlation_id="proposal_eval_1",
            status="filled",
            event_type="order_placed",
            summarized_input=json.dumps(
                {
                    "execution_request": {
                        "proposal_id": "proposal_eval_1",
                        "symbol": "BTC",
                        "side": "buy",
                        "price": 100.0,
                        "size_usd": 50.0,
                    }
                }
            ),
            summarized_output=json.dumps({"execution_result": {"status": "filled", "success": True}}),
            metadata={"proposal_id": "proposal_eval_1"},
            created_at=t0 + timedelta(minutes=5),
        )
        repo.insert_portfolio_snapshot(
            account_id="paper",
            total_equity_usd=10_100.0,
            cash_usd=5_000.0,
            exposure_usd=5_100.0,
            positions=[
                {
                    "symbol": "BTC",
                    "quantity": 0.5,
                    "avg_entry": 100.0,
                    "mark_price": 110.0,
                    "notional_usd": 55.0,
                    "pnl_unrealized": 5.0,
                }
            ],
            snapshot_time=t0 + timedelta(hours=12),
        )

    summary = run_strategy_evaluator(database_url=database_url, account_id="paper", lookback_hours=48)

    assert summary.updated_rows == 1
    assert "momentum" in summary.priors
    assert summary.priors["momentum"]["wins"] == 1

    with session_scope(database_url=database_url) as session:
        row = session.scalars(
            select(StrategyEvaluationRow).where(StrategyEvaluationRow.strategy_name == "momentum")
        ).one()

    assert row.outcome == "win"
    assert row.pnl_pct == pytest.approx(0.10, rel=1e-3)
    assert row.metadata_json["strategy_prior"]["multiplier"] > 1.0

    clear_strategy_prior_cache()
    prior = get_strategy_prior("momentum", database_url=database_url)
    assert prior.resolved_count == 1
    assert prior.multiplier > 1.0
