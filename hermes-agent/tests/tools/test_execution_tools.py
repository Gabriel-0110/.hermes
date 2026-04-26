import json
from types import SimpleNamespace

import backend.tools.get_exchange_balances as balances_module
import backend.tools.place_order as place_order_module
import backend.tools.preview_execution_order as preview_order_module
import backend.integrations.execution.multi_venue as multi_venue_module
from backend.integrations.execution.normalization import execution_order_payload, normalize_ccxt_order
from backend.integrations.execution.multi_venue import VenueExecutionClient
from backend.models import ExecutionOrder
from backend.tools.get_exchange_balances import get_exchange_balances
from backend.tools.place_order import place_order
from backend.tools.preview_execution_order import preview_execution_order
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
    monkeypatch.delenv("BITMART_UID", raising=False)

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


def test_place_order_blocks_bitmart_futures_when_readiness_is_not_api_ready(monkeypatch):
    placed: list[dict[str, object]] = []

    class FakeVenueClient:
        exchange_id = "bitmart"
        account_type = "swap"
        provider = SimpleNamespace(name="BITMART")
        credential_env_names = ["BITMART_API_KEY", "BITMART_SECRET", "BITMART_MEMO"]
        configured = True

        def __init__(self, venue):
            assert venue == "bitmart"

        def get_execution_status(self, *, order_id=None, symbol=None):
            return SimpleNamespace(
                readiness_status="read_only_live",
                readiness={
                    "status": "read_only_live",
                    "private_reads_working": True,
                    "signed_writes_verified": False,
                    "signed_write_failure": "dry_run_prepared",
                    "blockers": ["Signed BitMart write capability has not been verified."],
                },
                support_matrix={
                    "readiness_state": "read_only_live",
                    "write_failure_category": "dry_run_prepared",
                    "blockers": ["Signed BitMart write capability has not been verified."],
                },
            )

        def place_order(self, **kwargs):
            placed.append(kwargs)
            raise AssertionError("place_order must not be called")

    monkeypatch.setattr(place_order_module, "select_order_venue", lambda **kwargs: {"selected_venue": "bitmart", "warnings": []})
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

    payload = place_order({"symbol": "BTCUSDT", "side": "buy", "order_type": "market", "amount": 1, "venue": "bitmart"})

    assert payload["meta"]["ok"] is False
    assert payload["data"]["error"] == "execution_readiness_blocked"
    assert payload["data"]["execution_result"]["status"] == "blocked"
    assert payload["data"]["execution_result"]["reason"] == "execution_failed"
    assert payload["data"]["execution_result"]["payload"]["readiness_status"] == "read_only_live"
    assert placed == []


def test_place_order_blocks_bitmart_futures_when_private_reads_are_degraded(monkeypatch):
    class FakeVenueClient:
        exchange_id = "bitmart"
        account_type = "swap"
        provider = SimpleNamespace(name="BITMART")
        credential_env_names = ["BITMART_API_KEY", "BITMART_SECRET", "BITMART_MEMO"]
        configured = True

        def __init__(self, venue):
            assert venue == "bitmart"

        def get_execution_status(self, *, order_id=None, symbol=None):
            return SimpleNamespace(
                readiness_status="degraded_private_access",
                readiness={
                    "status": "degraded_private_access",
                    "private_reads_working": False,
                    "private_read_failure": "cloudflare_waf",
                    "signed_writes_verified": False,
                    "blockers": ["Private BitMart read probe failed."],
                },
                support_matrix={
                    "readiness_state": "degraded_private_access",
                    "read_failure_category": "cloudflare_waf",
                    "blockers": ["Private BitMart read probe failed."],
                },
            )

        def place_order(self, **kwargs):
            raise AssertionError("place_order must not be called")

    monkeypatch.setattr(place_order_module, "select_order_venue", lambda **kwargs: {"selected_venue": "bitmart", "warnings": []})
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

    payload = place_order({"symbol": "BTCUSDT", "side": "sell", "order_type": "market", "amount": 1, "venue": "bitmart"})

    assert payload["meta"]["ok"] is False
    assert payload["data"]["error"] == "execution_readiness_blocked"
    assert payload["data"]["execution_result"]["payload"]["readiness_status"] == "degraded_private_access"
    assert payload["data"]["execution_result"]["payload"]["support_matrix"]["read_failure_category"] == "cloudflare_waf"


