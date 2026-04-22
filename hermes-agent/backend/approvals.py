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

State machine
-------------
  pending  →  approved  (operator ACK, re-publishes execution_requested)
  pending  →  rejected  (operator deny)
  pending  →  expired   (explicit call or TTL-based; blocks late execution)

Only "pending" records may transition.  Attempting to approve/reject a
non-pending record is a no-op that returns None.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from backend.trading.models import ExecutionRequest

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
    proposal_id: str | None = None,
    execution_mode: str | None = None,
    decision_reasons: list[str] | None = None,
) -> str:
    """Persist a new approval request and return its ``approval_id``.

    Extra linkage fields (``proposal_id``, ``execution_mode``,
    ``decision_reasons``) are stored in the hash so operators and audit
    consumers can trace approvals back to the originating proposal and
    policy decision without querying additional data stores.
    """
    request = ExecutionRequest.model_validate(payload)
    approval_id = str(uuid.uuid4())
    key = f"{_KEY_PREFIX}{approval_id}"
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "approval_id": approval_id,
        "status": "pending",
        "payload": json.dumps(request.model_dump(mode="json")),
        "correlation_id": correlation_id,
        "symbol": symbol or request.symbol or "",
        "side": side or request.side or "",
        "amount": str(amount or request.amount or request.size_usd or ""),
        "proposal_id": proposal_id or request.proposal_id or "",
        "execution_mode": execution_mode or "",
        "decision_reasons": json.dumps(decision_reasons or []),
        "operator_action": "",
        "outcome_event_id": "",
        "created_at": now,
        "updated_at": now,
        "approved_at": "",
        "rejected_at": "",
        "expired_at": "",
        "operator": "",
        "reject_reason": "",
    }
    client = _redis()
    client.hset(key, mapping=data)
    client.expire(key, _TTL_SECONDS)
    client.lpush(_PENDING_LIST, approval_id)
    logger.info(
        "approvals: created approval_id=%s proposal_id=%s correlation_id=%s mode=%s",
        approval_id,
        data["proposal_id"],
        correlation_id,
        execution_mode or "unknown",
    )
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
    """Mark a **pending** approval as approved.

    Returns the updated approval dict, or ``None`` if not found or already
    in a terminal state (approved / rejected / expired).

    On approval the original payload is re-published to Redis Streams so the
    execution worker can process it.
    """
    client = _redis()
    key = f"{_KEY_PREFIX}{approval_id}"
    if not client.exists(key):
        logger.warning("approvals: approve_request called for unknown approval_id=%s", approval_id)
        return None
    current_status = (client.hget(key, "status") or b"").decode()
    if current_status != "pending":
        logger.warning(
            "approvals: approve_request rejected — approval_id=%s is already %s",
            approval_id,
            current_status,
        )
        return None
    now = datetime.now(timezone.utc).isoformat()
    client.hset(
        key,
        mapping={
            "status": "approved",
            "approved_at": now,
            "updated_at": now,
            "operator": operator,
            "operator_action": "approved",
        },
    )
    raw = client.hgetall(key)
    approval = _deserialize(raw)
    # Re-publish the original execution payload so the worker can proceed
    outcome_event_id = _republish_for_execution(approval, client)
    if outcome_event_id:
        client.hset(key, "outcome_event_id", outcome_event_id)
    logger.info("approvals: approved approval_id=%s operator=%s", approval_id, operator)
    try:
        from backend.trading.lifecycle_notifications import notify_approval_granted
        notify_approval_granted(
            approval_id=approval_id,
            symbol=approval.get("symbol") or "unknown",
            side=approval.get("side") or "unknown",
            amount=float(approval.get("amount") or 0),
        )
    except Exception as exc:
        logger.debug("approvals: notification for grant failed: %s", exc)
    return approval


