from __future__ import annotations

from datetime import UTC, datetime

from backend.db import HermesTimeSeriesRepository, ensure_time_series_schema, session_scope
from backend.db.session import get_engine, normalize_database_url
from backend.tools import get_portfolio_state as get_portfolio_state_module
from backend.tools.get_portfolio_state import get_portfolio_state
from backend.tools.send_notification import send_notification
from backend.tradingview.service import TradingViewIngestionService
from backend.tradingview.store import TradingViewStore


def test_tradingview_store_honors_explicit_sqlite_fallback_when_database_url_is_set(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://hermes:hermes@timescaledb:5432/hermes_trading")

    service = TradingViewIngestionService(db_path=tmp_path / "state.db")
    result = service.ingest(
        body=b'{"symbol":"BTCUSDT","signal":"entry","direction":"buy"}',
        content_type="application/json",
    )

    store = TradingViewStore(db_path=tmp_path / "state.db")
    alerts = store.list_alerts(limit=5, symbol="BTCUSDT")

    assert store.backend == "sqlite_fallback"
    assert result.alert.id == alerts[0]["id"]


def test_normalize_database_url_prefers_psycopg_driver():
    assert normalize_database_url("postgresql://user:pass@db:5432/hermes") == "postgresql+psycopg://user:pass@db:5432/hermes"
    assert normalize_database_url("postgres://user:pass@db:5432/hermes") == "postgresql+psycopg://user:pass@db:5432/hermes"
    assert normalize_database_url("postgresql+psycopg://user:pass@db:5432/hermes") == "postgresql+psycopg://user:pass@db:5432/hermes"


def test_get_portfolio_state_reads_latest_shared_snapshot(tmp_path, monkeypatch):
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
            positions=[{"symbol": "BTC", "quantity": 1.25}],
            snapshot_time=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
        )

    payload = get_portfolio_state()

    assert payload["meta"]["ok"] is True
    assert payload["meta"]["warnings"] == []
    assert payload["data"]["account_id"] == "paper"
    assert payload["data"]["total_equity_usd"] == 125000.0
    assert payload["data"]["positions"][0]["symbol"] == "BTC"


def test_get_portfolio_state_reconciles_only_when_explicitly_requested(tmp_path, monkeypatch):
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
            positions=[{"symbol": "BTC", "quantity": 1.25}],
            snapshot_time=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
        )

    reconcile_calls: list[dict] = []

    def _fake_reconcile_exchange_balances(*, venue=None, venues=None):
        reconcile_calls.append({"venue": venue, "venues": venues})
        return {
            "configured_venues": ["bitmart"],
            "aggregate_balances": [{"asset": "BTC", "total": 1.25}],
            "warnings": ["bitmart credentials are not configured."],
        }

    monkeypatch.setattr(
        get_portfolio_state_module,
        "reconcile_exchange_balances",
        _fake_reconcile_exchange_balances,
    )

    passive_payload = get_portfolio_state()

    assert passive_payload["meta"]["warnings"] == []
    assert "reconciliation" not in passive_payload["data"]
    assert reconcile_calls == []

    explicit_payload = get_portfolio_state({"include_exchange_balances": True})

    assert reconcile_calls == [{"venue": None, "venues": None}]
    assert explicit_payload["data"]["reconciliation"]["configured_venues"] == ["bitmart"]
    assert explicit_payload["meta"]["warnings"] == ["bitmart credentials are not configured."]


def test_send_notification_writes_notifications_sent_record(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("TRADING_NOTIFICATION_BACKEND", "log")

    payload = send_notification({"channel": "log", "message": "risk limit breached"})

    assert payload["meta"]["ok"] is True
    assert payload["data"]["channel"] == "log"

    ensure_time_series_schema(get_engine())
    with session_scope() as session:
        rows = HermesTimeSeriesRepository(session).list_notifications_sent(limit=5, channel="log")

    assert len(rows) == 1
    assert rows[0].payload["message"] == "risk limit breached"