def test_place_order_allows_bitmart_futures_only_when_readiness_is_api_ready(monkeypatch):
    captured: dict[str, object] = {}

    class FakeVenueClient:
        exchange_id = "bitmart"
        account_type = "swap"
        provider = SimpleNamespace(name="BITMART")
        credential_env_names = ["BITMART_API_KEY", "BITMART_SECRET", "BITMART_MEMO"]
        configured = True

        def __init__(self, venue):
            assert venue == "bitmart"

        def get_execution_status(self, *, order_id=None, symbol=None):
            return SimpleNamespace(
                readiness_status="api_execution_ready",
                readiness={"status": "api_execution_ready", "signed_writes_verified": True},
                support_matrix={"readiness_state": "api_execution_ready", "blockers": []},
            )

        def place_order(self, **kwargs):
            captured.update(kwargs)
            return ExecutionOrder(
                order_id="ord-ready-1",
                exchange="BITMART",
                symbol=kwargs["symbol"],
                side=kwargs["side"],
                order_type=kwargs["order_type"],
                amount=kwargs["amount"],
                status="submitted",
            )

    monkeypatch.setattr(place_order_module, "select_order_venue", lambda **kwargs: {"selected_venue": "bitmart", "warnings": []})
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
            "venue": "bitmart",
        }
    )

    assert payload["meta"]["ok"] is True
    assert payload["data"]["order_id"] == "ord-ready-1"
    assert captured["reduce_only"] is True
    assert captured["position_side"] == "long"


def test_place_order_preserves_approval_gate_before_readiness_check(monkeypatch):
    class FakeVenueClient:
        def __init__(self, venue):
            raise AssertionError("Venue client should not be constructed before approval is satisfied")

    monkeypatch.setattr(place_order_module, "VenueExecutionClient", FakeVenueClient)
    monkeypatch.setattr(
        place_order_module,
        "evaluate_execution_safety",
        lambda approval_id=None: SimpleNamespace(
            execution_mode="live",
            blockers=[],
            kill_switch_active=False,
            kill_switch_reason=None,
            approval_required=True,
        ),
    )

    payload = place_order({"symbol": "BTCUSDT", "side": "buy", "amount": 1, "venue": "bitmart"})

    assert payload["meta"]["ok"] is False
    assert payload["data"]["error"] == "approval_required"


def test_bitmart_swap_orders_use_direct_rest_submission(monkeypatch):
    monkeypatch.setenv("BITMART_API_KEY", "key")
    monkeypatch.setenv("BITMART_SECRET", "secret")
    monkeypatch.setenv("BITMART_MEMO", "memo")
    monkeypatch.setenv("BITMART_UID", "uid")

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


