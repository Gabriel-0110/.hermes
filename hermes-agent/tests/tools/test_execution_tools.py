from types import SimpleNamespace

import backend.tools.get_exchange_balances as balances_module
import backend.tools.place_order as place_order_module
from backend.models import ExecutionOrder
from backend.tools.get_exchange_balances import get_exchange_balances
from backend.tools.place_order import place_order
from backend.integrations.execution.mode import (
    LIVE_TRADING_ACK_PHRASE,
    current_trading_mode,
    is_paper_mode,
    live_trading_enabled,
)


def test_get_exchange_balances_fails_safely_without_credentials(monkeypatch):
    monkeypatch.delenv("BITMART_API_KEY", raising=False)
    monkeypatch.delenv("BITMART_SECRET", raising=False)
    monkeypatch.delenv("BITMART_MEMO", raising=False)

    payload = get_exchange_balances({})

    assert payload["meta"]["ok"] is False
    assert payload["data"]["error"] == "provider_not_configured"
    assert payload["meta"]["providers"][0]["provider"] == "BITMART"


def test_place_order_rejects_limit_order_without_price():
    payload = place_order(
        {
            "symbol": "BTC/USDT",
            "side": "buy",
            "order_type": "limit",
            "amount": 0.1,
        }
    )

    assert payload["meta"]["ok"] is False
    assert payload["data"]["error"] == "invalid_input"
    assert "price is required" in payload["data"]["detail"]


def test_get_exchange_balances_can_reconcile_multiple_venues(monkeypatch):
    fake_clients = [
        SimpleNamespace(configured=True, provider=SimpleNamespace(name="BITMART"), credential_env_names=["BITMART_API_KEY"]),
        SimpleNamespace(configured=True, provider=SimpleNamespace(name="BINANCE"), credential_env_names=["BINANCE_API_KEY"]),
    ]

    monkeypatch.setattr(balances_module, "get_execution_clients", lambda **kwargs: fake_clients)
    monkeypatch.setattr(
        balances_module,
        "reconcile_exchange_balances",
        lambda **kwargs: {
            "requested_venues": ["bitmart", "binance"],
            "configured_venues": ["bitmart", "binance"],
            "venue_count": 2,
            "venue_balances": [
                {"exchange": "BITMART", "balances": [{"asset": "BTC", "free": 0.4, "used": 0.1, "total": 0.5}]},
                {"exchange": "BINANCE", "balances": [{"asset": "BTC", "free": 0.2, "used": 0.0, "total": 0.2}]},
            ],
            "aggregate_balances": [{"asset": "BTC", "free": 0.6, "used": 0.1, "total": 0.7, "venues": ["BITMART", "BINANCE"]}],
            "warnings": [],
        },
    )

    payload = get_exchange_balances({"venues": ["bitmart", "binance"], "aggregate": True})

    assert payload["meta"]["ok"] is True
    assert payload["data"]["venue_count"] == 2
    assert payload["data"]["aggregate_balances"][0]["total"] == 0.7


def test_place_order_uses_smart_selected_venue(monkeypatch):
    class FakeVenueClient:
        def __init__(self, venue):
            assert venue == "binance"
            self.provider = SimpleNamespace(name="BINANCE")
            self.credential_env_names = ["BINANCE_API_KEY", "BINANCE_SECRET"]
            self.configured = True

        def place_order(self, **kwargs):
            return ExecutionOrder(
                order_id="ord_123",
                exchange="BINANCE",
                symbol=kwargs["symbol"],
                side=kwargs["side"],
                order_type=kwargs["order_type"],
                amount=kwargs["amount"],
                status="open",
            )

    monkeypatch.setattr(
        place_order_module,
        "select_order_venue",
        lambda **kwargs: {
            "mode": "smart",
            "selected_venue": "binance",
            "selected_provider": "BINANCE",
            "considered": [{"venue": "bitmart", "score": 18.2}, {"venue": "binance", "score": 9.4}],
            "warnings": [],
        },
    )
    monkeypatch.setattr(place_order_module, "VenueExecutionClient", FakeVenueClient)

    payload = place_order(
        {
            "symbol": "BTC/USDT",
            "side": "buy",
            "amount": 0.1,
            "venues": ["bitmart", "binance"],
        }
    )

    assert payload["meta"]["ok"] is True
    assert payload["data"]["exchange"] == "BINANCE"
    assert payload["data"]["routing"]["selected_venue"] == "binance"


def test_execution_mode_defaults_to_paper(monkeypatch):
    monkeypatch.delenv("HERMES_TRADING_MODE", raising=False)
    monkeypatch.delenv("HERMES_PAPER_MODE", raising=False)
    monkeypatch.delenv("HERMES_ENABLE_LIVE_TRADING", raising=False)
    monkeypatch.delenv("HERMES_LIVE_TRADING_ACK", raising=False)

    assert current_trading_mode() == "paper"
    assert is_paper_mode() is True
    assert live_trading_enabled() is False


def test_execution_mode_requires_explicit_live_unlock(monkeypatch):
    monkeypatch.setenv("HERMES_TRADING_MODE", "live")
    monkeypatch.delenv("HERMES_PAPER_MODE", raising=False)
    monkeypatch.setenv("HERMES_ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("HERMES_LIVE_TRADING_ACK", LIVE_TRADING_ACK_PHRASE)

    assert current_trading_mode() == "live"
    assert is_paper_mode() is False
    assert live_trading_enabled() is True