def reject_request(approval_id: str, reason: str = "", operator: str = "api") -> dict | None:
    """Mark a **pending** approval as rejected.

    Returns the updated dict, or ``None`` if not found or already in a
    terminal state.
    """
    client = _redis()
    key = f"{_KEY_PREFIX}{approval_id}"
    if not client.exists(key):
        logger.warning("approvals: reject_request called for unknown approval_id=%s", approval_id)
        return None
    current_status = (client.hget(key, "status") or b"").decode()
    if current_status != "pending":
        logger.warning(
            "approvals: reject_request rejected — approval_id=%s is already %s",
            approval_id,
            current_status,
        )
        return None
    now = datetime.now(timezone.utc).isoformat()
    client.hset(
        key,
        mapping={
            "status": "rejected",
            "rejected_at": now,
            "updated_at": now,
            "operator": operator,
            "operator_action": "rejected",
            "reject_reason": reason,
        },
    )
    raw = client.hgetall(key)
    result = _deserialize(raw)
    logger.info("approvals: rejected approval_id=%s operator=%s reason=%s", approval_id, operator, reason)
    try:
        from backend.trading.lifecycle_notifications import notify_approval_rejected
        notify_approval_rejected(
            approval_id=approval_id,
            symbol=result.get("symbol") or "unknown",
            reason=reason or None,
        )
    except Exception as exc:
        logger.debug("approvals: notification for reject failed: %s", exc)
    return result


def expire_request(approval_id: str) -> dict | None:
    """Explicitly expire a **pending** approval, preventing future execution.

    Returns the updated dict or ``None`` if not found / already terminal.
    This is an alternative to waiting for the Redis TTL to evict the key;
    it immediately marks the approval as ``expired`` so any late ``approve``
    call will be rejected by the status guard.
    """
    client = _redis()
    key = f"{_KEY_PREFIX}{approval_id}"
    if not client.exists(key):
        return None
    current_status = (client.hget(key, "status") or b"").decode()
    if current_status != "pending":
        logger.warning(
            "approvals: expire_request skipped — approval_id=%s is already %s",
            approval_id,
            current_status,
        )
        return None
    now = datetime.now(timezone.utc).isoformat()
    client.hset(
        key,
        mapping={"status": "expired", "expired_at": now, "updated_at": now},
    )
    raw = client.hgetall(key)
    logger.info("approvals: expired approval_id=%s", approval_id)
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
    # Parse decision_reasons back to list
    reasons_str = result.get("decision_reasons", "[]")
    try:
        result["decision_reasons"] = json.loads(reasons_str)
    except (ValueError, TypeError):
        result["decision_reasons"] = []
    # Convert empty strings to None for optional fields
    for field in (
        "approved_at", "rejected_at", "expired_at", "operator",
        "reject_reason", "symbol", "side", "proposal_id",
        "execution_mode", "operator_action", "outcome_event_id",
    ):
        if result.get(field) == "":
            result[field] = None
    return result


def _republish_for_execution(approval: dict, client) -> str | None:
    """Re-publish the approved execution payload to the execution_requested stream.

    Injects ``approval_id`` and ``approved_by`` into the execution request so
    the worker's approval gate recognises the request as already approved and
    proceeds without re-queuing.

    Returns the new event_id on success, or None on failure.
    """
    try:
        from backend.event_bus.models import TradingEvent
        from backend.event_bus.publisher import publish_trading_event

        payload = approval.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}

        # Inject approval identity so the execution worker skips re-gating
        enriched_payload = {
            **payload,
            "approval_id": approval["approval_id"],
            "approved_by": approval.get("operator") or "api",
        }
        # Validate through the model to ensure the enriched payload is sane
        request = ExecutionRequest.model_validate(enriched_payload)

        event = TradingEvent(
            event_type="execution_requested",
            symbol=approval.get("symbol") or request.symbol,
            correlation_id=approval.get("correlation_id") or "",
            causation_id=approval["approval_id"],
            producer="approval_store",
            workflow_id=approval.get("proposal_id") or approval.get("correlation_id") or "",
            payload=request.model_dump(mode="json"),
            metadata={
                "approval_id": approval["approval_id"],
                "proposal_id": approval.get("proposal_id") or "",
                "operator": approval.get("operator") or "api",
                "execution_mode": approval.get("execution_mode") or "unknown",
            },
        )
        envelope = publish_trading_event(event)
        logger.info(
            "approvals: re-published execution_requested for approval_id=%s event_id=%s",
            approval["approval_id"],
            envelope.event.event_id,
        )
        return envelope.event.event_id
    except Exception as exc:
        logger.warning(
            "approvals: could not re-publish execution event for approval_id=%s: %s",
            approval.get("approval_id"),
            exc,
        )
        return None
