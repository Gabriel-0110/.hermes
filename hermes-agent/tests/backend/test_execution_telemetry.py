from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import backend.integrations.execution.multi_venue as multi_venue_module
from backend.integrations.base import IntegrationError
from backend.integrations.execution.multi_venue import VenueExecutionClient


def _enable_bitmart(monkeypatch: pytest.MonkeyPatch) -> VenueExecutionClient:
    monkeypatch.setenv("BITMART_API_KEY", "key")
    monkeypatch.setenv("BITMART_SECRET", "secret")
    monkeypatch.setenv("BITMART_MEMO", "memo")
    monkeypatch.setenv("BITMART_UID", "uid")
    monkeypatch.setenv("HERMES_TRADING_MODE", "live")
    monkeypatch.setenv("HERMES_ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("HERMES_LIVE_TRADING_ACK", "I_ACKNOWLEDGE_LIVE_TRADING_RISK")
    return VenueExecutionClient("bitmart")


def _capture_execution_events(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        multi_venue_module,
        "get_observability_service",
        lambda: SimpleNamespace(record_execution_event=lambda **kwargs: events.append(kwargs)),
    )
    return events


def test_capability_probe_emits_started_and_result_events_without_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _enable_bitmart(monkeypatch)
    events = _capture_execution_events(monkeypatch)

    class FakeResponse:
        status_code = 403
        text = "error code: 1010 cloudflare waf"

        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr(multi_venue_module.requests, "post", lambda *args, **kwargs: FakeResponse())

    result = client.check_futures_write_capability(symbol="BTCUSDT", verify_remote=True)

    assert result.status == "cloudflare_waf"
    assert [event["event_type"] for event in events] == [
        "bitmart_futures_write_probe_started",
        "bitmart_futures_write_probe_result",
    ]
    assert events[-1]["status"] == "cloudflare_waf"
    serialized = json.dumps(events)
    assert "key" not in serialized
    assert "secret" not in serialized
    assert "X-BM-SIGN" not in serialized


def test_submit_order_emits_requested_and_accepted_events(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _enable_bitmart(monkeypatch)
    events = _capture_execution_events(monkeypatch)

    class FakeExchange:
        def market(self, symbol):
            return {"id": "BTCUSDT", "symbol": symbol}

        def amount_to_precision(self, symbol, amount):
            return "1"

    class FakeResponse:
        status_code = 200
        text = '{"code":1000,"message":"Ok","data":{"order_id":"ord-1"}}'

        def json(self):
            return {"code": 1000, "message": "Ok", "data": {"order_id": "ord-1"}}

    monkeypatch.setattr(client, "_ensure_markets_loaded", lambda public=False: None)
    monkeypatch.setattr(client, "_get_exchange", lambda: FakeExchange())
    monkeypatch.setattr(multi_venue_module.requests, "post", lambda *args, **kwargs: FakeResponse())

    order = client.place_order(symbol="BTCUSDT", side="buy", order_type="market", amount=1)

    assert order.order_id == "ord-1"
    assert [event["event_type"] for event in events] == [
        "order_submit_requested",
        "order_submit_accepted",
    ]
    assert events[-1]["payload"]["order_id"] == "ord-1"


def test_submit_order_emits_rejected_event_with_classified_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _enable_bitmart(monkeypatch)
    events = _capture_execution_events(monkeypatch)

    class FakeExchange:
        def market(self, symbol):
            return {"id": "BTCUSDT", "symbol": symbol}

        def amount_to_precision(self, symbol, amount):
            return "1"

    class FakeResponse:
        status_code = 429
        text = "too many requests"

        def json(self):
            return {"code": 429, "message": "too many requests"}

    monkeypatch.setattr(client, "_ensure_markets_loaded", lambda public=False: None)
    monkeypatch.setattr(client, "_get_exchange", lambda: FakeExchange())
    monkeypatch.setattr(multi_venue_module.requests, "post", lambda *args, **kwargs: FakeResponse())

    with pytest.raises(IntegrationError):
        client.place_order(symbol="BTCUSDT", side="buy", order_type="market", amount=1)

    assert events[-1]["event_type"] == "order_submit_rejected"
    assert events[-1]["status"] == "rate_limited_write_access"
    assert events[-1]["payload"]["error_classification"] == "rate_limited_write_access"


def test_cancel_order_emits_requested_and_accepted_events(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _enable_bitmart(monkeypatch)
    events = _capture_execution_events(monkeypatch)

    class FakeExchange:
        def cancel_order(self, order_id, symbol=None):
            return {"id": order_id, "symbol": symbol or "BTCUSDT", "status": "canceled"}

    monkeypatch.setattr(client, "_get_exchange", lambda: FakeExchange())

    order = client.cancel_order(order_id="ord-1", symbol="BTCUSDT")

    assert order.order_id == "ord-1"
    assert [event["event_type"] for event in events] == [
        "order_cancel_requested",
        "order_cancel_accepted",
    ]


def test_cancel_order_emits_rejected_event_with_classified_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _enable_bitmart(monkeypatch)
    events = _capture_execution_events(monkeypatch)

    class FakeExchange:
        def cancel_order(self, order_id, symbol=None):
            raise RuntimeError("HTTP 403 Cloudflare WAF")

    monkeypatch.setattr(client, "_get_exchange", lambda: FakeExchange())

    with pytest.raises(IntegrationError):
        client.cancel_order(order_id="ord-1", symbol="BTCUSDT")

    assert events[-1]["event_type"] == "order_cancel_rejected"
    assert events[-1]["status"] == "cloudflare_waf"
    assert events[-1]["payload"]["error_classification"] == "cloudflare_waf"
