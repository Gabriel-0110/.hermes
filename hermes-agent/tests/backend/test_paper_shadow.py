from __future__ import annotations

from datetime import UTC, datetime

from backend.db import HermesTimeSeriesRepository, ensure_time_series_schema, session_scope
from backend.db.session import get_engine
from backend.integrations.execution.mode import (
    schedule_paper_shadow_for_approved_request,
    schedule_paper_shadow_for_request,
)
from backend.trading.models import ExecutionRequest, ExecutionResult


class _ImmediateTimer:
    def __init__(self, delay, fn):
        self.delay = delay
        self.fn = fn
        self.daemon = False

    def start(self):
        self.fn()


def test_schedule_paper_shadow_for_request_records_fill(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_TRADING_MODE", "live")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr("backend.integrations.execution.mode.threading.Timer", _ImmediateTimer)
    monkeypatch.setattr("backend.integrations.execution.mode._fetch_shadow_mid_price", lambda symbol: 101.5)
    monkeypatch.setattr(
        "backend.integrations.execution.mode.next_paper_shadow_fill_at",
        lambda now=None: datetime(2026, 4, 25, 12, 1, tzinfo=UTC),
    )

    request = ExecutionRequest(
        proposal_id="proposal-shadow",
        symbol="BTCUSDT",
        side="buy",
        order_type="market",
        size_usd=1000.0,
        amount=10.0,
        strategy_id="momentum/v1.1",
        strategy_template_id="momentum",
        source_agent="momentum_bot",
    )
    result = ExecutionResult.success_result(
        symbol="BTCUSDT",
        order_id="ord-123",
        execution_mode="live",
        correlation_id="corr-shadow",
        workflow_id="wf-shadow",
        payload={
            "exchange_order": {
                "order_id": "ord-123",
                "average_price": 100.0,
                "price": 100.0,
            }
        },
    )

    scheduled = schedule_paper_shadow_for_request(request, result)

    assert scheduled == ["2026-04-25T12:01:00+00:00"]

    db_path = tmp_path / "state.db"
    ensure_time_series_schema(get_engine(db_path=db_path))
    with session_scope(db_path=db_path) as session:
        rows = HermesTimeSeriesRepository(session).list_paper_shadow_fills(limit=10)

    assert len(rows) == 1
    row = rows[0]
    assert row.symbol == "BTCUSDT"
    assert row.strategy_template_id == "momentum"
    assert row.live_reference_price == 100.0
    assert row.shadow_price == 101.5
    assert row.pnl_divergence_usd == 15.0
    assert row.metadata_json["shadow_stage"] == "execution"


def test_schedule_paper_shadow_for_approved_request_records_fill(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("HERMES_TRADING_MODE", "live")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr("backend.integrations.execution.mode.threading.Timer", _ImmediateTimer)
    monkeypatch.setattr("backend.integrations.execution.mode._fetch_shadow_mid_price", lambda symbol: 99.5)
    monkeypatch.setattr(
        "backend.integrations.execution.mode.next_paper_shadow_fill_at",
        lambda now=None: datetime(2026, 4, 25, 12, 2, tzinfo=UTC),
    )

    request = ExecutionRequest(
        proposal_id="proposal-approved-shadow",
        request_id="exec-approval-shadow",
        symbol="ETHUSDT",
        side="buy",
        order_type="market",
        size_usd=800.0,
        amount=8.0,
        strategy_id="mean_reversion/v1.0",
        strategy_template_id="mean_reversion",
        source_agent="mean_reversion_bot",
    )

    scheduled = schedule_paper_shadow_for_approved_request(
        request,
        correlation_id="corr-approved-shadow",
        workflow_run_id="wf-approved-shadow",
    )

    assert scheduled == ["2026-04-25T12:02:00+00:00"]

    db_path = tmp_path / "state.db"
    ensure_time_series_schema(get_engine(db_path=db_path))
    with session_scope(db_path=db_path) as session:
        rows = HermesTimeSeriesRepository(session).list_paper_shadow_fills(limit=10)

    assert len(rows) == 1
    row = rows[0]
    assert row.symbol == "ETHUSDT"
    assert row.strategy_template_id == "mean_reversion"
    assert row.live_reference_price == 99.5
    assert row.shadow_price == 99.5
    assert row.metadata_json["shadow_stage"] == "approval"