"""Redis Streams publisher helpers for Hermes trading workflows."""

from __future__ import annotations

import logging
import os

from redis import Redis

from backend.redis_client import get_redis_client

from .models import TradingEvent, TradingEventEnvelope
from .schema import DEFAULT_TRADING_STREAM

logger = logging.getLogger(__name__)


def _stream_maxlen() -> int | None:
    raw = os.getenv("REDIS_STREAM_MAXLEN", "").strip()
    if not raw:
        return None
    try:
        return max(1, int(raw))
    except ValueError:
        logger.warning("Ignoring invalid REDIS_STREAM_MAXLEN=%r", raw)
        return None


class TradingEventPublisher:
    """Central publisher for trading events on Redis Streams."""

    def __init__(self, redis_client: Redis | None = None, *, stream: str = DEFAULT_TRADING_STREAM):
        self.redis = redis_client or get_redis_client()
        self.stream = stream
        self.maxlen = _stream_maxlen()

    def publish(self, event: TradingEvent) -> TradingEventEnvelope:
        envelope = TradingEventEnvelope(stream=self.stream, event=event)
        xadd_kwargs: dict[str, object] = {}
        if self.maxlen is not None:
            xadd_kwargs["maxlen"] = self.maxlen
            xadd_kwargs["approximate"] = True
        redis_id = self.redis.xadd(self.stream, envelope.to_stream_fields(), **xadd_kwargs)
        logger.info(
            "Published trading event %s (%s) to %s as %s",
            event.event_type,
            event.event_id,
            self.stream,
            redis_id,
        )
        return envelope.model_copy(update={"redis_id": redis_id})


# Convenience module-level function so callers don't need to instantiate the class.
def publish_trading_event(event: TradingEvent) -> TradingEventEnvelope:
    """Publish a single trading event using a default publisher instance."""
    return TradingEventPublisher().publish(event)
