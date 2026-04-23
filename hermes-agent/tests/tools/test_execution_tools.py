import json
from types import SimpleNamespace

import backend.tools.get_exchange_balances as balances_module
import backend.tools.place_order as place_order_module
import backend.integrations.execution.multi_venue as multi_venue_module
from backend.integrations.execution.normalization import execution_order_payload, normalize_ccxt_order
from backend.integrations.execution.multi_venue import VenueExecutionClient
from backend.models import ExecutionOrder
from backend.tools.get_exchange_balances import get_exchange_balances
from backend.tools.place_order import place_order
from backend.trading.models import ExecutionOutcome, ExecutionRequest, ExecutionResult
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
                reduce_only=kwargs.get("reduce_only"),
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
    monkeypatch.setattr(
        place_order_module,
        "evaluate_execution_safety",
        lambda approval_id=None: SimpleNamespace(
            execution_mode="live",
            blockers=[],
            kill_switch_active=False,
            kill_switch_reason=None,
            approval_required=False,
        ),
    )

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
    assert payload["data"]["execution_request"]["symbol"] == "BTC/USDT"
    assert payload["data"]["execution_result"]["status"] == "filled"
    assert payload["data"]["execution_result"]["execution_mode"] == "live"
    assert payload["data"]["execution_result"]["payload"]["exchange_order"]["exchange"] == "BINANCE"
    assert payload["data"]["execution_result"]["payload"]["exchange_order"]["routing"]["selected_venue"] == "binance"


def test_place_order_passes_reduce_only_futures_close_flags(monkeypatch):
    captured: dict[str, object] = {}

    class FakeVenueClient:
        def __init__(self, venue):
            assert venue == "bitmart"
            self.provider = SimpleNamespace(name="BITMART")
            self.credential_env_names = ["BITMART_API_KEY", "BITMART_SECRET", "BITMART_MEMO"]
            self.configured = True

        def place_order(self, **kwargs):
            captured.update(kwargs)
            return ExecutionOrder(
                order_id="ord_close_123",
                exchange="BITMART",
                symbol=kwargs["symbol"],
                side=kwargs["side"],
                order_type=kwargs["order_type"],
                amount=kwargs["amount"],
                reduce_only=kwargs.get("reduce_only"),
                status="open",
            )

    monkeypatch.setattr(
        place_order_module,
        "select_order_venue",
        lambda **kwargs: {
            "mode": "single_venue",
            "selected_venue": "bitmart",
            "selected_provider": "BITMART",
            "considered": [{"venue": "bitmart", "score": 0.0}],
            "warnings": [],
        },
    )
    monkeypatch.setattr(place_order_module, "VenueExecutionClient", FakeVenueClient)
    monkeypatch.setattr(
        place_order_module,
        "evaluate_execution_safety",
        lambda approval_id=None: SimpleNamespace(
            execution_mode="live",
            blockers=[],
            kill_switch_active=False,
            kill_switch_reason=None,
            approval_required=False,
        ),
    )

    payload = place_order(
        {
            "symbol": "BTCUSDT",
            "side": "sell",
            "order_type": "market",
            "amount": 1,
            "close_only": True,
            "position_side": "long",
        }
    )

    assert payload["meta"]["ok"] is True
    assert captured["reduce_only"] is True
    assert captured["position_side"] == "long"
    assert payload["data"]["reduce_only"] is True
    assert payload["data"]["execution_request"]["reduce_only"] is True
    assert payload["data"]["execution_request"]["position_side"] == "long"


def test_bitmart_swap_orders_use_direct_rest_submission(monkeypatch):
    monkeypatch.setenv("BITMART_API_KEY", "key")
    monkeypatch.setenv("BITMART_SECRET", "secret")
    monkeypatch.setenv("BITMART_MEMO", "memo")

    client = VenueExecutionClient("bitmart")
    assert client.account_type == "swap"

    class FakeExchange:
        def market(self, symbol):
            return {"id": "BTCUSDT", "symbol": symbol}

        def amount_to_precision(self, symbol, amount):
            return "1"

        def price_to_precision(self, symbol, price):
            return f"{price:.1f}"

    captured = {}

    class FakeResponse:
        status_code = 200
        text = '{"code":1000,"message":"Ok","data":{"order_id":231116359426639,"price":"market price"}}'

        def json(self):
            return {
                "code": 1000,
                "message": "Ok",
                "trace": "trace-1",
                "data": {"order_id": 231116359426639, "price": "market price"},
            }

    monkeypatch.setattr(client, "_ensure_markets_loaded", lambda public=False: None)
    monkeypatch.setattr(client, "_get_exchange", lambda: FakeExchange())

    def fake_post(url, data=None, headers=None, timeout=None):
        captured["url"] = url
        captured["body"] = data
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(multi_venue_module.requests, "post", fake_post)

    order = client.place_order(
        symbol="BTCUSDT",
        side="sell",
        order_type="market",
        amount=1,
        reduce_only=True,
        position_side="long",
    )

    body = json.loads(captured["body"])
    assert captured["url"].endswith("/contract/private/submit-order")
    assert body["symbol"] == "BTCUSDT"
    assert body["type"] == "market"
    assert body["side"] == 3
    assert body["size"] == 1
    assert "open_type" not in body
    assert order.order_id == "231116359426639"
    assert order.reduce_only is True
    assert order.status == "submitted"


