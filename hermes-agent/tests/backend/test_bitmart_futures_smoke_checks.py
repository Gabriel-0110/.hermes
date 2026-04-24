from __future__ import annotations

import json

from backend.integrations.execution.multi_venue import VenueExecutionClient
import backend.integrations.execution.multi_venue as multi_venue_module


def _configured_bitmart_client(monkeypatch) -> VenueExecutionClient:
    monkeypatch.setenv("BITMART_API_KEY", "key")
    monkeypatch.setenv("BITMART_SECRET", "secret")
    monkeypatch.setenv("BITMART_MEMO", "memo")
    monkeypatch.setenv("HERMES_TRADING_MODE", "live")
    monkeypatch.setenv("HERMES_ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("HERMES_LIVE_TRADING_ACK", "I_ACKNOWLEDGE_LIVE_TRADING_RISK")
    return VenueExecutionClient("bitmart")


def test_futures_write_smoke_check_dry_run_prepares_signed_request_without_posting(monkeypatch) -> None:
    client = _configured_bitmart_client(monkeypatch)
    posts: list[object] = []

    monkeypatch.setattr(multi_venue_module.requests, "post", lambda *args, **kwargs: posts.append((args, kwargs)))

    result = client.check_futures_write_capability(symbol="BTCUSDT")

    assert result.status == "dry_run_prepared"
    assert result.verified is False
    assert result.live_risking_order is False
    assert result.request_path == "/contract/private/submit-order"
    assert result.prepared_request is not None
    assert result.prepared_request["body"]["size"] == 0
    assert "X-BM-SIGN" in result.prepared_request["headers"]
    assert posts == []


def test_futures_write_smoke_check_verifies_when_exchange_reaches_business_validation(monkeypatch) -> None:
    client = _configured_bitmart_client(monkeypatch)

    class FakeResponse:
        status_code = 200
        text = '{"code":30013,"message":"Invalid order size","trace":"trace-1"}'

        def json(self):
            return {"code": 30013, "message": "Invalid order size", "trace": "trace-1"}

    captured: dict[str, object] = {}

    def fake_post(url, data=None, headers=None, timeout=None):
        captured["url"] = url
        captured["body"] = json.loads(data)
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(multi_venue_module.requests, "post", fake_post)

    result = client.check_futures_write_capability(symbol="BTCUSDT", verify_remote=True)

    assert result.status == "write_verified"
    assert result.verified is True
    assert result.live_risking_order is False
    assert captured["body"]["size"] == 0


def test_futures_write_smoke_check_classifies_cloudflare_waf(monkeypatch) -> None:
    client = _configured_bitmart_client(monkeypatch)

    class FakeResponse:
        status_code = 403
        text = "error code: 1010 cloudflare waf"

        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr(multi_venue_module.requests, "post", lambda *args, **kwargs: FakeResponse())

    result = client.check_futures_write_capability(symbol="BTCUSDT", verify_remote=True)

    assert result.status == "cloudflare_waf"
    assert result.verified is False
    assert "Cloudflare" in (result.detail or "")


def test_futures_write_smoke_check_classifies_rate_limit(monkeypatch) -> None:
    client = _configured_bitmart_client(monkeypatch)

    class FakeResponse:
        status_code = 429
        text = "too many requests"

        def json(self):
            return {"code": 429, "message": "too many requests"}

    monkeypatch.setattr(multi_venue_module.requests, "post", lambda *args, **kwargs: FakeResponse())

    result = client.check_futures_write_capability(symbol="BTCUSDT", verify_remote=True)

    assert result.status == "rate_limited_write_access"
    assert result.verified is False


def test_futures_write_smoke_check_classifies_auth_signature_failure(monkeypatch) -> None:
    client = _configured_bitmart_client(monkeypatch)

    class FakeResponse:
        status_code = 200
        text = '{"code":30005,"message":"Invalid signature","trace":"trace-1"}'

        def json(self):
            return {"code": 30005, "message": "Invalid signature", "trace": "trace-1"}

    monkeypatch.setattr(multi_venue_module.requests, "post", lambda *args, **kwargs: FakeResponse())

    result = client.check_futures_write_capability(symbol="BTCUSDT", verify_remote=True)

    assert result.status == "auth_failed"
    assert result.verified is False
    assert "Invalid signature" in (result.detail or "")


def test_futures_write_smoke_check_classifies_unknown_write_failure(monkeypatch) -> None:
    client = _configured_bitmart_client(monkeypatch)

    class FakeResponse:
        status_code = 500
        text = "server exploded"

        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr(multi_venue_module.requests, "post", lambda *args, **kwargs: FakeResponse())

    result = client.check_futures_write_capability(symbol="BTCUSDT", verify_remote=True)

    assert result.status == "unknown_write_failure"
    assert result.verified is False


def test_execution_readiness_does_not_treat_dry_run_write_probe_as_ready(monkeypatch) -> None:
    client = _configured_bitmart_client(monkeypatch)
    monkeypatch.delenv("HERMES_BITMART_VERIFY_SIGNED_WRITES", raising=False)
    monkeypatch.setattr(client, "get_exchange_balances", lambda: None)

    status = client.get_execution_status()

    assert status.readiness_status == "read_only_live"
    assert status.readiness is not None
    assert status.readiness["signed_writes_verified"] is False


def test_execution_readiness_can_reach_api_ready_after_remote_write_verification(monkeypatch) -> None:
    client = _configured_bitmart_client(monkeypatch)
    monkeypatch.setenv("HERMES_BITMART_VERIFY_SIGNED_WRITES", "true")
    monkeypatch.setattr(client, "get_exchange_balances", lambda: None)
    monkeypatch.setattr(
        client,
        "check_futures_write_capability",
        lambda **kwargs: multi_venue_module.FuturesWriteCapabilityCheck(
            exchange="BITMART",
            venue="bitmart",
            account_type="swap",
            status="write_verified",
            verified=True,
        ),
    )

    status = client.get_execution_status()

    assert status.readiness_status == "api_execution_ready"
    assert status.readiness is not None
    assert status.readiness["signed_writes_verified"] is True
