from __future__ import annotations

import json

from redis.exceptions import ResponseError

from backend.event_bus.bootstrap import bootstrap_consumer_groups, ensure_consumer_group
from backend.event_bus.consumer import RedisStreamWorker
from backend.event_bus.models import TradingEvent, TradingEventEnvelope
from backend.event_bus.publisher import TradingEventPublisher


class FakeRedisPublisher:
    def __init__(self):
        self.calls: list[dict[str, object]] = []

    def xadd(self, stream: str, fields: dict[str, str], **kwargs: object) -> str:
        self.calls.append({"stream": stream, "fields": fields, "kwargs": kwargs})
        return "1744740000000-0"


class FakeRedisBootstrap:
    def __init__(self, busy_groups: set[str] | None = None):
        self.busy_groups = busy_groups or set()
        self.created: list[tuple[str, str, str, bool]] = []

    def xgroup_create(self, name: str, groupname: str, id: str, mkstream: bool) -> None:
        self.created.append((name, groupname, id, mkstream))
        if groupname in self.busy_groups:
            raise ResponseError("BUSYGROUP Consumer Group name already exists")


class FakeRedisWorker:
    def __init__(self, messages: list[tuple[str, list[tuple[str, dict[str, str]]]]]):
        self.messages = messages
        self.acked: list[tuple[str, str, str]] = []
        self.group_creates: list[tuple[str, str, str, bool]] = []

    def xgroup_create(self, name: str, groupname: str, id: str, mkstream: bool) -> None:
        self.group_creates.append((name, groupname, id, mkstream))

    def xreadgroup(
        self,
        *,
        groupname: str,
        consumername: str,
        streams: dict[str, str],
        count: int,
        block: int,
    ) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        return self.messages

    def xack(self, stream: str, group_name: str, redis_id: str) -> int:
        self.acked.append((stream, group_name, redis_id))
        return 1


def _stream_fields(event_type: str) -> dict[str, str]:
    return TradingEventEnvelope(
        event=TradingEvent(
            event_id="evt-1",
            event_type=event_type,  # type: ignore[arg-type]
            source="test",
            payload={"value": 1},
        )
    ).to_stream_fields()


def test_publisher_serializes_event_for_xadd():
    fake_redis = FakeRedisPublisher()
    publisher = TradingEventPublisher(redis_client=fake_redis, stream="events:trading")

    envelope = publisher.publish(
        TradingEvent(
            event_id="evt-123",
            event_type="risk_review_requested",
            source="test-suite",
            symbol="BTCUSDT",
            payload={"score": 0.42},
            metadata={"agent": "orchestrator"},
        )
    )

    assert envelope.redis_id == "1744740000000-0"
    assert len(fake_redis.calls) == 1
    fields = fake_redis.calls[0]["fields"]
    assert fields["event_id"] == "evt-123"
    assert fields["event_type"] == "risk_review_requested"
    assert json.loads(fields["payload"]) == {"score": 0.42}
    assert json.loads(fields["metadata"]) == {"agent": "orchestrator"}


def test_ensure_consumer_group_handles_existing_group():
    fake_redis = FakeRedisBootstrap(busy_groups={"risk_group"})

    created = ensure_consumer_group("risk_group", redis_client=fake_redis)

    assert created is False
    assert fake_redis.created == [("events:trading", "risk_group", "0", True)]


def test_bootstrap_consumer_groups_creates_multiple_groups():
    fake_redis = FakeRedisBootstrap()

    results = bootstrap_consumer_groups(("orchestrator_group", "strategy_group"), redis_client=fake_redis)

    assert results == {"orchestrator_group": True, "strategy_group": True}
    assert fake_redis.created == [
        ("events:trading", "orchestrator_group", "0", True),
        ("events:trading", "strategy_group", "0", True),
    ]


def test_worker_acks_successful_messages():
    fake_redis = FakeRedisWorker(messages=[("events:trading", [("1-0", _stream_fields("tradingview_signal_ready"))])])
    worker = RedisStreamWorker(group_name="strategy_group", consumer_name="worker-1", redis_client=fake_redis)

    handled: list[str] = []

    processed = worker.poll_once(lambda envelope: handled.append(envelope.event.event_type) or True)

    assert processed == 1
    assert handled == ["tradingview_signal_ready"]
    assert fake_redis.acked == [("events:trading", "strategy_group", "1-0")]


def test_worker_leaves_failed_messages_unacked():
    fake_redis = FakeRedisWorker(messages=[("events:trading", [("1-0", _stream_fields("notification_requested"))])])
    worker = RedisStreamWorker(group_name="notifications_group", consumer_name="worker-1", redis_client=fake_redis)

    def fail(_: TradingEventEnvelope) -> bool:
        raise RuntimeError("boom")

    processed = worker.poll_once(fail)

    assert processed == 0
    assert fake_redis.acked == []
