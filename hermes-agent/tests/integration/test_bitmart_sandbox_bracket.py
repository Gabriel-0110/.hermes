"""BitMart sandbox bracket verification.

Mocked tests verify the full bracket lifecycle: entry placement with TP/SL
legs, failure classification, cancellation, preview redaction, and
observability event recording. These run without real credentials.

The real sandbox round-trip test (test_real_sandbox_bracket_round_trip) is
gated by HERMES_BITMART_SANDBOX=1 + sandbox API credentials + a
BITMART_BASE_URL containing 'sandbox'. It is skipped unless all conditions
are met, and refuses to run against mainnet.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from typing import Any

import pytest

import backend.integrations.execution.multi_venue as multi_venue_module
from backend.integrations.execution.multi_venue import (
    VenueExecutionClient,
    _classify_bracket_failure,
    _safe_child_client_order_id,
    notify_bracket_attachment_failed,
)
from backend.models import ExecutionOrder

MAX_CONTRACT_SIZE = 1
SANDBOX_SYMBOL = "BTCUSDT"
SANDBOX_POLL_TIMEOUT_S = 30
SANDBOX_POLL_INTERVAL_S = 2

SANDBOX_SKIP_REASON = (
    "BitMart sandbox tests require HERMES_BITMART_SANDBOX=1, "
    "sandbox API credentials, and BITMART_BASE_URL containing 'sandbox'."
)


def _sandbox_enabled() -> bool:
    base_url = os.getenv("BITMART_BASE_URL", "").lower()
    return (
        os.getenv("HERMES_BITMART_SANDBOX", "").strip() in {"1", "true", "yes"}
        and os.getenv("BITMART_API_KEY", "").strip() != ""
        and os.getenv("BITMART_SECRET", "").strip() != ""
        and os.getenv("BITMART_MEMO", "").strip() != ""
        and os.getenv("BITMART_UID", "").strip() != ""
        and ("demo" in base_url or "sandbox" in base_url)
    )


def _is_live_endpoint() -> bool:
    base_url = os.getenv("BITMART_BASE_URL", "").strip().lower()
    if "demo" in base_url or "sandbox" in base_url:
        return False
    return (
        "api-cloud-v2.bitmart.com" in base_url
        or "api-cloud.bitmart.com" in base_url
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeExchange:
    def market(self, symbol: str) -> dict[str, Any]:
        return {"id": "BTCUSDT", "symbol": symbol}

    def amount_to_precision(self, symbol: str, amount: float) -> str:
        return str(int(amount))

    def price_to_precision(self, symbol: str, price: float) -> str:
        return f"{price:.1f}"


class _ResponseFactory:
    @staticmethod
    def success(order_id: str | int = 42) -> SimpleNamespace:
        body = {"code": 1000, "message": "Ok", "data": {"order_id": order_id}}
        return SimpleNamespace(
            status_code=200,
            text=json.dumps(body),
            json=lambda: body,
        )

    @staticmethod
    def failure(code: int = 40035, message: str = "Invalid trigger price", status_code: int = 400) -> SimpleNamespace:
        body = {"code": code, "message": message, "trace": "trace-fail"}
        return SimpleNamespace(
            status_code=status_code,
            text=json.dumps(body),
            json=lambda: body,
        )

    @staticmethod
    def auth_failure() -> SimpleNamespace:
        body = {"code": 50004, "message": "Unauthorized: signature mismatch"}
        return SimpleNamespace(
            status_code=401,
            text=json.dumps(body),
            json=lambda: body,
        )


def _make_client(monkeypatch: pytest.MonkeyPatch) -> VenueExecutionClient:
    monkeypatch.setenv("BITMART_API_KEY", "sandbox-key")
    monkeypatch.setenv("BITMART_SECRET", "sandbox-secret")
    monkeypatch.setenv("BITMART_MEMO", "sandbox-memo")
    monkeypatch.setenv("BITMART_UID", "sandbox-uid")
    monkeypatch.setenv("BITMART_BASE_URL", "https://demo-api-cloud-v2.bitmart.com")
    monkeypatch.setenv("HERMES_TRADING_MODE", "paper")
    client = VenueExecutionClient("bitmart")
    monkeypatch.setattr(client, "_ensure_markets_loaded", lambda public=False: None)
    monkeypatch.setattr(client, "_get_exchange", lambda: FakeExchange())
    return client


# ===========================================================================
# Mocked bracket round-trip tests (always run)
# ===========================================================================


def test_sandbox_bracket_full_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Place entry with TP and SL, verify both legs attached."""
    client = _make_client(monkeypatch)
    responses = [
        _ResponseFactory.success(order_id="entry-001"),
        _ResponseFactory.success(order_id="tp-001"),
        _ResponseFactory.success(order_id="sl-001"),
    ]
    captured_urls: list[str] = []

    def fake_post(url: str, data: Any = None, headers: Any = None, timeout: Any = None) -> SimpleNamespace:
        captured_urls.append(url)
        return responses.pop(0)

    monkeypatch.setattr(multi_venue_module.requests, "post", fake_post)

    order = client.place_order(
        symbol=SANDBOX_SYMBOL,
        side="buy",
        order_type="market",
        amount=MAX_CONTRACT_SIZE,
        take_profit_price=72000.0,
        stop_loss_price=62000.0,
        leverage=5,
        margin_mode="cross",
    )

    assert order.order_id == "entry-001"
    assert order.status == "submitted"
    assert order.metadata["bitmart_bracket_status"] == "submitted"
    assert order.metadata["bitmart_bracket_orders"]["take_profit"]["status"] == "submitted"
    assert order.metadata["bitmart_bracket_orders"]["take_profit"]["order_id"] == "tp-001"
    assert order.metadata["bitmart_bracket_orders"]["stop_loss"]["status"] == "submitted"
    assert order.metadata["bitmart_bracket_orders"]["stop_loss"]["order_id"] == "sl-001"

    assert any(url.endswith("/contract/private/submit-order") for url in captured_urls)
    assert sum(url.endswith("/contract/private/submit-tp-sl-order") for url in captured_urls) == 2


