"""Consumer-group bootstrap helpers for Redis Streams."""

from __future__ import annotations

import logging
from collections.abc import Iterable

from redis import Redis
from redis.exceptions import ResponseError

from backend.redis_client import get_redis_client

from .schema import DEFAULT_TRADING_STREAM

logger = logging.getLogger(__name__)

DEFAULT_CONSUMER_GROUPS: tuple[str, ...] = (
    "orchestrator_group",
    "strategy_group",
    "risk_group",
    "notifications_group",
)


def ensure_consumer_group(
    group_name: str,
    *,
    redis_client: Redis | None = None,
    stream: str = DEFAULT_TRADING_STREAM,
    start_id: str = "0",
) -> bool:
    client = redis_client or get_redis_client()
    try:
        client.xgroup_create(name=stream, groupname=group_name, id=start_id, mkstream=True)
        logger.info("Created Redis consumer group %s on %s", group_name, stream)
        return True
    except ResponseError as exc:
        if "BUSYGROUP" in str(exc):
            logger.info("Redis consumer group %s already exists on %s", group_name, stream)
            return False
        raise


def bootstrap_consumer_groups(
    groups: Iterable[str] = DEFAULT_CONSUMER_GROUPS,
    *,
    redis_client: Redis | None = None,
    stream: str = DEFAULT_TRADING_STREAM,
    start_id: str = "0",
) -> dict[str, bool]:
    client = redis_client or get_redis_client()
    results = {
        group_name: ensure_consumer_group(
            group_name,
            redis_client=client,
            stream=stream,
            start_id=start_id,
        )
        for group_name in groups
    }
    logger.info(
        "Redis consumer group bootstrap completed for %s: %s",
        stream,
        ", ".join(f"{group}={'created' if created else 'existing'}" for group, created in results.items()),
    )
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = bootstrap_consumer_groups()
    for group_name, created in results.items():
        state = "created" if created else "existing"
        print(f"{group_name}: {state}")
