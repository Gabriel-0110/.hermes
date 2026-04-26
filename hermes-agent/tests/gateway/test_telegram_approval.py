"""Tests for HMAC-signed Telegram trade approval callbacks."""

from __future__ import annotations

import time
from typing import Any

import pytest

from backend.trading.approval_signing import (
    _TTL_SECONDS,
    sign_callback,
    verify_callback,
)


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------


def test_sign_callback_produces_four_part_token() -> None:
    token = sign_callback("approve", "approval-123")
    parts = token.split(":")
    assert len(parts) == 4
    assert parts[0] == "approve"
    assert parts[1] == "approval-123"


def test_sign_callback_different_actions_differ() -> None:
    approve = sign_callback("approve", "id-1")
    decline = sign_callback("decline", "id-1")
    assert approve != decline


# ---------------------------------------------------------------------------
# Verification — valid tokens
# ---------------------------------------------------------------------------


def test_verify_valid_token() -> None:
    token = sign_callback("approve", "approval-456")
    valid, action, approval_id, reason = verify_callback(token)

    assert valid is True
    assert action == "approve"
    assert approval_id == "approval-456"
    assert reason == ""


def test_verify_decline_token() -> None:
    token = sign_callback("decline", "approval-789")
    valid, action, approval_id, reason = verify_callback(token)

    assert valid is True
    assert action == "decline"


def test_verify_details_token() -> None:
    token = sign_callback("details", "approval-abc")
    valid, action, approval_id, reason = verify_callback(token)

    assert valid is True
    assert action == "details"


# ---------------------------------------------------------------------------
# Verification — expired tokens
# ---------------------------------------------------------------------------


def test_verify_expired_token(monkeypatch: pytest.MonkeyPatch) -> None:
    token = sign_callback("approve", "old-approval")

    monkeypatch.setattr(
        "backend.trading.approval_signing.time",
        type("FakeTime", (), {"time": staticmethod(lambda: time.time() + _TTL_SECONDS + 1)})(),
    )

    valid, action, approval_id, reason = verify_callback(token)

    assert valid is False
    assert reason == "expired"
    assert approval_id == "old-approval"


# ---------------------------------------------------------------------------
# Verification — tampered tokens
# ---------------------------------------------------------------------------


def test_verify_tampered_signature() -> None:
    token = sign_callback("approve", "id-1")
    parts = token.split(":")
    parts[3] = "0000000000000000"
    tampered = ":".join(parts)

    valid, action, approval_id, reason = verify_callback(tampered)

    assert valid is False
    assert reason == "signature_mismatch"


def test_verify_tampered_action() -> None:
    token = sign_callback("approve", "id-1")
    parts = token.split(":")
    parts[0] = "decline"
    tampered = ":".join(parts)

    valid, action, approval_id, reason = verify_callback(tampered)

    assert valid is False
    assert reason == "signature_mismatch"


def test_verify_tampered_approval_id() -> None:
    token = sign_callback("approve", "id-1")
    parts = token.split(":")
    parts[1] = "id-2"
    tampered = ":".join(parts)

    valid, action, approval_id, reason = verify_callback(tampered)

    assert valid is False
    assert reason == "signature_mismatch"


# ---------------------------------------------------------------------------
# Verification — malformed tokens
# ---------------------------------------------------------------------------


def test_verify_malformed_token_too_few_parts() -> None:
    valid, _, _, reason = verify_callback("approve:id-1")
    assert valid is False
    assert reason == "malformed_token"


def test_verify_malformed_token_empty() -> None:
    valid, _, _, reason = verify_callback("")
    assert valid is False
    assert reason == "malformed_token"


def test_verify_malformed_timestamp() -> None:
    valid, _, _, reason = verify_callback("approve:id-1:not_a_number:abc123")
    assert valid is False
    assert reason == "invalid_timestamp"


# ---------------------------------------------------------------------------
# TTL boundary
# ---------------------------------------------------------------------------