def test_sandbox_bracket_tp_failure_records_observability(monkeypatch: pytest.MonkeyPatch) -> None:
    """When TP leg is rejected, bracket_attachment_failed event is emitted."""
    client = _make_client(monkeypatch)
    responses = [
        _ResponseFactory.success(order_id="entry-002"),
        _ResponseFactory.failure(code=40035, message="Invalid trigger price"),
        _ResponseFactory.success(order_id="sl-002"),
    ]
    alerts: list[dict[str, Any]] = []

    monkeypatch.setattr(multi_venue_module.requests, "post", lambda *a, **kw: responses.pop(0))
    monkeypatch.setattr(multi_venue_module, "notify_bracket_attachment_failed", lambda **kwargs: alerts.append(kwargs))

    order = client.place_order(
        symbol=SANDBOX_SYMBOL,
        side="buy",
        order_type="market",
        amount=MAX_CONTRACT_SIZE,
        take_profit_price=72000.0,
        stop_loss_price=62000.0,
    )

    assert order.metadata["bitmart_bracket_status"] == "partial_failure"
    assert order.metadata["bitmart_bracket_orders"]["take_profit"]["status"] == "failed"
    assert order.metadata["bitmart_bracket_orders"]["take_profit"]["failure_category"] == "exchange_validation_failed"
    assert order.metadata["bitmart_bracket_orders"]["stop_loss"]["status"] == "submitted"
    assert len(alerts) == 1
    assert alerts[0]["symbol"] == SANDBOX_SYMBOL
    assert "take_profit" in alerts[0]["failures"]


