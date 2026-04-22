from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from backend.db import HermesTimeSeriesRepository, ensure_time_series_schema, session_scope
from backend.db.session import get_engine
from backend.models import PortfolioState
from backend.trading.models import (
    ExecutionOutcome,
    ExecutionRequest,
    ExecutionResult,
)
from backend.trading.position_manager import (
    apply_execution_outcome_to_portfolio,
    get_position_monitor_snapshot,
)


def _seed_snapshot(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("TRADING_PORTFOLIO_ACCOUNT_ID", "paper")

    ensure_time_series_schema(get_engine())
    with session_scope() as session:
        HermesTimeSeriesRepository(session).insert_portfolio_snapshot(
            account_id="paper",
            total_equity_usd=125000.0,
            cash_usd=45000.0,
            exposure_usd=80000.0,
            positions=[{"symbol": "BTC", "quantity": 1.25, "notional_usd": 80000.0}],
            payload={"source": "exchange_sync", "execution_mode": "live", "positions_count": 1},
            snapshot_time=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
        )


def test_position_monitor_snapshot_reuses_snapshot_metadata(tmp_path, monkeypatch) -> None:
    _seed_snapshot(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "backend.trading.position_manager.get_observability_service",
        lambda: SimpleNamespace(get_execution_event_history=lambda limit=20: []),
    )

    snapshot = get_position_monitor_snapshot()

    assert snapshot.account_id == "paper"
    assert snapshot.state_mode == "live"
    assert snapshot.snapshot_metadata["source"] == "exchange_sync"
    assert snapshot.risk_summary.total_positions == 1
    assert snapshot.position_states[0].symbol == "BTC"
    assert snapshot.position_states[0].execution_mode == "live"


def test_paper_execution_updates_persisted_position_state(tmp_path, monkeypatch) -> None:
    _seed_snapshot(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "backend.trading.position_manager.get_observability_service",
        lambda: SimpleNamespace(get_execution_event_history=lambda limit=20: []),
    )

    outcome = ExecutionOutcome(
        request=ExecutionRequest(
            request_id="exec_req_paper_1",
            symbol="ETH",
            side="buy",
            order_type="market",
            size_usd=2500.0,
            amount=2.0,
        ),
        result=ExecutionResult(
            symbol="ETH",
            order_id=None,
            status="paper_filled",
            success=True,
            execution_mode="paper",
            correlation_id="corr-paper-1",
            workflow_id="wf-paper-1",
            payload={"updated_at": datetime(2026, 4, 16, 12, 0, tzinfo=UTC).isoformat()},
        ),
    )

    updated = apply_execution_outcome_to_portfolio(outcome)

    assert updated is not None
    assert any(position.symbol == "ETH" for position in updated.positions)

    monitor = get_position_monitor_snapshot()

    assert monitor.state_mode == "paper"
    assert monitor.snapshot_metadata["source"] == "execution_projection"
    assert monitor.snapshot_metadata["derived_from_request_id"] == "exec_req_paper_1"
    assert any(position.symbol == "ETH" for position in monitor.position_states)


def test_live_execution_reuses_sync_service_for_position_state(tmp_path, monkeypatch) -> None:
    _seed_snapshot(tmp_path, monkeypatch)

    synced_state = PortfolioState(
        account_id="paper",
        total_equity_usd=126000.0,
        cash_usd=44000.0,
        exposure_usd=82000.0,
        positions=[
            {"symbol": "BTC", "quantity": 1.25, "notional_usd": 80000.0},
            {"symbol": "ETH", "quantity": 1.0, "notional_usd": 2000.0},
        ],
        updated_at=datetime(2026, 4, 16, 12, 0, tzinfo=UTC).isoformat(),
    )

    sync_calls: list[str | None] = []
    monkeypatch.setattr(
        "backend.trading.position_manager.sync_portfolio_from_exchange",
        lambda account_id=None: sync_calls.append(account_id) or synced_state,
    )

    outcome = ExecutionOutcome(
        request=ExecutionRequest(
            request_id="exec_req_live_1",
            symbol="ETH",
            side="buy",
            order_type="market",
            size_usd=2000.0,
            amount=1.0,
        ),
        result=ExecutionResult(
            symbol="ETH",
            order_id="ord-live-1",
            status="filled",
            success=True,
            execution_mode="live",
            correlation_id="corr-live-1",
            workflow_id="wf-live-1",
        ),
    )

    updated = apply_execution_outcome_to_portfolio(outcome)

    assert sync_calls == ["paper"]
    assert updated is not None
    assert updated.total_equity_usd == 126000.0
