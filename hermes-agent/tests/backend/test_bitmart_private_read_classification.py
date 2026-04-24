from __future__ import annotations

import pytest

import backend.integrations.execution.ccxt_client as ccxt_module
from backend.integrations.execution.ccxt_client import CCXTExecutionClient
from backend.integrations.execution.mode import LIVE_TRADING_ACK_PHRASE
from backend.integrations.execution.multi_venue import VenueExecutionClient
from backend.integrations.execution.private_read import (
    ClassifiedPrivateReadError,
    parse_bitmart_private_read_response,
)


class FakeResponse:
    def __init__(self, status_code: int, text: str, payload=None, json_error: Exception | None = None) -> None:
        self.status_code = status_code
        self.text = text
        self._payload = payload
        self._json_error = json_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload


def test_private_read_classifier_identifies_cloudflare_waf() -> None:
    response = FakeResponse(403, "error code: 1010 cloudflare waf", json_error=ValueError("not json"))

    with pytest.raises(ClassifiedPrivateReadError) as exc_info:
        parse_bitmart_private_read_response(response, operation="futures balance")

    assert exc_info.value.classification == "cloudflare_waf"
    assert "Cloudflare/WAF" in str(exc_info.value)


def test_private_read_classifier_identifies_503_challenge_or_origin_problem() -> None:
    response = FakeResponse(503, "<html><title>Just a moment...</title></html>", json_error=ValueError("not json"))

    with pytest.raises(ClassifiedPrivateReadError) as exc_info:
        parse_bitmart_private_read_response(response, operation="futures balance")

    assert exc_info.value.classification == "service_unavailable_or_challenge"


def test_private_read_classifier_identifies_rate_limit() -> None:
    response = FakeResponse(429, '{"message":"too many requests"}', {"message": "too many requests"})

    with pytest.raises(ClassifiedPrivateReadError) as exc_info:
        parse_bitmart_private_read_response(response, operation="futures balance")

    assert exc_info.value.classification == "rate_limited_private_access"


def test_private_read_classifier_identifies_malformed_non_json_response() -> None:
    response = FakeResponse(200, "<html>not json</html>", json_error=ValueError("not json"))

    with pytest.raises(ClassifiedPrivateReadError) as exc_info:
        parse_bitmart_private_read_response(response, operation="futures balance")

    assert exc_info.value.classification == "malformed_response"


def test_private_read_classifier_separates_auth_from_exchange_business_errors() -> None:
    auth_response = FakeResponse(200, '{"code":30005,"message":"Invalid signature"}', {"code": 30005, "message": "Invalid signature"})
    business_response = FakeResponse(200, '{"code":30013,"message":"Invalid currency"}', {"code": 30013, "message": "Invalid currency"})

    with pytest.raises(ClassifiedPrivateReadError) as auth_exc:
        parse_bitmart_private_read_response(auth_response, operation="futures balance")
    with pytest.raises(ClassifiedPrivateReadError) as business_exc:
        parse_bitmart_private_read_response(business_response, operation="futures balance")

    assert auth_exc.value.classification == "auth_failed"
    assert business_exc.value.classification == "exchange_business_error"


def test_ccxt_direct_futures_balance_uses_private_read_classifier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BITMART_API_KEY", "key")
    monkeypatch.setenv("BITMART_SECRET", "secret")
    monkeypatch.setenv("BITMART_MEMO", "memo")
    monkeypatch.setenv("BITMART_UID", "uid")
    client = CCXTExecutionClient()

    monkeypatch.setattr(
        ccxt_module.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(429, '{"message":"too many requests"}', {"message": "too many requests"}),
    )

    with pytest.raises(ClassifiedPrivateReadError) as exc_info:
        client._fetch_futures_balances_rest()

    assert exc_info.value.classification == "rate_limited_private_access"


def test_venue_readiness_exposes_classified_ccxt_private_read_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BITMART_API_KEY", "key")
    monkeypatch.setenv("BITMART_SECRET", "secret")
    monkeypatch.setenv("BITMART_MEMO", "memo")
    monkeypatch.setenv("BITMART_UID", "uid")
    monkeypatch.setenv("HERMES_TRADING_MODE", "live")
    monkeypatch.setenv("HERMES_ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("HERMES_LIVE_TRADING_ACK", LIVE_TRADING_ACK_PHRASE)
    client = VenueExecutionClient("bitmart")

    class FakeExchange:
        def fetch_balance(self):
            raise RuntimeError("HTTP 403 Cloudflare WAF")

    monkeypatch.setattr(client, "_get_exchange", lambda: FakeExchange())

    status = client.get_execution_status()

    assert status.readiness_status == "degraded_private_access"
    assert status.readiness is not None
    assert status.readiness["private_read_failure"] == "cloudflare_waf"