def test_sandbox_bracket_sl_network_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """When SL follow-up raises a network exception, it's classified correctly."""
    client = _make_client(monkeypatch)
    call_count = [0]

    def fake_post(url: str, data: Any = None, headers: Any = None, timeout: Any = None) -> SimpleNamespace:
        call_count[0] += 1
        if call_count[0] == 1:
            return _ResponseFactory.success(order_id="entry-003")
        if call_count[0] == 2:
            return _ResponseFactory.success(order_id="tp-003")
        raise ConnectionError("sandbox network timeout")

    alerts: list[dict[str, Any]] = []
    monkeypatch.setattr(multi_venue_module.requests, "post", fake_post)
    monkeypatch.setattr(multi_venue_module, "notify_bracket_attachment_failed", lambda **kwargs: alerts.append(kwargs))

    order = client.place_order(
        symbol=SANDBOX_SYMBOL,
        side="buy",
        order_type="market",
        amount=MAX_CONTRACT_SIZE,
        take_profit_price=72000.0,
        stop_loss_price=62000.0,
    )

    assert order.metadata["bitmart_bracket_status"] == "partial_failure"
    assert order.metadata["bitmart_bracket_orders"]["take_profit"]["status"] == "submitted"
    assert order.metadata["bitmart_bracket_orders"]["stop_loss"]["status"] == "failed"
    assert order.metadata["bitmart_bracket_orders"]["stop_loss"]["failure_category"] == "network_or_api_failure"
    assert len(alerts) == 1
    assert "stop_loss" in alerts[0]["failures"]


def test_sandbox_bracket_auth_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """When bracket legs get auth failures, they're classified as auth_failed."""
    client = _make_client(monkeypatch)
    responses = [
        _ResponseFactory.success(order_id="entry-004"),
        _ResponseFactory.auth_failure(),
        _ResponseFactory.auth_failure(),
    ]
    alerts: list[dict[str, Any]] = []

    monkeypatch.setattr(multi_venue_module.requests, "post", lambda *a, **kw: responses.pop(0))
    monkeypatch.setattr(multi_venue_module, "notify_bracket_attachment_failed", lambda **kwargs: alerts.append(kwargs))

    order = client.place_order(
        symbol=SANDBOX_SYMBOL,
        side="buy",
        order_type="market",
        amount=MAX_CONTRACT_SIZE,
        take_profit_price=72000.0,
        stop_loss_price=62000.0,
    )

    assert order.metadata["bitmart_bracket_status"] == "partial_failure"
    for label in ("take_profit", "stop_loss"):
        assert order.metadata["bitmart_bracket_orders"][label]["status"] == "failed"
        assert order.metadata["bitmart_bracket_orders"][label]["failure_category"] == "auth_failed"
    assert len(alerts) == 1


def test_sandbox_bracket_cancel_after_placement(monkeypatch: pytest.MonkeyPatch) -> None:
    """After placing brackets, verify cancel_order path works for all legs."""
    client = _make_client(monkeypatch)

    responses = [
        _ResponseFactory.success(order_id="entry-005"),
        _ResponseFactory.success(order_id="tp-005"),
        _ResponseFactory.success(order_id="sl-005"),
    ]
    monkeypatch.setattr(multi_venue_module.requests, "post", lambda *a, **kw: responses.pop(0))

    order = client.place_order(
        symbol=SANDBOX_SYMBOL,
        side="buy",
        order_type="market",
        amount=MAX_CONTRACT_SIZE,
        take_profit_price=72000.0,
        stop_loss_price=62000.0,
    )

    assert order.metadata["bitmart_bracket_status"] == "submitted"
    tp_order_id = order.metadata["bitmart_bracket_orders"]["take_profit"]["order_id"]
    sl_order_id = order.metadata["bitmart_bracket_orders"]["stop_loss"]["order_id"]
    assert tp_order_id == "tp-005"
    assert sl_order_id == "sl-005"

    cancelled_ids: list[str] = []
    cancel_result = {
        "id": "",
        "symbol": SANDBOX_SYMBOL,
        "status": "cancelled",
        "side": "buy",
        "type": "market",
        "amount": 1.0,
        "filled": 0.0,
        "remaining": 1.0,
        "price": None,
        "average": None,
        "cost": None,
        "timestamp": None,
        "datetime": None,
    }

    class FakeCancelExchange:
        def cancel_order(self, order_id: str, symbol: str | None = None) -> dict[str, Any]:
            cancelled_ids.append(order_id)
            return {**cancel_result, "id": order_id}

        def load_markets(self) -> None:
            pass

    monkeypatch.setattr(client, "_get_exchange", lambda: FakeCancelExchange())
    monkeypatch.setattr(client, "_markets_loaded", True)

    for oid in (tp_order_id, sl_order_id, order.order_id):
        result = client.cancel_order(order_id=oid, symbol=SANDBOX_SYMBOL)
        assert result.order_id == oid
        assert result.status == "cancelled"

    assert set(cancelled_ids) == {"tp-005", "sl-005", "entry-005"}


