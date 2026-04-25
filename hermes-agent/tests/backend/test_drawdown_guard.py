from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from backend.db import HermesTimeSeriesRepository, ensure_time_series_schema, session_scope
from backend.db.session import get_engine
from backend.jobs.drawdown_guard import run_drawdown_guard


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, key: str):
        return self.store.get(key)

    def set(self, key: str, value: str):
        self.store[key] = value
        return True


def test_drawdown_guard_trips_kill_switch_and_sends_alert(monkeypatch, tmp_path) -> None:
    fake_redis = FakeRedis()
    kill_switch_calls: list[dict[str, object]] = []
    notification_calls: list[dict[str, object]] = []
    db_path = tmp_path / "drawdown_guard.db"

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr("backend.jobs.drawdown_guard.get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(
        "backend.jobs.drawdown_guard.set_kill_switch",
        lambda payload: kill_switch_calls.append(payload) or {"data": {"success": True}},
    )
    monkeypatch.setattr(
        "backend.jobs.drawdown_guard.send_notification",
        lambda payload: notification_calls.append(payload) or {"data": {"delivered": True}},
    )
    monkeypatch.setattr("backend.jobs.drawdown_guard._configured_drawdown_limit", lambda default=8.0: 8.0)

    ensure_time_series_schema(get_engine())
    now = datetime.now(UTC)
    with session_scope() as session:
        repo = HermesTimeSeriesRepository(session)
        repo.insert_portfolio_snapshot(
            account_id="paper",
            total_equity_usd=1000.0,
            cash_usd=1000.0,
            exposure_usd=0.0,
            positions=[],
            snapshot_time=now - timedelta(days=3),
        )
        repo.insert_portfolio_snapshot(
            account_id="paper",
            total_equity_usd=900.0,
            cash_usd=900.0,
            exposure_usd=0.0,
            positions=[],
            snapshot_time=now,
        )

    summary = run_drawdown_guard(account_id="paper")

    assert summary.breached is True
    assert summary.kill_switch_set is True
    assert summary.notification_delivered is True
    assert kill_switch_calls and kill_switch_calls[0]["active"] is True
    assert notification_calls and notification_calls[0]["channel"] == "telegram"

    peak_payload = json.loads(fake_redis.store["hermes:risk:equity_peak"])
    assert peak_payload["equity"] == 1000.0