def test_bitmart_swap_orders_include_inline_tp_sl_and_leverage(monkeypatch):
    monkeypatch.setenv("BITMART_API_KEY", "key")
    monkeypatch.setenv("BITMART_SECRET", "secret")
    monkeypatch.setenv("BITMART_MEMO", "memo")
    monkeypatch.setenv("BITMART_UID", "uid")

    client = VenueExecutionClient("bitmart")

    class FakeExchange:
        def market(self, symbol):
            return {"id": "BTCUSDT", "symbol": symbol}

        def amount_to_precision(self, symbol, amount):
            return "1"

        def price_to_precision(self, symbol, price):
            return f"{price:.1f}"

    captured: list[tuple[str, str]] = []

    class FakeResponse:
        status_code = 200
        text = '{"code":1000,"message":"Ok","data":{"order_id":42}}'

        def json(self):
            return {"code": 1000, "message": "Ok", "data": {"order_id": 42}}

    monkeypatch.setattr(client, "_ensure_markets_loaded", lambda public=False: None)
    monkeypatch.setattr(client, "_get_exchange", lambda: FakeExchange())

    def fake_post(url, data=None, headers=None, timeout=None):
        captured.append((url, data))
        return FakeResponse()

    monkeypatch.setattr(multi_venue_module.requests, "post", fake_post)

    order = client.place_order(
        symbol="BTCUSDT",
        side="buy",
        order_type="limit",
        amount=1,
        price=65000.0,
        take_profit_price=68000.0,
        stop_loss_price=64000.0,
        leverage=5,
        margin_mode="isolated",
    )

    entry_url, entry_body_raw = captured[0]
    tp_url, tp_body_raw = captured[1]
    sl_url, sl_body_raw = captured[2]

    body = json.loads(entry_body_raw)
    tp_body = json.loads(tp_body_raw)
    sl_body = json.loads(sl_body_raw)

    assert entry_url.endswith("/contract/private/submit-order")
    assert body["open_type"] == "isolated"
    assert body["leverage"] == "5"
    assert body["preset_take_profit_price"] == "68000.0"
    assert body["preset_take_profit_price_type"] == 1
    assert body["preset_stop_loss_price"] == "64000.0"
    assert body["preset_stop_loss_price_type"] == 1

    assert tp_url.endswith("/contract/private/submit-tp-sl-order")
    assert tp_body["type"] == "take_profit"
    assert tp_body["category"] == "market"
    assert tp_body["plan_category"] == 2
    assert tp_body["price_type"] == 1
    assert "client_order_id" not in tp_body
    assert tp_body["trigger_price"] == "68000.0"
    assert tp_body["executive_price"] == "68000.0"

    assert sl_url.endswith("/contract/private/submit-tp-sl-order")
    assert sl_body["type"] == "stop_loss"
    assert sl_body["category"] == "market"
    assert sl_body["plan_category"] == 2
    assert sl_body["price_type"] == 1
    assert "client_order_id" not in sl_body
    assert sl_body["trigger_price"] == "64000.0"
    assert sl_body["executive_price"] == "64000.0"
    assert order.metadata["leverage"] == "5"
    assert order.metadata["bitmart_bracket_status"] == "submitted"
    assert order.metadata["bitmart_bracket_orders"]["take_profit"]["status"] == "submitted"
    assert order.metadata["bitmart_bracket_orders"]["stop_loss"]["status"] == "submitted"


def test_bitmart_swap_orders_raise_risk_alert_when_take_profit_follow_up_is_rejected(monkeypatch):
    monkeypatch.setenv("BITMART_API_KEY", "key")
    monkeypatch.setenv("BITMART_SECRET", "secret")
    monkeypatch.setenv("BITMART_MEMO", "memo")
    monkeypatch.setenv("BITMART_UID", "uid")

    client = VenueExecutionClient("bitmart")

    class FakeExchange:
        def market(self, symbol):
            return {"id": "BTCUSDT", "symbol": symbol}

        def amount_to_precision(self, symbol, amount):
            return "1"

        def price_to_precision(self, symbol, price):
            return f"{price:.1f}"

    class FakeEntryResponse:
        status_code = 200
        text = '{"code":1000,"message":"Ok","data":{"order_id":42}}'

        def json(self):
            return {"code": 1000, "message": "Ok", "data": {"order_id": 42}}

    class FakeTriggerRejectResponse:
        status_code = 400
        text = '{"code":40035,"message":"Invalid trigger price","trace":"trace-tp"}'

        def json(self):
            return {"code": 40035, "message": "Invalid trigger price", "trace": "trace-tp"}

    class FakeSuccessResponse:
        status_code = 200
        text = '{"code":1000,"message":"Ok","data":{"order_id":"sl-1"}}'

        def json(self):
            return {"code": 1000, "message": "Ok", "data": {"order_id": "sl-1"}}

    posts = [FakeEntryResponse(), FakeTriggerRejectResponse(), FakeSuccessResponse()]
    alerts: list[dict[str, object]] = []

    monkeypatch.setattr(client, "_ensure_markets_loaded", lambda public=False: None)
    monkeypatch.setattr(client, "_get_exchange", lambda: FakeExchange())
    monkeypatch.setattr(multi_venue_module, "notify_bracket_attachment_failed", lambda **kwargs: alerts.append(kwargs))
    monkeypatch.setattr(multi_venue_module.requests, "post", lambda *args, **kwargs: posts.pop(0))

    order = client.place_order(
        symbol="BTCUSDT",
        side="buy",
        order_type="limit",
        amount=1,
        price=65000.0,
        take_profit_price=68000.0,
        stop_loss_price=64000.0,
    )

    assert order.order_id == "42"
    assert order.metadata["bitmart_bracket_status"] == "partial_failure"
    assert order.metadata["bitmart_bracket_orders"]["take_profit"]["status"] == "failed"
    assert order.metadata["bitmart_bracket_orders"]["take_profit"]["failure_category"] == "exchange_validation_failed"
    assert order.metadata["bitmart_bracket_orders"]["stop_loss"]["status"] == "submitted"
    assert alerts and alerts[0]["symbol"] == "BTCUSDT"
    assert "take_profit" in alerts[0]["failures"]