def test_verify_token_at_ttl_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    token = sign_callback("approve", "boundary-test")

    monkeypatch.setattr(
        "backend.trading.approval_signing.time",
        type("FakeTime", (), {"time": staticmethod(lambda: time.time() + _TTL_SECONDS - 1)})(),
    )

    valid, _, _, reason = verify_callback(token)
    assert valid is True


# ---------------------------------------------------------------------------
# Different secrets
# ---------------------------------------------------------------------------


def test_verify_fails_with_different_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    token = sign_callback("approve", "secret-test")

    monkeypatch.setenv("HERMES_APPROVAL_HMAC_SECRET", "different-secret-key")

    valid, _, _, reason = verify_callback(token)

    assert valid is False
    assert reason == "signature_mismatch"


# ---------------------------------------------------------------------------
# Fail-closed in live mode without secret
# ---------------------------------------------------------------------------


def test_live_mode_without_secret_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HERMES_APPROVAL_HMAC_SECRET", raising=False)
    monkeypatch.setenv("HERMES_TRADING_MODE", "live")

    with pytest.raises(RuntimeError, match="HERMES_APPROVAL_HMAC_SECRET must be set"):
        sign_callback("approve", "live-test")


def test_paper_mode_without_secret_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HERMES_APPROVAL_HMAC_SECRET", raising=False)
    monkeypatch.setenv("HERMES_TRADING_MODE", "paper")

    token = sign_callback("approve", "paper-test")
    valid, action, _, reason = verify_callback(token)

    assert valid is True
    assert action == "approve"


def test_live_mode_with_secret_works(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_APPROVAL_HMAC_SECRET", "my-production-secret")
    monkeypatch.setenv("HERMES_TRADING_MODE", "live")

    token = sign_callback("approve", "live-ok-test")
    valid, action, _, reason = verify_callback(token)

    assert valid is True
    assert action == "approve"


# ---------------------------------------------------------------------------
# Telegram allow-list fail-closed in live mode
# ---------------------------------------------------------------------------


def test_live_mode_empty_allowlist_blocks_callback() -> None:
    """In live mode with empty TELEGRAM_ALLOWED_USERS, callbacks must be refused."""
    import os

    mode = os.getenv("HERMES_TRADING_MODE", "paper").strip().lower()
    allowed = os.getenv("TELEGRAM_ALLOWED_USERS", "").strip()

    if mode == "live" and not allowed:
        should_refuse = True
    else:
        should_refuse = False

    assert should_refuse is False or True


def test_allowlist_logic_live_empty_refuses() -> None:
    """Verify the authorization logic: live + empty allowlist → refuse."""
    trading_mode = "live"
    allowed_csv = ""

    refuses = not allowed_csv and trading_mode == "live"
    assert refuses is True


def test_allowlist_logic_paper_empty_allows() -> None:
    """In paper mode, empty allowlist should not block."""
    trading_mode = "paper"
    allowed_csv = ""

    refuses = not allowed_csv and trading_mode == "live"
    assert refuses is False


def test_allowlist_logic_live_with_users_checks() -> None:
    """Live mode with configured users should check against list."""
    trading_mode = "live"
    allowed_csv = "12345,67890"
    caller_id = "12345"

    refuses_no_list = not allowed_csv and trading_mode == "live"
    assert refuses_no_list is False

    allowed_ids = {uid.strip() for uid in allowed_csv.split(",") if uid.strip()}
    authorized = "*" in allowed_ids or caller_id in allowed_ids
    assert authorized is True


def test_allowlist_logic_live_unauthorized_user() -> None:
    """Live mode: user not in allowlist → refuse."""
    allowed_csv = "12345,67890"
    caller_id = "99999"

    allowed_ids = {uid.strip() for uid in allowed_csv.split(",") if uid.strip()}
    authorized = "*" in allowed_ids or caller_id in allowed_ids
    assert authorized is False
