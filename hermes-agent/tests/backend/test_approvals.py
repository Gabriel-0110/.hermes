"""Focused tests for approval state transitions in backend/approvals.py.

All Redis interactions are patched with a simple in-memory dict so the tests
run without a live Redis instance.
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_MINIMAL_EXEC_PAYLOAD = {
    "symbol": "BTCUSDT",
    "side": "buy",
    "order_type": "market",
    "size_usd": 100.0,
    "amount": 100.0,
    "rationale": "Unit test trade.",
    "source_agent": "test_agent",
}


def _fake_redis_factory():
    """Return a minimal in-memory Redis stand-in."""
    store: dict[str, dict] = {}
    lists: dict[str, list] = {}

    class FakeRedis:
        def hset(self, key, field_or_mapping=None, value=None, mapping=None, **kwargs):
            if isinstance(field_or_mapping, dict):
                store.setdefault(key, {}).update(field_or_mapping)
            elif mapping is not None:
                store.setdefault(key, {}).update(mapping)
            elif field_or_mapping is not None and value is not None:
                store.setdefault(key, {})[field_or_mapping] = value

        def hget(self, key, field):
            v = store.get(key, {}).get(field)
            return v.encode() if isinstance(v, str) else v

        def hgetall(self, key):
            return {k: v.encode() if isinstance(v, str) else v for k, v in store.get(key, {}).items()}

        def exists(self, key):
            return key in store

        def expire(self, key, seconds):
            pass

        def lpush(self, key, *values):
            lists.setdefault(key, [])
            for v in reversed(values):
                lists[key].insert(0, v.encode() if isinstance(v, str) else v)

        def lrange(self, key, start, end):
            lst = lists.get(key, [])
            return lst[start : end + 1 if end != -1 else None]

    return FakeRedis(), store, lists


# ---------------------------------------------------------------------------
# create_approval_request
# ---------------------------------------------------------------------------


class TestCreateApprovalRequest:
    def test_stores_pending_status_and_linkage(self):
        fake_redis, store, _ = _fake_redis_factory()
        with patch("backend.approvals._redis", return_value=fake_redis):
            from backend.approvals import create_approval_request

            aid = create_approval_request(
                _MINIMAL_EXEC_PAYLOAD,
                "corr-123",
                proposal_id="proposal_abc",
                execution_mode="paper",
                decision_reasons=["approval=required"],
            )

        assert isinstance(aid, str)
        key = f"hermes:approvals:{aid}"
        assert key in store
        record = store[key]
        assert record["status"] == "pending"
        assert record["proposal_id"] == "proposal_abc"
        assert record["execution_mode"] == "paper"
        assert json.loads(record["decision_reasons"]) == ["approval=required"]
        assert record["approved_at"] == ""
        assert record["rejected_at"] == ""
        assert record["expired_at"] == ""

    def test_stores_symbol_side_amount(self):
        fake_redis, store, _ = _fake_redis_factory()
        with patch("backend.approvals._redis", return_value=fake_redis):
            from importlib import reload
            import backend.approvals as approvals_mod

            aid = approvals_mod.create_approval_request(
                _MINIMAL_EXEC_PAYLOAD,
                "corr-xyz",
                symbol="ETHUSDT",
                side="sell",
                amount=250.0,
            )

        record = store[f"hermes:approvals:{aid}"]
        assert record["symbol"] == "ETHUSDT"
        assert record["side"] == "sell"
        assert record["amount"] == "250.0"

    def test_adds_to_pending_list(self):
        fake_redis, store, lists = _fake_redis_factory()
        with patch("backend.approvals._redis", return_value=fake_redis):
            import backend.approvals as approvals_mod

            aid = approvals_mod.create_approval_request(_MINIMAL_EXEC_PAYLOAD, "c1")

        pending = lists.get("hermes:approvals:pending_ids", [])
        assert any(
            (v.decode() if isinstance(v, bytes) else v) == aid for v in pending
        )


# ---------------------------------------------------------------------------
# approve_request — state guard
# ---------------------------------------------------------------------------


class TestApproveRequest:
    def _setup_pending(self, fake_redis, store, extra=None):
        """Pre-populate store with one pending approval."""
        aid = str(uuid.uuid4())
        key = f"hermes:approvals:{aid}"
        base = {
            "approval_id": aid,
            "status": "pending",
            "payload": json.dumps({**_MINIMAL_EXEC_PAYLOAD, "approval_id": None}),
            "correlation_id": "corr-abc",
            "symbol": "BTCUSDT",
            "side": "buy",
            "amount": "100.0",
            "proposal_id": "prop_001",
            "execution_mode": "paper",
            "decision_reasons": "[]",
            "operator_action": "",
            "outcome_event_id": "",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "approved_at": "",
            "rejected_at": "",
            "expired_at": "",
            "operator": "",
            "reject_reason": "",
        }
        if extra:
            base.update(extra)
        store[key] = base
        return aid

    def test_approve_pending_returns_updated_record(self):
        fake_redis, store, _ = _fake_redis_factory()
        aid = self._setup_pending(fake_redis, store)

        published = []
        with (
            patch("backend.approvals._redis", return_value=fake_redis),
            patch(
                "backend.event_bus.publisher.publish_trading_event",
                side_effect=lambda ev: published.append(ev) or SimpleNamespace(event=SimpleNamespace(event_id="ev-001")),
            ),
            patch("backend.trading.lifecycle_notifications.notify_approval_granted"),
        ):
            import backend.approvals as approvals_mod

            result = approvals_mod.approve_request(aid, operator="alice")

        assert result is not None
        assert result["status"] == "approved"
        assert result["operator"] == "alice"
        assert result["operator_action"] == "approved"
        assert result["approved_at"]

    def test_approve_pending_republishes_execution_event(self):
        fake_redis, store, _ = _fake_redis_factory()
        aid = self._setup_pending(fake_redis, store)

        published = []
        with (
            patch("backend.approvals._redis", return_value=fake_redis),
            patch(
                "backend.event_bus.publisher.publish_trading_event",
                side_effect=lambda ev: published.append(ev) or SimpleNamespace(event=SimpleNamespace(event_id="ev-002")),
            ),
            patch("backend.trading.lifecycle_notifications.notify_approval_granted"),
        ):
            import backend.approvals as approvals_mod

            approvals_mod.approve_request(aid, operator="bob")

        assert len(published) == 1
        event = published[0]
        assert event.event_type == "execution_requested"
        assert event.payload.get("approval_id") == aid
        assert event.payload.get("approved_by") == "bob"

    def test_approve_already_approved_returns_none(self):
        fake_redis, store, _ = _fake_redis_factory()
        aid = self._setup_pending(fake_redis, store, extra={"status": "approved"})

        with (
            patch("backend.approvals._redis", return_value=fake_redis),
            patch("backend.event_bus.publisher.publish_trading_event"),
        ):
            import backend.approvals as approvals_mod

            result = approvals_mod.approve_request(aid)

        assert result is None

    def test_approve_rejected_approval_returns_none(self):
        fake_redis, store, _ = _fake_redis_factory()
        aid = self._setup_pending(fake_redis, store, extra={"status": "rejected"})

        with patch("backend.approvals._redis", return_value=fake_redis):
            import backend.approvals as approvals_mod

            result = approvals_mod.approve_request(aid)

        assert result is None

    def test_approve_expired_approval_returns_none(self):
        fake_redis, store, _ = _fake_redis_factory()
        aid = self._setup_pending(fake_redis, store, extra={"status": "expired"})

        with patch("backend.approvals._redis", return_value=fake_redis):
            import backend.approvals as approvals_mod

            result = approvals_mod.approve_request(aid)

        assert result is None

    def test_approve_unknown_id_returns_none(self):
        fake_redis, store, _ = _fake_redis_factory()
        with patch("backend.approvals._redis", return_value=fake_redis):
            import backend.approvals as approvals_mod

            result = approvals_mod.approve_request("nonexistent-id")

        assert result is None


# ---------------------------------------------------------------------------
# reject_request — state guard
# ---------------------------------------------------------------------------


class TestRejectRequest:
    def _setup_pending(self, store, extra=None):
        aid = str(uuid.uuid4())
        key = f"hermes:approvals:{aid}"
        base = {
            "approval_id": aid,
            "status": "pending",
            "payload": json.dumps(_MINIMAL_EXEC_PAYLOAD),
            "correlation_id": "corr-rej",
            "symbol": "ETHUSDT",
            "side": "sell",
            "amount": "50.0",
            "proposal_id": "prop_rej",
            "execution_mode": "live",
            "decision_reasons": "[]",
            "operator_action": "",
            "outcome_event_id": "",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "approved_at": "",
            "rejected_at": "",
            "expired_at": "",
            "operator": "",
            "reject_reason": "",
        }
        if extra:
            base.update(extra)
        store[key] = base
        return aid

    def test_reject_pending_marks_rejected(self):
        fake_redis, store, _ = _fake_redis_factory()
        aid = self._setup_pending(store)

        with (
            patch("backend.approvals._redis", return_value=fake_redis),
            patch("backend.trading.lifecycle_notifications.notify_approval_rejected"),
        ):
            import backend.approvals as approvals_mod

            result = approvals_mod.reject_request(aid, reason="Too large", operator="carol")

        assert result is not None
        assert result["status"] == "rejected"
        assert result["operator"] == "carol"
        assert result["operator_action"] == "rejected"
        assert result["reject_reason"] == "Too large"
        assert result["rejected_at"]

    def test_reject_already_approved_returns_none(self):
        fake_redis, store, _ = _fake_redis_factory()
        aid = self._setup_pending(store, extra={"status": "approved"})

        with patch("backend.approvals._redis", return_value=fake_redis):
            import backend.approvals as approvals_mod

            result = approvals_mod.reject_request(aid, reason="too late")

        assert result is None

    def test_reject_already_rejected_returns_none(self):
        fake_redis, store, _ = _fake_redis_factory()
        aid = self._setup_pending(store, extra={"status": "rejected"})

        with patch("backend.approvals._redis", return_value=fake_redis):
            import backend.approvals as approvals_mod

            result = approvals_mod.reject_request(aid)

        assert result is None

    def test_reject_unknown_id_returns_none(self):
        fake_redis, store, _ = _fake_redis_factory()
        with patch("backend.approvals._redis", return_value=fake_redis):
            import backend.approvals as approvals_mod

            result = approvals_mod.reject_request("no-such-id")

        assert result is None


# ---------------------------------------------------------------------------
# expire_request
# ---------------------------------------------------------------------------


class TestExpireRequest:
    def _setup_pending(self, store, extra=None):
        aid = str(uuid.uuid4())
        key = f"hermes:approvals:{aid}"
        base = {
            "approval_id": aid,
            "status": "pending",
            "payload": json.dumps(_MINIMAL_EXEC_PAYLOAD),
            "correlation_id": "corr-exp",
            "symbol": "SOLUSDT",
            "side": "buy",
            "amount": "30.0",
            "proposal_id": "prop_exp",
            "execution_mode": "paper",
            "decision_reasons": "[]",
            "operator_action": "",
            "outcome_event_id": "",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "approved_at": "",
            "rejected_at": "",
            "expired_at": "",
            "operator": "",
            "reject_reason": "",
        }
        if extra:
            base.update(extra)
        store[key] = base
        return aid

    def test_expire_pending_marks_expired(self):
        fake_redis, store, _ = _fake_redis_factory()
        aid = self._setup_pending(store)

        with patch("backend.approvals._redis", return_value=fake_redis):
            import backend.approvals as approvals_mod

            result = approvals_mod.expire_request(aid)

        assert result is not None
        assert result["status"] == "expired"
        assert result["expired_at"]

    def test_expire_then_approve_is_rejected(self):
        """After expiry, a subsequent approve_request must return None."""
        fake_redis, store, _ = _fake_redis_factory()
        aid = self._setup_pending(store)

        with (
            patch("backend.approvals._redis", return_value=fake_redis),
            patch("backend.event_bus.publisher.publish_trading_event"),
        ):
            import backend.approvals as approvals_mod

            approvals_mod.expire_request(aid)
            result = approvals_mod.approve_request(aid)

        assert result is None

    def test_expire_already_approved_returns_none(self):
        fake_redis, store, _ = _fake_redis_factory()
        aid = self._setup_pending(store, extra={"status": "approved"})

        with patch("backend.approvals._redis", return_value=fake_redis):
            import backend.approvals as approvals_mod

            result = approvals_mod.expire_request(aid)

        assert result is None

    def test_expire_unknown_id_returns_none(self):
        fake_redis, store, _ = _fake_redis_factory()
        with patch("backend.approvals._redis", return_value=fake_redis):
            import backend.approvals as approvals_mod

            result = approvals_mod.expire_request("ghost-id")

        assert result is None


# ---------------------------------------------------------------------------
# republish — approval_id injected into execution payload
# ---------------------------------------------------------------------------


class TestRepublish:
    def test_republished_payload_contains_approval_id_and_operator(self):
        fake_redis, store, _ = _fake_redis_factory()

        published = []
        aid = str(uuid.uuid4())
        key = f"hermes:approvals:{aid}"
        store[key] = {
            "approval_id": aid,
            "status": "pending",
            "payload": json.dumps({**_MINIMAL_EXEC_PAYLOAD, "approval_id": None}),
            "correlation_id": "corr-rep",
            "symbol": "BTCUSDT",
            "side": "buy",
            "amount": "100.0",
            "proposal_id": "prop_rep",
            "execution_mode": "live",
            "decision_reasons": "[]",
            "operator_action": "",
            "outcome_event_id": "",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "approved_at": "",
            "rejected_at": "",
            "expired_at": "",
            "operator": "",
            "reject_reason": "",
        }

        def _fake_publish(ev):
            published.append(ev)
            return SimpleNamespace(event=SimpleNamespace(event_id="ev-rep-001"))

        with (
            patch("backend.approvals._redis", return_value=fake_redis),
            patch("backend.event_bus.publisher.publish_trading_event", side_effect=_fake_publish),
            patch("backend.trading.lifecycle_notifications.notify_approval_granted"),
        ):
            import backend.approvals as approvals_mod

            approvals_mod.approve_request(aid, operator="dave")

        assert len(published) == 1
        ev = published[0]
        assert ev.payload["approval_id"] == aid
        assert ev.payload["approved_by"] == "dave"
        assert ev.metadata["proposal_id"] == "prop_rep"
        assert ev.metadata["execution_mode"] == "live"
