"""Reusable Redis Streams consumer scaffolding for Hermes workers."""

from __future__ import annotations

import logging
import socket
import time
from collections.abc import Callable

from redis import Redis
from redis.exceptions import RedisError

from backend.redis_client import get_redis_client

from .bootstrap import ensure_consumer_group
from .models import TradingEventEnvelope
from .schema import DEFAULT_TRADING_STREAM

logger = logging.getLogger(__name__)

TradingEventHandler = Callable[[TradingEventEnvelope], bool | None]


class RedisStreamWorker:
    """Generic worker loop for a single Redis Streams consumer group."""

    def __init__(
        self,
        *,
        group_name: str,
        consumer_name: str | None = None,
        redis_client: Redis | None = None,
        stream: str = DEFAULT_TRADING_STREAM,
        block_ms: int = 5000,
        count: int = 10,
        start_id: str = "0",
    ):
        self.redis = redis_client or get_redis_client()
        self.stream = stream
        self.group_name = group_name
        self.consumer_name = consumer_name or f"{socket.gethostname()}-{group_name}"
        self.block_ms = max(1, block_ms)
        self.count = max(1, count)
        ensure_consumer_group(group_name, redis_client=self.redis, stream=stream, start_id=start_id)

    def poll_once(self, handler: TradingEventHandler) -> int:
        logger.info(
            "Worker %s polling stream=%s consumer=%s block_ms=%s count=%s",
            self.group_name,
            self.stream,
            self.consumer_name,
            self.block_ms,
            self.count,
        )
        messages = self.redis.xreadgroup(
            groupname=self.group_name,
            consumername=self.consumer_name,
            streams={self.stream: ">"},
            count=self.count,
            block=self.block_ms,
        )
        processed = 0
        for stream_name, stream_messages in messages:
            for redis_id, fields in stream_messages:
                envelope = TradingEventEnvelope.from_stream_message(
                    stream=stream_name,
                    redis_id=redis_id,
                    fields=fields,
                )
                try:
                    result = handler(envelope)
                except Exception:
                    logger.exception(
                        "Worker %s failed to process %s (%s); leaving unacked",
                        self.group_name,
                        envelope.event.event_type,
                        redis_id,
                    )
                    continue
                if result is False:
                    logger.warning(
                        "Worker %s handler returned False for %s (%s); leaving unacked",
                        self.group_name,
                        envelope.event.event_type,
                        redis_id,
                    )
                    continue
                try:
                    self.redis.xack(self.stream, self.group_name, redis_id)
                except RedisError:
                    logger.exception(
                        "Worker %s failed to ack %s (%s)",
                        self.group_name,
                        envelope.event.event_type,
                        redis_id,
                    )
                    continue
                processed += 1
                logger.info(
                    "Worker %s acked %s (%s)",
                    self.group_name,
                    envelope.event.event_type,
                    redis_id,
                )
        return processed

    def run_forever(self, handler: TradingEventHandler, *, idle_sleep_seconds: float = 1.0) -> None:
        logger.info(
            "Worker %s entering run loop on stream=%s consumer=%s",
            self.group_name,
            self.stream,
            self.consumer_name,
        )
        while True:
            processed = self.poll_once(handler)
            if processed == 0:
                time.sleep(max(0.0, idle_sleep_seconds))