def test_normalize_ccxt_order_maps_common_bitmart_fields() -> None:
    normalized = normalize_ccxt_order(
        provider_name="BITMART",
        order={
            "id": "12345",
            "symbol": "BTC/USDT",
            "side": "buy",
            "type": "market",
            "status": "open",
            "clientOrderId": "client-1",
            "price": "62500.5",
            "average": "62495.1",
            "amount": "0.2",
            "filled": "0.1",
            "remaining": "0.1",
            "cost": "6249.51",
            "timeInForce": "GTC",
            "postOnly": False,
            "reduceOnly": False,
            "timestamp": 1710000000000,
        },
    )

    assert normalized.order_id == "12345"
    assert normalized.exchange == "BITMART"
    assert normalized.symbol == "BTC/USDT"
    assert normalized.price == 62500.5
    assert normalized.amount == 0.2
    assert normalized.created_at is not None


def test_execution_order_payload_keeps_normalized_shape_with_request_context() -> None:
    payload = execution_order_payload(
        ExecutionOrder(
            order_id="ord_123",
            exchange="BITMART",
            symbol="BTC/USDT",
            side="buy",
            order_type="market",
            amount=0.25,
            status="open",
        ),
        request_id="exec_req_123",
        idempotency_key="idem_123",
        routing={"selected_venue": "bitmart", "mode": "single_venue"},
    )

    assert payload["order_id"] == "ord_123"
    assert payload["exchange"] == "BITMART"
    assert payload["request_id"] == "exec_req_123"
    assert payload["idempotency_key"] == "idem_123"
    assert payload["routing"]["selected_venue"] == "bitmart"


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


def test_place_order_rejects_live_execution_in_paper_mode():
    payload = place_order(
        {
            "symbol": "BTC/USDT",
            "side": "buy",
            "amount": 0.1,
        }
    )

    assert payload["meta"]["ok"] is False
    assert payload["data"]["error"] == "paper_mode_active"
    assert payload["data"]["execution_result"]["status"] == "blocked"
    assert payload["data"]["execution_result"]["execution_mode"] == "paper"


def test_place_order_requires_approval_id_when_live_approvals_enabled(monkeypatch):
    monkeypatch.setenv("HERMES_TRADING_MODE", "live")
    monkeypatch.setenv("HERMES_ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("HERMES_LIVE_TRADING_ACK", LIVE_TRADING_ACK_PHRASE)
    monkeypatch.setenv("HERMES_REQUIRE_APPROVAL", "true")

    payload = place_order(
        {
            "symbol": "BTC/USDT",
            "side": "buy",
            "amount": 0.1,
        }
    )

    assert payload["meta"]["ok"] is False
    assert payload["data"]["error"] == "approval_required"
    assert payload["data"]["execution_result"]["reason"] == "approval_required"


def test_place_order_blocks_live_mode_when_unlock_requirements_are_missing(monkeypatch):
    monkeypatch.setenv("HERMES_TRADING_MODE", "live")
    monkeypatch.delenv("HERMES_ENABLE_LIVE_TRADING", raising=False)
    monkeypatch.delenv("HERMES_LIVE_TRADING_ACK", raising=False)

    payload = place_order(
        {
            "symbol": "BTC/USDT",
            "side": "buy",
            "amount": 0.1,
        }
    )

    assert payload["meta"]["ok"] is False
    assert payload["data"]["error"] == "live_trading_disabled"
    assert payload["data"]["execution_result"]["status"] == "blocked"
    assert payload["data"]["execution_result"]["reason"] == "live_trading_disabled"


def test_execution_outcome_keeps_typed_request_and_result_fields():
    outcome = ExecutionOutcome(
        request=ExecutionRequest(
            request_id="exec_req_test",
            symbol="BTCUSDT",
            side="buy",
            order_type="market",
            amount=0.25,
        ),
        result=ExecutionResult(
            symbol="BTCUSDT",
            order_id="ord-1",
            status="filled",
            success=True,
            execution_mode="live",
        ),
    )

    assert outcome.request.request_id == "exec_req_test"
    assert outcome.request.idempotency_key
    assert outcome.result.status == "filled"
