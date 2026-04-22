"""Runtime bootstrap and inspection helpers for the Hermes Redis event bus."""

from __future__ import annotations

import logging

from redis import Redis
from redis.exceptions import RedisError

from backend.redis_client import get_redis_client, get_redis_url, ping_redis

from .bootstrap import DEFAULT_CONSUMER_GROUPS, bootstrap_consumer_groups
from .schema import DEFAULT_TRADING_STREAM

logger = logging.getLogger(__name__)

_BOOTSTRAPPED_STREAMS: set[str] = set()


def bootstrap_event_bus_on_startup(
    *,
    redis_client: Redis | None = None,
    stream: str = DEFAULT_TRADING_STREAM,
) -> None:
    """Initialize Redis connectivity and required consumer groups for live runtimes."""

    if stream in _BOOTSTRAPPED_STREAMS:
        logger.warning("Redis event bus bootstrap skipped: already completed in this process for %s.", stream)
        return

    client = redis_client or get_redis_client()
    redis_url = get_redis_url()
    logger.warning("Redis event bus bootstrap started: redis_url=%s stream=%s", redis_url, stream)

    if not ping_redis(redis_url=redis_url):
        logger.error("Redis event bus bootstrap failed: Redis is unreachable at %s", redis_url)
        raise RuntimeError(f"Redis is unreachable at {redis_url}")

    try:
        results = bootstrap_consumer_groups(DEFAULT_CONSUMER_GROUPS, redis_client=client, stream=stream)
    except RedisError:
        logger.exception("Redis consumer group bootstrap failed for stream=%s", stream)
        raise

    logger.info(
        "Redis event bus bootstrap succeeded: stream=%s groups=%s",
        stream,
        ", ".join(f"{group}={'created' if created else 'existing'}" for group, created in results.items()),
    )
    logger.warning(
        "Redis event bus bootstrap succeeded: stream=%s groups=%s",
        stream,
        ", ".join(f"{group}={'created' if created else 'existing'}" for group, created in results.items()),
    )
    _BOOTSTRAPPED_STREAMS.add(stream)


def list_consumer_groups(
    *,
    redis_client: Redis | None = None,
    stream: str = DEFAULT_TRADING_STREAM,
) -> list[dict[str, object]]:
    client = redis_client or get_redis_client()
    groups = client.xinfo_groups(stream)
    logger.info("Redis event bus group inspection: stream=%s groups=%s", stream, len(groups))
    return groups


def inspect_pending(
    group_name: str,
    *,
    redis_client: Redis | None = None,
    stream: str = DEFAULT_TRADING_STREAM,
) -> dict[str, object]:
    client = redis_client or get_redis_client()
    summary = client.xpending(stream, group_name)
    logger.info("Redis pending inspection: stream=%s group=%s summary=%s", stream, group_name, summary)
    return summary


def inspect_stream(
    *,
    redis_client: Redis | None = None,
    stream: str = DEFAULT_TRADING_STREAM,
) -> dict[str, object]:
    client = redis_client or get_redis_client()
    info = client.xinfo_stream(stream)
    logger.info("Redis stream inspection: stream=%s length=%s", stream, info.get("length"))
    return info


def ensure_stream_exists(
    *,
    redis_client: Redis | None = None,
    stream: str = DEFAULT_TRADING_STREAM,
) -> bool:
    client = redis_client or get_redis_client()
    try:
        client.xinfo_stream(stream)
        logger.info("Redis stream already exists: %s", stream)
        return False
    except RedisError:
        client.xgroup_create(name=stream, groupname="__bootstrap__", id="0", mkstream=True)
        client.xgroup_destroy(stream, "__bootstrap__")
        logger.info("Created Redis stream via bootstrap helper: %s", stream)
        return True