def test_bitmart_swap_orders_raise_risk_alert_when_stop_loss_follow_up_has_network_failure(monkeypatch):
    monkeypatch.setenv("BITMART_API_KEY", "key")
    monkeypatch.setenv("BITMART_SECRET", "secret")
    monkeypatch.setenv("BITMART_MEMO", "memo")
    monkeypatch.setenv("BITMART_UID", "uid")

    client = VenueExecutionClient("bitmart")

    class FakeExchange:
        def market(self, symbol):
            return {"id": "BTCUSDT", "symbol": symbol}

        def amount_to_precision(self, symbol, amount):
            return "1"

        def price_to_precision(self, symbol, price):
            return f"{price:.1f}"

    class FakeEntryResponse:
        status_code = 200
        text = '{"code":1000,"message":"Ok","data":{"order_id":99}}'

        def json(self):
            return {"code": 1000, "message": "Ok", "data": {"order_id": 99}}

    class FakeSuccessResponse:
        status_code = 200
        text = '{"code":1000,"message":"Ok","data":{"order_id":"tp-1"}}'

        def json(self):
            return {"code": 1000, "message": "Ok", "data": {"order_id": "tp-1"}}

    responses = [FakeEntryResponse(), FakeSuccessResponse()]
    alerts: list[dict[str, object]] = []

    def fake_post(*args, **kwargs):
        if responses:
            return responses.pop(0)
        raise RuntimeError("connection reset by peer")

    monkeypatch.setattr(client, "_ensure_markets_loaded", lambda public=False: None)
    monkeypatch.setattr(client, "_get_exchange", lambda: FakeExchange())
    monkeypatch.setattr(multi_venue_module, "notify_bracket_attachment_failed", lambda **kwargs: alerts.append(kwargs))
    monkeypatch.setattr(multi_venue_module.requests, "post", fake_post)

    order = client.place_order(
        symbol="BTCUSDT",
        side="buy",
        order_type="limit",
        amount=1,
        price=65000.0,
        take_profit_price=68000.0,
        stop_loss_price=64000.0,
    )

    assert order.order_id == "99"
    assert order.metadata["bitmart_bracket_status"] == "partial_failure"
    assert order.metadata["bitmart_bracket_orders"]["take_profit"]["status"] == "submitted"
    assert order.metadata["bitmart_bracket_orders"]["stop_loss"]["status"] == "failed"
    assert order.metadata["bitmart_bracket_orders"]["stop_loss"]["failure_category"] == "network_or_api_failure"
    assert alerts and "stop_loss" in alerts[0]["failures"]