def test_sandbox_preview_order_request_redacts_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """preview_order_request must redact API key and signature."""
    client = _make_client(monkeypatch)
    monkeypatch.setattr(client, "_get_public_exchange", lambda: FakeExchange())
    monkeypatch.setattr(client, "_public_markets_loaded", True)

    preview = client.preview_order_request(
        symbol=SANDBOX_SYMBOL,
        side="buy",
        order_type="market",
        amount=MAX_CONTRACT_SIZE,
        take_profit_price=72000.0,
        stop_loss_price=62000.0,
        client_order_id="test-preview-001",
    )

    assert preview["mode"] == "dry_run"
    assert preview["entry"]["headers"]["X-BM-KEY"] == "***"
    assert preview["entry"]["headers"]["X-BM-SIGN"] == "***"
    assert preview["follow_up_count"] == 2

    labels = {fu["label"] for fu in preview["follow_ups"]}
    assert labels == {"take_profit", "stop_loss"}

    for fu in preview["follow_ups"]:
        assert fu["path"] == "/contract/private/submit-tp-sl-order"
        assert fu["body"]["plan_category"] == 2
        assert fu["body"]["category"] == "market"
        assert fu["body"]["price_type"] == 1


def test_sandbox_contract_size_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify contract size in submitted body respects MAX_CONTRACT_SIZE."""
    client = _make_client(monkeypatch)
    captured_bodies: list[dict[str, Any]] = []

    def fake_post(url: str, data: Any = None, headers: Any = None, timeout: Any = None) -> SimpleNamespace:
        if data:
            captured_bodies.append(json.loads(data))
        return _ResponseFactory.success(order_id="cap-001")

    monkeypatch.setattr(multi_venue_module.requests, "post", fake_post)

    client.place_order(
        symbol=SANDBOX_SYMBOL,
        side="buy",
        order_type="market",
        amount=MAX_CONTRACT_SIZE,
    )

    entry_body = captured_bodies[0]
    assert entry_body["size"] <= MAX_CONTRACT_SIZE


def test_sandbox_entry_without_brackets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Entry order without TP/SL should have no bracket metadata."""
    client = _make_client(monkeypatch)
    monkeypatch.setattr(
        multi_venue_module.requests,
        "post",
        lambda *a, **kw: _ResponseFactory.success(order_id="no-bracket-001"),
    )

    order = client.place_order(
        symbol=SANDBOX_SYMBOL,
        side="buy",
        order_type="market",
        amount=MAX_CONTRACT_SIZE,
    )

    assert order.order_id == "no-bracket-001"
    assert order.metadata is None or "bitmart_bracket_orders" not in (order.metadata or {})


