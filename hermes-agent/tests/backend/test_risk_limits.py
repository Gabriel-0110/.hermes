from __future__ import annotations

from backend.tools.get_risk_state import get_risk_state
from backend.tools.set_kill_switch import set_risk_limits


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, key: str):
        return self.store.get(key)

    def set(self, key: str, value: str):
        self.store[key] = value
        return True


def test_set_risk_limits_persists_symbol_cap_to_database(monkeypatch, tmp_path) -> None:
    fake_redis = FakeRedis()
    db_path = tmp_path / "risk_limits.db"

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr("backend.tools.set_kill_switch.get_redis_client", lambda: fake_redis)
    monkeypatch.setattr("backend.tools.get_risk_state.get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(
        "backend.tools.get_portfolio_state.get_portfolio_state",
        lambda payload=None: {"data": {"total_equity_usd": None}},
    )

    result = set_risk_limits({"symbol": "BTCUSDT", "max_notional_usd": 1250.0, "max_leverage": 3.0})
    assert result["meta"]["ok"] is True
    assert result["data"]["database_persisted"] is True

    state = get_risk_state({})
    assert state["data"]["symbol_limits"]["BTCUSDT"]["max_notional_usd"] == 1250.0
    assert state["data"]["symbol_limits"]["BTCUSDT"]["max_leverage"] == 3.0


def test_set_risk_limits_persists_global_drawdown_limit(monkeypatch, tmp_path) -> None:
    fake_redis = FakeRedis()
    db_path = tmp_path / "risk_limits_global.db"

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr("backend.tools.set_kill_switch.get_redis_client", lambda: fake_redis)
    monkeypatch.setattr("backend.tools.get_risk_state.get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(
        "backend.tools.get_portfolio_state.get_portfolio_state",
        lambda payload=None: {"data": {"total_equity_usd": None}},
    )

    result = set_risk_limits({"drawdown_limit_pct": 8.0})
    assert result["meta"]["ok"] is True

    state = get_risk_state({})
    assert state["data"]["drawdown_limit_pct"] == 8.0