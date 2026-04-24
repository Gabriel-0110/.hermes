from __future__ import annotations

from types import SimpleNamespace

import pytest

import backend.tools.get_execution_status as get_execution_status_module
from backend.integrations.base import IntegrationError
from backend.integrations.execution.mode import LIVE_TRADING_ACK_PHRASE
from backend.integrations.execution.readiness import classify_live_execution_readiness


def _enable_live(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_TRADING_MODE", "live")
    monkeypatch.setenv("HERMES_ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("HERMES_LIVE_TRADING_ACK", LIVE_TRADING_ACK_PHRASE)


def _client(*, configured: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        provider=SimpleNamespace(name="BITMART"),
        exchange_id="bitmart",
        account_type="swap",
        configured=configured,
        credential_env_names=["BITMART_API_KEY", "BITMART_SECRET", "BITMART_MEMO"],
    )


def test_live_readiness_is_not_live_when_unlock_is_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HERMES_TRADING_MODE", raising=False)
    monkeypatch.delenv("HERMES_ENABLE_LIVE_TRADING", raising=False)
    monkeypatch.delenv("HERMES_LIVE_TRADING_ACK", raising=False)

    status = classify_live_execution_readiness(_client(configured=True))

    assert status.status == "not_live"
    assert status.live_env_unlocked is False
    assert status.private_reads_working is False
    assert status.signed_writes_verified is False
    assert status.copy_trading_api_supported is False


def test_live_readiness_blocks_missing_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_live(monkeypatch)

    status = classify_live_execution_readiness(_client(configured=False))

    assert status.status == "blocked_missing_credentials"
    assert status.live_env_unlocked is True
    assert status.credentials_configured is False
    assert "credentials are not configured" in status.blockers[0]


def test_live_readiness_degrades_when_private_reads_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_live(monkeypatch)

    def private_read_probe() -> None:
        raise IntegrationError("BitMart futures balance blocked (HTTP 403 / Cloudflare WAF).")

    status = classify_live_execution_readiness(
        _client(),
        private_read_probe=private_read_probe,
    )

    assert status.status == "degraded_private_access"
    assert status.private_reads_working is False
    assert status.signed_writes_verified is False
    assert "Private BitMart read probe failed" in status.blockers[0]


def test_live_readiness_is_read_only_when_writes_are_unverified(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_live(monkeypatch)

    status = classify_live_execution_readiness(
        _client(),
        private_read_probe=lambda: None,
    )

    assert status.status == "read_only_live"
    assert status.private_reads_working is True
    assert status.signed_writes_verified is False
    assert status.copy_trading_api_supported is False


def test_live_readiness_is_ready_when_signed_write_verification_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_live(monkeypatch)

    status = classify_live_execution_readiness(
        _client(),
        private_read_probe=lambda: None,
        signed_write_probe=lambda: True,
    )

    assert status.status == "api_execution_ready"
    assert status.private_reads_working is True
    assert status.signed_writes_verified is True
    assert status.copy_trading_api_supported is False


def test_execution_status_tool_exposes_readiness_classification(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_live(monkeypatch)

    class FakeVenueClient:
        provider = SimpleNamespace(name="BITMART")
        exchange_id = "bitmart"
        account_type = "swap"
        configured = True
        credential_env_names = ["BITMART_API_KEY", "BITMART_SECRET", "BITMART_MEMO"]
        rate_limit_enabled = True

        def __init__(self, venue: str) -> None:
            assert venue == "bitmart"

        def get_execution_status(self, *, order_id=None, symbol=None):
            readiness = classify_live_execution_readiness(
                self,
                private_read_probe=lambda: None,
                signed_write_probe=lambda: True,
            )
            return SimpleNamespace(
                configured=True,
                detail="BitMart execution readiness: api_execution_ready.",
                model_dump=lambda mode="json": {
                    "exchange": "BITMART",
                    "configured": True,
                    "connected": True,
                    "rate_limit_enabled": True,
                    "account_type": "swap",
                    "readiness_status": readiness.status,
                    "readiness": readiness.model_dump(mode="json"),
                    "support_matrix": {
                        "live_env_unlocked": readiness.live_env_unlocked,
                        "credentials_configured": readiness.credentials_configured,
                        "private_futures_reads_working": readiness.private_reads_working,
                        "signed_futures_writes_verified": readiness.signed_writes_verified,
                        "readiness_state": readiness.status,
                        "read_failure_category": readiness.private_read_failure,
                        "write_failure_category": readiness.signed_write_failure,
                        "copy_trading_api_automation_supported": readiness.copy_trading_api_supported,
                        "copy_trading_api_automation_verified": readiness.copy_trading_api_verified,
                        "blockers": readiness.blockers,
                    },
                    "detail": "BitMart execution readiness: api_execution_ready.",
                    "order": None,
                    "checked_at": readiness.checked_at,
                },
            )

    monkeypatch.setattr(get_execution_status_module, "VenueExecutionClient", FakeVenueClient)

    payload = get_execution_status_module.get_execution_status({"venue": "bitmart"})

    assert payload["meta"]["ok"] is True
    assert payload["data"]["readiness_status"] == "api_execution_ready"
    assert payload["data"]["readiness"]["copy_trading_api_supported"] is False
    assert payload["data"]["support_matrix"]["readiness_state"] == "api_execution_ready"
    assert payload["data"]["support_matrix"]["copy_trading_api_automation_supported"] is False
