"""Redis-backed operator approval store for execution gating.

Approval requests are created by the event-bus worker when
``HERMES_REQUIRE_APPROVAL=true`` is set.  Operators review and approve or
reject them via the API (``POST /execution/approvals/{id}/approve``).

On approval the stored payload is re-published to Redis Streams so the
execution worker can proceed normally — maintaining the existing event-driven
pipeline without a separate execution path.

Redis key layout
----------------
- ``hermes:approvals:<uuid>``          — HASH per approval request
- ``hermes:approvals:pending_ids``     — LIST of UUIDs in arrival order
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_KEY_PREFIX = "hermes:approvals:"
_PENDING_LIST = "hermes:approvals:pending_ids"
_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days — auto-expire stale approvals


def _redis():
    from backend.redis_client import get_redis_client  # type: ignore[import]

    return get_redis_client()


def create_approval_request(
    payload: dict,
    correlation_id: str,
    *,
    symbol: str | None = None,
    side: str | None = None,
    amount: float | None = None,
) -> str:
    """Persist a new approval request and return its ``approval_id``."""
    approval_id = str(uuid.uuid4())
    key = f"{_KEY_PREFIX}{approval_id}"
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "approval_id": approval_id,
        "status": "pending",
        "payload": json.dumps(payload),
        "correlation_id": correlation_id,
        "symbol": symbol or payload.get("symbol") or "",
        "side": side or payload.get("side") or "",
        "amount": str(amount or payload.get("amount") or ""),
        "created_at": now,
        "updated_at": now,
        "approved_at": "",
        "rejected_at": "",
        "operator": "",
        "reject_reason": "",
    }
    client = _redis()
    client.hset(key, mapping=data)
    client.expire(key, _TTL_SECONDS)
    client.lpush(_PENDING_LIST, approval_id)
    logger.info("approvals: created approval_id=%s correlation_id=%s", approval_id, correlation_id)
    return approval_id


def list_pending_approvals(limit: int = 20) -> list[dict]:
    """Return up to *limit* pending approvals in arrival order (newest first)."""
    client = _redis()
    # LRANGE returns oldest-first (LPUSH inserts at head); reverse for newest-first
    ids = client.lrange(_PENDING_LIST, 0, limit * 2)  # over-fetch to account for non-pending
    results: list[dict] = []
    for approval_id in ids:
        raw = client.hgetall(f"{_KEY_PREFIX}{approval_id}")
        if not raw:
            continue
        if raw.get("status") != "pending":
            continue
        results.append(_deserialize(raw))
        if len(results) >= limit:
            break
    return results


def get_approval(approval_id: str) -> dict | None:
    """Fetch a single approval by ID.  Returns ``None`` if not found."""
    raw = _redis().hgetall(f"{_KEY_PREFIX}{approval_id}")
    if not raw:
        return None
    return _deserialize(raw)


def approve_request(approval_id: str, operator: str = "api") -> dict | None:
    """Mark an approval as approved.

    Returns the updated approval dict, or ``None`` if not found.
    On approval the original payload is re-published to Redis Streams so the
    execution worker can process it.
    """
    client = _redis()
    key = f"{_KEY_PREFIX}{approval_id}"
    if not client.exists(key):
        return None
    now = datetime.now(timezone.utc).isoformat()
    client.hset(
        key,
        mapping={"status": "approved", "approved_at": now, "updated_at": now, "operator": operator},
    )
    raw = client.hgetall(key)
    approval = _deserialize(raw)
    # Re-publish the original execution payload so the worker can proceed
    _republish_for_execution(approval, client)
    logger.info("approvals: approved approval_id=%s operator=%s", approval_id, operator)
    return approval


def reject_request(approval_id: str, reason: str = "", operator: str = "api") -> dict | None:
    """Mark an approval as rejected.  Returns the updated dict or ``None``."""
    client = _redis()
    key = f"{_KEY_PREFIX}{approval_id}"
    if not client.exists(key):
        return None
    now = datetime.now(timezone.utc).isoformat()
    client.hset(
        key,
        mapping={
            "status": "rejected",
            "rejected_at": now,
            "updated_at": now,
            "operator": operator,
            "reject_reason": reason,
        },
    )
    raw = client.hgetall(key)
    logger.info("approvals: rejected approval_id=%s operator=%s reason=%s", approval_id, operator, reason)
    return _deserialize(raw)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _deserialize(raw: dict) -> dict:
    """Convert raw Redis hash to a Python dict with proper types."""
    result = dict(raw)
    # Decode bytes keys/values (redis-py may return bytes)
    result = {
        (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
        for k, v in result.items()
    }
    # Parse payload back to dict
    payload_str = result.get("payload", "{}")
    try:
        result["payload"] = json.loads(payload_str)
    except (ValueError, TypeError):
        result["payload"] = {}
    # Convert empty strings to None for optional fields
    for field in ("approved_at", "rejected_at", "operator", "reject_reason", "symbol", "side"):
        if result.get(field) == "":
            result[field] = None
    return result


def _republish_for_execution(approval: dict, client) -> None:
    """Re-publish the approved execution payload to the execution_requested stream."""
    try:
        import json as _json

        from backend.event_bus.publisher import publish_event  # type: ignore[import]

        payload = approval.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}

        event_data = {
            "event_type": "execution_requested",
            "correlation_id": approval.get("correlation_id") or "",
            "approved_by": approval.get("operator") or "api",
            "approval_id": approval["approval_id"],
            **payload,
        }
        publish_event("execution_requested", event_data)
        logger.info(
            "approvals: re-published execution_requested for approval_id=%s",
            approval["approval_id"],
        )
    except Exception as exc:
        logger.warning(
            "approvals: could not re-publish execution event for approval_id=%s: %s",
            approval.get("approval_id"),
            exc,
        )
