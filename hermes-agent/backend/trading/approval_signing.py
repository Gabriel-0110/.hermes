"""HMAC signing for trade approval callback data.

Generates and verifies signed callback tokens for Telegram inline keyboards
to prevent spoofing of approve/decline actions. Tokens include a 10-minute
TTL — expired tokens are always rejected.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time

_TTL_SECONDS = 600
_SECRET_ENV = "HERMES_APPROVAL_HMAC_SECRET"
_DEFAULT_SECRET = "hermes-approval-default-key"


def _get_secret() -> str:
    return os.getenv(_SECRET_ENV, _DEFAULT_SECRET)


def sign_callback(action: str, approval_id: str) -> str:
    ts = str(int(time.time()))
    payload = f"{action}:{approval_id}:{ts}"
    sig = hmac.new(_get_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{action}:{approval_id}:{ts}:{sig}"


def verify_callback(token: str) -> tuple[bool, str, str, str]:
    """Returns (valid, action, approval_id, rejection_reason)."""
    parts = token.split(":")
    if len(parts) != 4:
        return False, "", "", "malformed_token"

    action, approval_id, ts_str, sig = parts

    try:
        ts = int(ts_str)
    except ValueError:
        return False, action, approval_id, "invalid_timestamp"

    if time.time() - ts > _TTL_SECONDS:
        return False, action, approval_id, "expired"

    expected_payload = f"{action}:{approval_id}:{ts_str}"
    expected_sig = hmac.new(_get_secret().encode(), expected_payload.encode(), hashlib.sha256).hexdigest()[:16]

    if not hmac.compare_digest(sig, expected_sig):
        return False, action, approval_id, "signature_mismatch"

    return True, action, approval_id, ""