def test_bitmart_swap_orders_raise_risk_alert_when_bracket_auth_fails(monkeypatch):
    monkeypatch.setenv("BITMART_API_KEY", "key")
    monkeypatch.setenv("BITMART_SECRET", "secret")
    monkeypatch.setenv("BITMART_MEMO", "memo")
    monkeypatch.setenv("BITMART_UID", "uid")

    client = VenueExecutionClient("bitmart")

    class FakeExchange:
        def market(self, symbol):
            return {"id": "BTCUSDT", "symbol": symbol}

        def amount_to_precision(self, symbol, amount):
            return "1"

        def price_to_precision(self, symbol, price):
            return f"{price:.1f}"

    class FakeEntryResponse:
        status_code = 200
        text = '{"code":1000,"message":"Ok","data":{"order_id":77}}'

        def json(self):
            return {"code": 1000, "message": "Ok", "data": {"order_id": 77}}

    class FakeAuthFailureResponse:
        status_code = 200
        text = '{"code":30005,"message":"Invalid signature","trace":"trace-auth"}'

        def json(self):
            return {"code": 30005, "message": "Invalid signature", "trace": "trace-auth"}

    posts = [FakeEntryResponse(), FakeAuthFailureResponse(), FakeAuthFailureResponse()]
    alerts: list[dict[str, object]] = []

    monkeypatch.setattr(client, "_ensure_markets_loaded", lambda public=False: None)
    monkeypatch.setattr(client, "_get_exchange", lambda: FakeExchange())
    monkeypatch.setattr(multi_venue_module, "notify_bracket_attachment_failed", lambda **kwargs: alerts.append(kwargs))
    monkeypatch.setattr(multi_venue_module.requests, "post", lambda *args, **kwargs: posts.pop(0))

    order = client.place_order(
        symbol="BTCUSDT",
        side="buy",
        order_type="limit",
        amount=1,
        price=65000.0,
        take_profit_price=68000.0,
        stop_loss_price=64000.0,
    )

    assert order.order_id == "77"
    assert order.metadata["bitmart_bracket_status"] == "partial_failure"
    assert order.metadata["bitmart_bracket_orders"]["take_profit"]["failure_category"] == "auth_failed"
    assert order.metadata["bitmart_bracket_orders"]["stop_loss"]["failure_category"] == "auth_failed"
    assert alerts and set(alerts[0]["failures"].keys()) == {"take_profit", "stop_loss"}


def test_place_order_surfaces_bitmart_bracket_warning_metadata(monkeypatch):
    class FakeVenueClient:
        exchange_id = "bitmart"
        account_type = "swap"
        provider = SimpleNamespace(name="BITMART")
        credential_env_names = ["BITMART_API_KEY", "BITMART_SECRET", "BITMART_MEMO"]
        configured = True

        def __init__(self, venue):
            assert venue == "bitmart"

        def get_execution_status(self, *, order_id=None, symbol=None):
            return SimpleNamespace(
                readiness_status="api_execution_ready",
                readiness={"status": "api_execution_ready", "signed_writes_verified": True},
                support_matrix={"readiness_state": "api_execution_ready", "blockers": []},
            )

        def place_order(self, **kwargs):
            return ExecutionOrder(
                order_id="ord-bracket-warning",
                exchange="BITMART",
                symbol=kwargs["symbol"],
                side=kwargs["side"],
                order_type=kwargs["order_type"],
                amount=kwargs["amount"],
                status="submitted",
                metadata={
                    "bitmart_bracket_status": "partial_failure",
                    "bitmart_bracket_orders": {
                        "take_profit": {
                            "status": "failed",
                            "trigger_price": "68000.0",
                            "failure_category": "exchange_validation_failed",
                            "error": "Invalid trigger price",
                        }
                    },
                },
            )

    monkeypatch.setattr(place_order_module, "select_order_venue", lambda **kwargs: {"selected_venue": "bitmart", "warnings": []})
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

    payload = place_order({"symbol": "BTCUSDT", "side": "buy", "order_type": "market", "amount": 1, "venue": "bitmart"})

    assert payload["meta"]["ok"] is True
    assert payload["data"]["bracket_status"] == "partial_failure"
    assert payload["data"]["bracket_warnings"]
    assert "BitMart take profit bracket follow-up failed" in payload["meta"]["warnings"][0]