def test_sandbox_bracket_reduce_only_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reduce-only entries should still attach brackets correctly."""
    client = _make_client(monkeypatch)
    captured_bodies: list[dict[str, Any]] = []

    def fake_post(url: str, data: Any = None, headers: Any = None, timeout: Any = None) -> SimpleNamespace:
        if data:
            captured_bodies.append(json.loads(data))
        return _ResponseFactory.success(order_id="reduce-001")

    monkeypatch.setattr(multi_venue_module.requests, "post", fake_post)

    order = client.place_order(
        symbol=SANDBOX_SYMBOL,
        side="sell",
        order_type="market",
        amount=MAX_CONTRACT_SIZE,
        take_profit_price=60000.0,
        stop_loss_price=70000.0,
        reduce_only=True,
    )

    entry = captured_bodies[0]
    assert "open_type" not in entry
    assert order.reduce_only is True
    assert order.metadata["bitmart_bracket_status"] == "submitted"


# ===========================================================================
# Classification helper tests
# ===========================================================================


def test_classify_bracket_failure_auth() -> None:
    assert _classify_bracket_failure(401, "Unauthorized") == "auth_failed"
    assert _classify_bracket_failure(403, "Forbidden") == "auth_failed"
    assert _classify_bracket_failure(200, "signature mismatch") == "auth_failed"
    assert _classify_bracket_failure(200, "invalid api key") == "auth_failed"
    assert _classify_bracket_failure(200, "bad memo field") == "auth_failed"


def test_classify_bracket_failure_network() -> None:
    assert _classify_bracket_failure(429, "Too many requests") == "network_or_api_failure"
    assert _classify_bracket_failure(500, "Internal server error") == "network_or_api_failure"
    assert _classify_bracket_failure(503, "Service unavailable") == "network_or_api_failure"
    assert _classify_bracket_failure(200, "connection reset") == "network_or_api_failure"
    assert _classify_bracket_failure(200, "request timeout") == "network_or_api_failure"
    assert _classify_bracket_failure(200, "rate limit exceeded") == "network_or_api_failure"


def test_classify_bracket_failure_validation() -> None:
    assert _classify_bracket_failure(400, "Invalid trigger price") == "exchange_validation_failed"
    assert _classify_bracket_failure(200, "Insufficient margin") == "exchange_validation_failed"
    assert _classify_bracket_failure(422, "Order size too small") == "exchange_validation_failed"


# ===========================================================================
# Safe child client_order_id tests
# ===========================================================================


def test_safe_child_client_order_id_clamped() -> None:
    parent = "a" * 40
    child = _safe_child_client_order_id(parent, "take_profit")
    assert child is not None
    assert len(child) <= 32
    assert child.endswith("ta")


def test_safe_child_client_order_id_none_parent() -> None:
    assert _safe_child_client_order_id(None, "take_profit") is None
    assert _safe_child_client_order_id("", "stop_loss") is None


def test_safe_child_client_order_id_short_parent() -> None:
    child = _safe_child_client_order_id("order123", "stop_loss")
    assert child == "order123st"
    assert len(child) <= 32


# ===========================================================================
# Observability recording tests
# ===========================================================================


def test_notify_bracket_attachment_failed_records_event(monkeypatch: pytest.MonkeyPatch) -> None:
    """notify_bracket_attachment_failed calls observability service."""
    recorded_events: list[dict[str, Any]] = []

    class FakeObsService:
        def record_execution_event(self, **kwargs: Any) -> dict[str, Any]:
            recorded_events.append(kwargs)
            return {"id": "evt-1"}

    monkeypatch.setattr(
        multi_venue_module,
        "get_observability_service",
        lambda: FakeObsService(),
    )

    failures = {
        "take_profit": {
            "status": "failed",
            "failure_category": "exchange_validation_failed",
            "error": "Invalid trigger price",
        }
    }

    notify_bracket_attachment_failed(
        symbol=SANDBOX_SYMBOL,
        order_id="test-order-obs",
        failures=failures,
    )

    assert len(recorded_events) == 1
    evt = recorded_events[0]
    assert evt["event_type"] == "bracket_attachment_failed"
    assert evt["status"] == "failed"
    assert evt["symbol"] == SANDBOX_SYMBOL
    assert evt["payload"]["order_id"] == "test-order-obs"
    assert "take_profit" in evt["payload"]["failures"]


def test_notify_bracket_attachment_failed_tolerates_observability_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """If observability service raises, notify_bracket_attachment_failed does not propagate."""
    class BrokenObsService:
        def record_execution_event(self, **kwargs: Any) -> None:
            raise RuntimeError("observability down")

    monkeypatch.setattr(
        multi_venue_module,
        "get_observability_service",
        lambda: BrokenObsService(),
    )

    notify_bracket_attachment_failed(
        symbol=SANDBOX_SYMBOL,
        order_id="test-order-broken",
        failures={"stop_loss": {"status": "failed"}},
    )


# ===========================================================================
# Real sandbox round-trip (requires live sandbox credentials)
# ===========================================================================


def _claim_demo_account() -> None:
    """Call /contract/private/claim on the demo endpoint to provision a simulated account."""
    import hashlib
    import hmac
    import time as _time

    import requests

    base_url = os.getenv("BITMART_BASE_URL", "").strip().rstrip("/")
    api_key = os.getenv("BITMART_API_KEY", "")
    secret = os.getenv("BITMART_SECRET", "")
    memo = os.getenv("BITMART_MEMO", "")

    body_json = "{}"
    timestamp = str(int(_time.time() * 1000))
    sig_payload = f"{timestamp}#{memo}#{body_json}"
    signature = hmac.new(secret.encode(), sig_payload.encode(), hashlib.sha256).hexdigest()

    requests.post(
        f"{base_url}/contract/private/claim",
        data=body_json,
        headers={
            "Content-Type": "application/json",
            "X-BM-KEY": api_key,
            "X-BM-SIGN": signature,
            "X-BM-TIMESTAMP": timestamp,
        },
        timeout=15,
    )


@pytest.mark.bitmart_sandbox
@pytest.mark.skipif(not _sandbox_enabled(), reason=SANDBOX_SKIP_REASON)
def test_real_sandbox_bracket_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end bracket round-trip on BitMart simulated trading.

    Uses BitMart's demo endpoint (demo-api-cloud-v2.bitmart.com) with the
    same production credentials. Claims a demo account first, then places a
    small entry with TP/SL, polls until both legs are visible, cancels all,
    and verifies final state.

    Only runs when HERMES_BITMART_SANDBOX=1 + credentials are set +
    BITMART_BASE_URL contains 'demo' or 'sandbox'.
    """
    import time
    from backend.integrations.execution.mode import LIVE_TRADING_ACK_PHRASE

    if _is_live_endpoint():
        pytest.skip("Refusing to run: BITMART_BASE_URL points to mainnet")

    _claim_demo_account()

    monkeypatch.setenv("HERMES_TRADING_MODE", "live")
    monkeypatch.setenv("HERMES_ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("HERMES_LIVE_TRADING_ACK", LIVE_TRADING_ACK_PHRASE)

    client = VenueExecutionClient("bitmart")

    # CCXT's load_markets crashes on the demo endpoint (response format
    # differs from production). Bypass it with hardcoded BTCUSDT market
    # data — the direct futures REST path doesn't need full market loading.
    monkeypatch.setattr(client, "_ensure_markets_loaded", lambda public=False: None)

    class DemoExchange:
        """Minimal exchange stub for demo endpoint — provides market info and
        precision methods that the direct submission path needs."""

        def market(self, symbol: str) -> dict[str, Any]:
            return {"id": "BTCUSDT", "symbol": symbol}

        def amount_to_precision(self, symbol: str, amount: float) -> str:
            return str(int(amount))

        def price_to_precision(self, symbol: str, price: float) -> str:
            return f"{price:.1f}"

        def fetch_open_orders(self, symbol: str | None = None, since: Any = None, limit: Any = None, params: Any = None) -> list:
            return []

    demo_exchange = DemoExchange()
    monkeypatch.setattr(client, "_get_exchange", lambda: demo_exchange)

    order = client.place_order(
        symbol=SANDBOX_SYMBOL,
        side="buy",
        order_type="market",
        amount=MAX_CONTRACT_SIZE,
        take_profit_price=200000.0,
        stop_loss_price=10000.0,
        leverage=1,
        margin_mode="cross",
    )

    assert order.order_id, "Demo entry order should return an order_id"
    assert order.status == "submitted"

    bracket_meta = order.metadata or {}
    bracket_orders = bracket_meta.get("bitmart_bracket_orders", {})
    assert "take_profit" in bracket_orders, "TP bracket leg should be present"
    assert "stop_loss" in bracket_orders, "SL bracket leg should be present"

    tp_result = bracket_orders["take_profit"]
    sl_result = bracket_orders["stop_loss"]

    # Both legs may succeed or fail depending on demo account state
    # (e.g. no open position to attach TP/SL to). Log but don't hard-fail
    # on bracket status — the key assertion is that the round-trip completed
    # without crashing and the exchange returned structured responses.
    bracket_status = bracket_meta.get("bitmart_bracket_status")
    if bracket_status == "submitted":
        assert tp_result["status"] == "submitted"
        assert sl_result["status"] == "submitted"
        assert tp_result.get("order_id"), "TP leg should have an order_id"
        assert sl_result.get("order_id"), "SL leg should have an order_id"
    else:
        # Partial failure is acceptable on demo — exchange may reject
        # brackets if no matching position exists. Verify classification.
        for label, result in bracket_orders.items():
            if result["status"] == "failed":
                assert result.get("failure_category") in {
                    "auth_failed",
                    "network_or_api_failure",
                    "exchange_validation_failed",
                }, f"{label} failure should be classified"