def test_preview_execution_order_returns_redacted_bitmart_bracket_payloads(monkeypatch):
    monkeypatch.setenv("BITMART_API_KEY", "key")
    monkeypatch.setenv("BITMART_SECRET", "secret")
    monkeypatch.setenv("BITMART_MEMO", "memo")
    monkeypatch.setenv("BITMART_UID", "uid")

    client = VenueExecutionClient("bitmart")

    class FakeExchange:
        def market(self, symbol):
            return {"id": "BTCUSDT", "symbol": symbol}

        def amount_to_precision(self, symbol, amount):
            return "1"

        def price_to_precision(self, symbol, price):
            return f"{price:.1f}"

    monkeypatch.setattr(client, "_ensure_markets_loaded", lambda public=False: None)
    monkeypatch.setattr(client, "_get_public_exchange", lambda: FakeExchange())
    monkeypatch.setattr(preview_order_module, "VenueExecutionClient", lambda venue: client)

    payload = preview_execution_order(
        {
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "limit",
            "amount": 1,
            "price": 65000.0,
            "take_profit_price": 68000.0,
            "stop_loss_price": 64000.0,
            "venue": "bitmart",
        }
    )

    assert payload["meta"]["ok"] is True
    preview = payload["data"]["preview"]
    assert preview["mode"] == "dry_run"
    assert preview["entry"]["path"] == "/contract/private/submit-order"
    assert preview["entry"]["headers"]["X-BM-KEY"] == "***"
    assert preview["entry"]["headers"]["X-BM-SIGN"] == "***"
    assert preview["follow_up_count"] == 2
    assert {item["label"] for item in preview["follow_ups"]} == {"take_profit", "stop_loss"}
    assert all(item["path"] == "/contract/private/submit-tp-sl-order" for item in preview["follow_ups"])


def test_preview_execution_order_generates_bitmart_safe_child_client_order_ids(monkeypatch):
    monkeypatch.setenv("BITMART_API_KEY", "key")
    monkeypatch.setenv("BITMART_SECRET", "secret")
    monkeypatch.setenv("BITMART_MEMO", "memo")
    monkeypatch.setenv("BITMART_UID", "uid")

    client = VenueExecutionClient("bitmart")

    class FakeExchange:
        def market(self, symbol):
            return {"id": "BTCUSDT", "symbol": symbol}

        def amount_to_precision(self, symbol, amount):
            return "1"

        def price_to_precision(self, symbol, price):
            return f"{price:.1f}"

    monkeypatch.setattr(client, "_ensure_markets_loaded", lambda public=False: None)
    monkeypatch.setattr(client, "_get_public_exchange", lambda: FakeExchange())
    monkeypatch.setattr(preview_order_module, "VenueExecutionClient", lambda venue: client)

    payload = preview_execution_order(
        {
            "symbol": "BTCUSDT",
            "side": "buy",
            "order_type": "limit",
            "amount": 1,
            "price": 65000.0,
            "take_profit_price": 68000.0,
            "stop_loss_price": 64000.0,
            "venue": "bitmart",
            "client_order_id": "A" * 32,
        }
    )

    follow_ups = {item["label"]: item for item in payload["data"]["preview"]["follow_ups"]}
    tp_client_order_id = follow_ups["take_profit"]["body"]["client_order_id"]
    sl_client_order_id = follow_ups["stop_loss"]["body"]["client_order_id"]

    assert len(tp_client_order_id) <= 32
    assert len(sl_client_order_id) <= 32
    assert tp_client_order_id.isalnum()
    assert sl_client_order_id.isalnum()


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


# ---------------------------------------------------------------------------
# modify_bracket_order tests
# ---------------------------------------------------------------------------


def test_modify_bracket_order_success(monkeypatch):
    monkeypatch.setenv("BITMART_API_KEY", "key")
    monkeypatch.setenv("BITMART_SECRET", "secret")
    monkeypatch.setenv("BITMART_MEMO", "memo")
    monkeypatch.setenv("BITMART_UID", "uid")

    client = VenueExecutionClient("bitmart")

    class FakeExchange:
        def market(self, symbol):
            return {"id": "BTCUSDT", "symbol": symbol}

        def amount_to_precision(self, symbol, amount):
            return "1"

        def price_to_precision(self, symbol, price):
            return f"{price:.1f}"

    class FakeResponse:
        status_code = 200
        text = '{"code":1000,"message":"Ok","data":{}}'

        def json(self):
            return {"code": 1000, "message": "Ok", "data": {}}

    captured_urls: list[str] = []

    def fake_post(url, data=None, headers=None, timeout=None):
        captured_urls.append(url)
        return FakeResponse()

    monkeypatch.setattr(client, "_ensure_markets_loaded", lambda public=False: None)
    monkeypatch.setattr(client, "_get_exchange", lambda: FakeExchange())
    monkeypatch.setattr(multi_venue_module.requests, "post", fake_post)

    result = client.modify_bracket_order(
        order_id="tp-123",
        symbol="BTCUSDT",
        new_trigger_price=69000.0,
    )

    assert result["status"] == "modified"
    assert result["order_id"] == "tp-123"
    assert result["new_trigger_price"] == "69000.0"
    assert any(url.endswith("/contract/private/modify-tp-sl-order") for url in captured_urls)


def test_modify_bracket_order_exchange_rejection(monkeypatch):
    monkeypatch.setenv("BITMART_API_KEY", "key")
    monkeypatch.setenv("BITMART_SECRET", "secret")
    monkeypatch.setenv("BITMART_MEMO", "memo")
    monkeypatch.setenv("BITMART_UID", "uid")

    client = VenueExecutionClient("bitmart")

    class FakeExchange:
        def market(self, symbol):
            return {"id": "BTCUSDT", "symbol": symbol}

        def price_to_precision(self, symbol, price):
            return f"{price:.1f}"

    class FakeResponse:
        status_code = 400
        text = '{"code":40035,"message":"Invalid trigger price"}'

        def json(self):
            return {"code": 40035, "message": "Invalid trigger price"}

    monkeypatch.setattr(client, "_ensure_markets_loaded", lambda public=False: None)
    monkeypatch.setattr(client, "_get_exchange", lambda: FakeExchange())
    monkeypatch.setattr(multi_venue_module.requests, "post", lambda *a, **kw: FakeResponse())

    result = client.modify_bracket_order(
        order_id="tp-456",
        symbol="BTCUSDT",
        new_trigger_price=69000.0,
    )

    assert result["status"] == "failed"
    assert result["failure_category"] == "exchange_validation_failed"


def test_modify_bracket_order_network_failure(monkeypatch):
    monkeypatch.setenv("BITMART_API_KEY", "key")
    monkeypatch.setenv("BITMART_SECRET", "secret")
    monkeypatch.setenv("BITMART_MEMO", "memo")
    monkeypatch.setenv("BITMART_UID", "uid")

    client = VenueExecutionClient("bitmart")

    class FakeExchange:
        def market(self, symbol):
            return {"id": "BTCUSDT", "symbol": symbol}

        def price_to_precision(self, symbol, price):
            return f"{price:.1f}"

    def fake_post(*args, **kwargs):
        raise ConnectionError("network down")

    monkeypatch.setattr(client, "_ensure_markets_loaded", lambda public=False: None)
    monkeypatch.setattr(client, "_get_exchange", lambda: FakeExchange())
    monkeypatch.setattr(multi_venue_module.requests, "post", fake_post)

    result = client.modify_bracket_order(
        order_id="sl-789",
        symbol="BTCUSDT",
        new_trigger_price=62000.0,
    )

    assert result["status"] == "failed"
    assert result["failure_category"] == "network_or_api_failure"


def test_modify_bracket_order_auth_failure(monkeypatch):
    monkeypatch.setenv("BITMART_API_KEY", "key")
    monkeypatch.setenv("BITMART_SECRET", "secret")
    monkeypatch.setenv("BITMART_MEMO", "memo")
    monkeypatch.setenv("BITMART_UID", "uid")

    client = VenueExecutionClient("bitmart")

    class FakeExchange:
        def market(self, symbol):
            return {"id": "BTCUSDT", "symbol": symbol}

        def price_to_precision(self, symbol, price):
            return f"{price:.1f}"

    class FakeResponse:
        status_code = 401
        text = '{"code":50004,"message":"Unauthorized: signature mismatch"}'

        def json(self):
            return {"code": 50004, "message": "Unauthorized: signature mismatch"}

    monkeypatch.setattr(client, "_ensure_markets_loaded", lambda public=False: None)
    monkeypatch.setattr(client, "_get_exchange", lambda: FakeExchange())
    monkeypatch.setattr(multi_venue_module.requests, "post", lambda *a, **kw: FakeResponse())

    result = client.modify_bracket_order(
        order_id="tp-auth",
        symbol="BTCUSDT",
        new_trigger_price=69000.0,
    )

    assert result["status"] == "failed"
    assert result["failure_category"] == "auth_failed"
